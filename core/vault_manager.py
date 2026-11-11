"""High-level vault operations: create, inspect, unlock, verify, restore,
change password, recover. Independent of the GUI (progress/cancel are callbacks).

Safety rules enforced here
--------------------------
* A vault is written to a temporary ``*.flock.partial-*`` file, fully verified
  (authentication of every chunk, per-file SHA-256 against the source, password
  and recovery key both unwrap the DEK) and only then atomically renamed.
* Restored data is extracted into a hidden staging folder, verified on disk and
  only then moved to its final, never-overwriting location.
* Header updates use two slots so an interruption can never lose the vault.
"""
from __future__ import annotations

import hashlib
import os
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Callable

from cryptography.exceptions import InvalidTag

from core import folder_manager as fm
from core.vault_format import (
    BODY_OFFSET, FORMAT_VERSION, PARTIAL_MARKER, SLOT_OFFSETS, TAG_DIR, TAG_END,
    TAG_FILE, TAG_ROOT, canonical, check_preamble, encode_preamble, encode_slot,
    read_slots, PREAMBLE_SIZE,
)
from security import key_manager as km
from security.encryption import CHUNK_SIZE, TAG_SIZE, ChunkDecryptor, ChunkEncryptor
from security.recovery import InvalidRecoveryKeyFormat, parse_recovery_key
from utils.error_handler import (
    CorruptedVaultError, DestinationError, InvalidVaultError, OperationCancelled,
    SourceFolderError, VerificationError, WrongPasswordError, WrongRecoveryKeyError,
)
from utils.paths import unique_path

ProgressCB = Callable[[str, int, int], None]      # (phase, done, total)
CancelCB = Callable[[], bool]

_MIN_CHUNK, _MAX_CHUNK = 64 * 1024, 16 * 1024 * 1024
_IO_BLOCK = 1024 * 1024


# --------------------------------------------------------------------------- #
# Data classes
# --------------------------------------------------------------------------- #
@dataclass
class VaultKeys:
    """Unwrapped key material for one open vault. Keep short-lived."""
    dek: bytes
    data_key: bytes
    mac_key: bytes
    vault_id: bytes
    chunk_size: int
    generation: int
    slot_index: int
    core: dict
    via: str                       # "password" | "recovery"


@dataclass
class VaultInfo:
    path: Path
    size: int
    version: int


@dataclass
class VaultStats:
    root_name: str
    files: int
    dirs: int
    total_bytes: int
    skipped_links: int = 0


@dataclass
class CreateResult:
    vault_path: Path
    stats: VaultStats
    vault_bytes: int


@dataclass
class _Digests:
    root: str = ""
    files: dict[str, bytes] = field(default_factory=dict)
    sizes: dict[str, int] = field(default_factory=dict)
    dirs: set[str] = field(default_factory=set)
    total_bytes: int = 0


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _noop_progress(_phase: str, _done: int, _total: int) -> None:
    return None


def _check_cancel(cancel: CancelCB | None) -> None:
    if cancel is not None and cancel():
        raise OperationCancelled()


def _u32(n: int) -> bytes:
    return struct.pack(">I", n)


def _wrap_aad(kind: bytes, vault_id: bytes, extra: dict | None) -> bytes:
    return b"FolderLock wrap v1|" + kind + b"|" + vault_id + b"|" + (canonical(extra) if extra else b"")


def _mac_message(core: dict, generation: int) -> bytes:
    return canonical({"core": core, "generation": generation, "version": FORMAT_VERSION})


def _make_payload(core: dict, generation: int, mac_key: bytes) -> dict:
    mac = km.header_mac(mac_key, _mac_message(core, generation))
    return {"generation": generation, "core": core, "mac": mac.hex()}


def _hex(core_part: dict, key: str, size: int | None = None) -> bytes:
    try:
        raw = bytes.fromhex(core_part[key])
    except (KeyError, ValueError, TypeError) as exc:
        raise CorruptedVaultError() from exc
    if size is not None and len(raw) != size:
        raise CorruptedVaultError()
    return raw


# --------------------------------------------------------------------------- #
# Header construction / opening
# --------------------------------------------------------------------------- #
def _build_pw_section(dek: bytes, vault_id: bytes, password: str,
                      kdf: km.KdfParams) -> tuple[dict, bytes]:
    salt = km.random_bytes(km.SALT_SIZE)
    kek = km.derive_password_kek(password, salt, kdf)
    kdf_dict = kdf.to_dict()
    nonce, wrapped = km.wrap_key(kek, dek, _wrap_aad(b"pw", vault_id, kdf_dict))
    return {"kdf": kdf_dict, "salt": salt.hex(), "nonce": nonce.hex(), "wrapped": wrapped.hex()}, kek


def _build_rec_section(dek: bytes, vault_id: bytes, recovery_secret: bytes) -> tuple[dict, bytes]:
    salt = km.random_bytes(km.SALT_SIZE)
    kek = km.derive_recovery_kek(recovery_secret, salt)
    nonce, wrapped = km.wrap_key(kek, dek, _wrap_aad(b"rec", vault_id, None))
    return {"salt": salt.hex(), "nonce": nonce.hex(), "wrapped": wrapped.hex()}, kek


def _open_header(f: BinaryIO, size: int) -> list[tuple[int, dict]]:
    """Validate the preamble and return intact header slots, newest first."""
    if size < BODY_OFFSET + 4 + TAG_SIZE:
        raise InvalidVaultError()
    f.seek(0)
    check_preamble(f.read(PREAMBLE_SIZE))
    slots = read_slots(f)
    if not slots:
        raise CorruptedVaultError()
    slots.sort(key=lambda s: s[1]["generation"], reverse=True)
    return slots


def inspect_vault(path: Path) -> VaultInfo:
    """Cheap, password-free format check used before asking for a password."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            _open_header(f, size)
            f.seek(0)
            version = check_preamble(f.read(PREAMBLE_SIZE))
    except FileNotFoundError as exc:
        raise InvalidVaultError("The vault file could not be found.") from exc
    return VaultInfo(path, size, version)


def _try_slot(slot_index: int, payload: dict, kind: str, secret) -> VaultKeys:
    """Unwrap the DEK from one slot and authenticate the header. May raise
    ``InvalidTag`` (wrong secret) or ``CorruptedVaultError`` (bad header)."""
    try:
        core = payload["core"]
        vault_id = _hex(core, "vault_id", 16)
        chunk = int(core["chunk"])
        if not _MIN_CHUNK <= chunk <= _MAX_CHUNK:
            raise CorruptedVaultError()
        if kind == "password":
            sec = core["pw"]
            params = km.KdfParams.from_dict(sec["kdf"])
            kek = km.derive_password_kek(secret, _hex(sec, "salt", km.SALT_SIZE), params)
            aad = _wrap_aad(b"pw", vault_id, sec["kdf"])
        else:
            sec = core["rec"]
            kek = km.derive_recovery_kek(secret, _hex(sec, "salt", km.SALT_SIZE))
            aad = _wrap_aad(b"rec", vault_id, None)
        nonce, wrapped = _hex(sec, "nonce", km.NONCE_SIZE), _hex(sec, "wrapped")
    except CorruptedVaultError:
        raise
    except (KeyError, ValueError, TypeError) as exc:
        raise CorruptedVaultError() from exc

    dek = km.unwrap_key(kek, nonce, wrapped, aad)          # InvalidTag => wrong secret
    data_key, mac_key = km.derive_subkeys(dek)
    expected = km.header_mac(mac_key, _mac_message(core, payload["generation"]))
    try:
        stored = bytes.fromhex(payload["mac"])
    except (ValueError, TypeError) as exc:
        raise CorruptedVaultError() from exc
    if not km.constant_time_equal(expected, stored):
        raise CorruptedVaultError()                        # header was modified
    return VaultKeys(dek, data_key, mac_key, vault_id, chunk, payload["generation"],
                     slot_index, core, kind)


def _unlock(path: Path, kind: str, secret) -> VaultKeys:
    size = path.stat().st_size
    with open(path, "rb") as f:
        slots = _open_header(f, size)
    tried: set[bytes] = set()
    saw_wrong_secret = False
    last_corrupt: CorruptedVaultError | None = None
    for slot_index, payload in slots:
        fingerprint = canonical(payload["core"])
        if fingerprint in tried:                 # identical mirror slot: skip a second KDF run
            continue
        tried.add(fingerprint)
        try:
            return _try_slot(slot_index, payload, kind, secret)
        except InvalidTag:
            saw_wrong_secret = True
        except CorruptedVaultError as exc:
            last_corrupt = exc
    if saw_wrong_secret:
        raise WrongPasswordError() if kind == "password" else WrongRecoveryKeyError()
    raise last_corrupt or CorruptedVaultError()


def unlock_with_password(vault_path: Path, password: str) -> VaultKeys:
    if not password:
        raise WrongPasswordError("Please enter your password.")
    return _unlock(vault_path, "password", password)


def unlock_with_recovery_key(vault_path: Path, recovery_key: str) -> VaultKeys:
    try:
        secret = parse_recovery_key(recovery_key)
    except InvalidRecoveryKeyFormat as exc:
        raise WrongRecoveryKeyError(str(exc)) from exc
    return _unlock(vault_path, "recovery", secret)


# --------------------------------------------------------------------------- #
# Archive writing (folder -> authenticated stream)
# --------------------------------------------------------------------------- #
def _write_archive(enc: ChunkEncryptor, scan: fm.FolderScan, root_name: str,
                   progress: ProgressCB, cancel: CancelCB | None) -> _Digests:
    digests = _Digests(root=root_name)
    name_b = root_name.encode("utf-8")
    enc.write(TAG_ROOT + _u32(len(name_b)) + name_b)
    for rel in scan.dirs:
        rel_b = rel.encode("utf-8")
        enc.write(TAG_DIR + _u32(len(rel_b)) + rel_b)
        digests.dirs.add(rel)

    total, done = scan.total_bytes, 0
    progress("Encrypting", 0, total)
    for entry in scan.files:
        _check_cancel(cancel)
        rel_b = entry.rel.encode("utf-8")
        enc.write(TAG_FILE + _u32(len(rel_b)) + rel_b + struct.pack(">Qq", entry.size, entry.mtime_ns))
        hasher, remaining = hashlib.sha256(), entry.size
        try:
            with open(entry.abs, "rb") as src:
                while remaining:
                    _check_cancel(cancel)
                    block = src.read(min(_IO_BLOCK, remaining))
                    if not block:
                        raise SourceFolderError(
                            f"“{entry.rel}” changed while it was being locked. "
                            "Close programs that use the folder and try again.")
                    hasher.update(block)
                    enc.write(block)
                    remaining -= len(block)
                    done += len(block)
                    progress("Encrypting", done, total)
                if src.read(1):
                    raise SourceFolderError(
                        f"“{entry.rel}” changed while it was being locked. "
                        "Close programs that use the folder and try again.")
        except PermissionError as exc:
            raise SourceFolderError(
                f"FolderLock cannot read “{entry.rel}”. Close the program using it and try again."
            ) from exc
        digest = hasher.digest()
        enc.write(digest)
        digests.files[entry.rel] = digest
        digests.sizes[entry.rel] = entry.size
        digests.total_bytes += entry.size
    enc.write(TAG_END + struct.pack(">QQQ", len(scan.files), len(scan.dirs), total))
    return digests


# --------------------------------------------------------------------------- #
# Archive reading (authenticated stream -> sink)
# --------------------------------------------------------------------------- #
class _Sink:
    def root(self, name: str) -> None: ...
    def dir(self, rel: str) -> None: ...
    def file_begin(self, rel: str, size: int, mtime_ns: int) -> None: ...
    def file_data(self, block: bytes) -> None: ...
    def file_end(self, rel: str, digest: bytes) -> None: ...
    def close(self) -> None: ...


def _read_text(reader: ChunkDecryptor, limit: int) -> str:
    (length,) = struct.unpack(">I", reader.read(4))
    if length == 0 or length > limit:
        raise CorruptedVaultError()
    try:
        return reader.read(length).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CorruptedVaultError() from exc


def _walk_archive(reader: ChunkDecryptor, sink: _Sink, progress: ProgressCB, phase: str,
                  position: Callable[[], tuple[int, int]], cancel: CancelCB | None) -> None:
    if reader.read(1) != TAG_ROOT:
        raise CorruptedVaultError()
    root = _read_text(reader, 1024)
    fm.validate_component(root)
    sink.root(root)

    seen: set[str] = set()
    files = dirs = total = 0
    while True:
        _check_cancel(cancel)
        tag = reader.read(1)
        if tag == TAG_DIR:
            rel = _read_text(reader, 4096)
            fm.validate_relative_path(rel)
            if rel.casefold() in seen:
                raise CorruptedVaultError()
            seen.add(rel.casefold())
            sink.dir(rel)
            dirs += 1
        elif tag == TAG_FILE:
            rel = _read_text(reader, 4096)
            fm.validate_relative_path(rel)
            if rel.casefold() in seen:
                raise CorruptedVaultError()
            seen.add(rel.casefold())
            size, mtime_ns = struct.unpack(">Qq", reader.read(16))
            sink.file_begin(rel, size, mtime_ns)
            hasher, remaining = hashlib.sha256(), size
            while remaining:
                _check_cancel(cancel)
                block = reader.read(min(_IO_BLOCK, remaining))
                hasher.update(block)
                sink.file_data(block)
                remaining -= len(block)
                done, whole = position()
                progress(phase, done, whole)
            stored = reader.read(32)
            if not km.constant_time_equal(hasher.digest(), stored):
                raise CorruptedVaultError()
            sink.file_end(rel, stored)
            files += 1
            total += size
        elif tag == TAG_END:
            n_files, n_dirs, n_bytes = struct.unpack(">QQQ", reader.read(24))
            if (n_files, n_dirs, n_bytes) != (files, dirs, total):
                raise CorruptedVaultError()
            reader.assert_fully_consumed()
            return
        else:
            raise CorruptedVaultError()


def _stream(vault_path: Path, keys: VaultKeys, sink: _Sink, phase: str,
            progress: ProgressCB, cancel: CancelCB | None) -> None:
    size = vault_path.stat().st_size
    with open(vault_path, "rb") as f:
        reader = ChunkDecryptor(f, BODY_OFFSET, size, keys.data_key, keys.vault_id, keys.chunk_size)
        span = max(size - BODY_OFFSET, 1)
        try:
            _walk_archive(reader, sink, progress, phase,
                          lambda: (min(f.tell() - BODY_OFFSET, span), span), cancel)
        finally:
            sink.close()
    progress(phase, span, span)


def peek_root_name(vault_path: Path, keys: VaultKeys) -> str:
    """Name of the original folder (authenticated), read without decrypting the rest."""
    size = vault_path.stat().st_size
    with open(vault_path, "rb") as f:
        reader = ChunkDecryptor(f, BODY_OFFSET, size, keys.data_key, keys.vault_id, keys.chunk_size)
        if reader.read(1) != TAG_ROOT:
            raise CorruptedVaultError()
        name = _read_text(reader, 1024)
    fm.validate_component(name)
    return name


class _VerifySink(_Sink):
    def __init__(self) -> None:
        self.result = _Digests()

    def root(self, name: str) -> None:
        self.result.root = name

    def dir(self, rel: str) -> None:
        self.result.dirs.add(rel)

    def file_begin(self, rel: str, size: int, mtime_ns: int) -> None:
        self.result.sizes[rel] = size
        self.result.total_bytes += size

    def file_end(self, rel: str, digest: bytes) -> None:
        self.result.files[rel] = digest


def verify_vault(vault_path: Path, keys: VaultKeys, progress: ProgressCB | None = None,
                 cancel: CancelCB | None = None) -> _Digests:
    """Authenticate every chunk and every file hash without writing anything."""
    sink = _VerifySink()
    _stream(vault_path, keys, sink, "Verifying", progress or _noop_progress, cancel)
    return sink.result


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #
def create_vault(source: Path, vault_path: Path, password: str, recovery_key: str, *,
                 kdf: km.KdfParams = km.DEFAULT_KDF, chunk_size: int = CHUNK_SIZE,
                 progress: ProgressCB | None = None, cancel: CancelCB | None = None) -> CreateResult:
    """Encrypt ``source`` into ``vault_path``. The source folder is never modified."""
    progress = progress or _noop_progress
    source, vault_path = Path(source), Path(vault_path)
    recovery_secret = parse_recovery_key(recovery_key)

    if vault_path.exists():
        raise DestinationError("A vault with that name already exists. Nothing was changed.")
    out_dir = vault_path.parent
    if not out_dir.is_dir():
        raise DestinationError("The folder where the vault should be saved does not exist.")
    fm.cleanup_stale_files(out_dir)

    scan = fm.scan_folder(source, exclude={vault_path})
    fm.ensure_free_space(out_dir, scan.total_bytes)

    dek = km.generate_dek()
    vault_id = km.random_bytes(16)
    pw_section, _ = _build_pw_section(dek, vault_id, password, kdf)
    rec_section, _ = _build_rec_section(dek, vault_id, recovery_secret)
    core = {"vault_id": vault_id.hex(), "pw": pw_section, "rec": rec_section,
            "chunk": chunk_size, "created": int(time.time())}
    data_key, mac_key = km.derive_subkeys(dek)
    slot = encode_slot(_make_payload(core, 1, mac_key))

    tmp = vault_path.with_name(f"{vault_path.name}{PARTIAL_MARKER}{km.random_bytes(4).hex()}")
    try:
        try:
            with open(tmp, "xb") as out:
                out.write(encode_preamble())
                out.write(slot)
                out.write(slot)
                enc = ChunkEncryptor(out, data_key, vault_id, chunk_size)
                digests = _write_archive(enc, scan, source.name, progress, cancel)
                enc.finish()
                out.flush()
                os.fsync(out.fileno())
        except PermissionError as exc:
            raise DestinationError() from exc

        # ---- verification: nothing is reported as successful before this passes ----
        _check_cancel(cancel)
        _verify_new_vault(tmp, password, recovery_key, digests, progress, cancel)
        _check_cancel(cancel)
        if vault_path.exists():
            raise DestinationError("A vault with that name already exists. Nothing was changed.")
        os.replace(tmp, vault_path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise

    return CreateResult(
        vault_path,
        VaultStats(source.name, len(scan.files), len(scan.dirs), scan.total_bytes, scan.skipped_links),
        vault_path.stat().st_size,
    )


def _verify_new_vault(tmp: Path, password: str, recovery_key: str, expected: _Digests,
                      progress: ProgressCB, cancel: CancelCB | None) -> None:
    keys = unlock_with_password(tmp, password)              # proves the password works
    unlock_with_recovery_key(tmp, recovery_key)             # proves the recovery key works
    got = verify_vault(tmp, keys, progress, cancel)         # authenticates every byte
    if (got.root != expected.root or got.files != expected.files
            or got.dirs != expected.dirs or got.sizes != expected.sizes):
        raise VerificationError()


# --------------------------------------------------------------------------- #
# Restore (vault -> folder)
# --------------------------------------------------------------------------- #
class _ExtractSink(_Sink):
    def __init__(self, staging: Path) -> None:
        self.staging = staging
        self.root_dir: Path | None = None
        self.digests = _Digests()
        self._fh: BinaryIO | None = None
        self._pending: tuple[Path, int] | None = None

    def root(self, name: str) -> None:
        self.digests.root = name
        self.root_dir = self.staging / name
        self.root_dir.mkdir()

    def dir(self, rel: str) -> None:
        fm.safe_join(self.root_dir, rel).mkdir(parents=True, exist_ok=True)

    def file_begin(self, rel: str, size: int, mtime_ns: int) -> None:
        target = fm.safe_join(self.root_dir, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fh = open(target, "xb")               # exclusive: never overwrite
        except FileExistsError as exc:
            raise CorruptedVaultError() from exc
        self._pending = (target, mtime_ns)
        self.digests.sizes[rel] = size

    def file_data(self, block: bytes) -> None:
        self._fh.write(block)

    def file_end(self, rel: str, digest: bytes) -> None:
        self._fh.close()
        self._fh = None
        target, mtime_ns = self._pending
        try:
            os.utime(target, ns=(mtime_ns, mtime_ns))
        except (OSError, OverflowError, ValueError):
            pass
        self.digests.files[rel] = digest

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def _verify_restored(root_dir: Path, digests: _Digests, progress: ProgressCB,
                     cancel: CancelCB | None) -> None:
    """Re-read what was written to disk and compare with the authenticated hashes."""
    total = sum(digests.sizes.values())
    done = 0
    progress("Checking restored files", 0, total)
    for rel, expected in digests.files.items():
        _check_cancel(cancel)
        target = fm.safe_join(root_dir, rel)
        hasher = hashlib.sha256()
        with open(target, "rb") as fh:
            while block := fh.read(_IO_BLOCK):
                hasher.update(block)
                done += len(block)
                progress("Checking restored files", done, total)
        if not km.constant_time_equal(hasher.digest(), expected) \
                or target.stat().st_size != digests.sizes[rel]:
            raise VerificationError()


def extract_vault(vault_path: Path, keys: VaultKeys, dest_parent: Path,
                  progress: ProgressCB | None = None, cancel: CancelCB | None = None) -> Path:
    """Restore the vault into ``dest_parent/<original name>`` (made unique, never
    overwriting anything). Returns the final folder."""
    progress = progress or _noop_progress
    vault_path, dest_parent = Path(vault_path), Path(dest_parent)
    if not dest_parent.is_dir():
        raise DestinationError("The chosen destination folder does not exist.")
    if not os.access(dest_parent, os.W_OK):
        raise DestinationError("FolderLock cannot save files in the chosen folder. Please pick another.")
    fm.ensure_free_space(dest_parent, vault_path.stat().st_size)
    fm.cleanup_stale_files(dest_parent)

    staging = dest_parent / f"{fm.RESTORE_STAGING_PREFIX}{km.random_bytes(4).hex()}"
    try:
        staging.mkdir()
    except PermissionError as exc:
        raise DestinationError() from exc
    try:
        sink = _ExtractSink(staging)
        _stream(vault_path, keys, sink, "Restoring", progress, cancel)
        _verify_restored(sink.root_dir, sink.digests, progress, cancel)
        _check_cancel(cancel)
        final = unique_path(dest_parent / sink.digests.root, "(restored)") \
            if (dest_parent / sink.digests.root).exists() else dest_parent / sink.digests.root
        os.rename(sink.root_dir, final)
    except BaseException:
        fm.remove_staging(staging)
        raise
    fm.remove_staging(staging)
    return final


# --------------------------------------------------------------------------- #
# Header updates: change password, recover, new recovery key
# --------------------------------------------------------------------------- #
def _rewrite_header(vault_path: Path, keys: VaultKeys, new_core: dict,
                    check_section: str, kek: bytes, aad: bytes) -> None:
    """Crash-safe header update using the two-slot scheme (see vault_format)."""
    generation = keys.generation + 1
    new_slot = encode_slot(_make_payload(new_core, generation, keys.mac_key))
    target = 1 - keys.slot_index
    with open(vault_path, "r+b") as f:
        f.seek(SLOT_OFFSETS[target])
        previous_target = f.read(len(new_slot))
        try:
            f.seek(SLOT_OFFSETS[target])
            f.write(new_slot)
            f.flush()
            os.fsync(f.fileno())
            # --- verify what is really on disk before touching the old slot ---
            fresh = [p for _, p in read_slots(f) if p["generation"] == generation]
            if not fresh:
                raise VerificationError()
            sec = fresh[0]["core"][check_section]
            dek = km.unwrap_key(kek, bytes.fromhex(sec["nonce"]), bytes.fromhex(sec["wrapped"]), aad)
            expected_mac = km.header_mac(keys.mac_key, _mac_message(fresh[0]["core"], generation))
            if dek != keys.dek or not km.constant_time_equal(expected_mac, bytes.fromhex(fresh[0]["mac"])):
                raise VerificationError()
        except BaseException:
            f.seek(SLOT_OFFSETS[target])        # put the previous bytes back; old header untouched
            f.write(previous_target)
            f.flush()
            os.fsync(f.fileno())
            raise
        # New header verified: make the old slot identical so the OLD password stops working.
        f.seek(SLOT_OFFSETS[keys.slot_index])
        f.write(new_slot)
        f.flush()
        os.fsync(f.fileno())


def _set_password(vault_path: Path, keys: VaultKeys, new_password: str,
                  kdf: km.KdfParams) -> None:
    core = dict(keys.core)
    section, kek = _build_pw_section(keys.dek, keys.vault_id, new_password, kdf)
    core["pw"] = section
    _rewrite_header(vault_path, keys, core, "pw", kek,
                    _wrap_aad(b"pw", keys.vault_id, section["kdf"]))


def change_password(vault_path: Path, old_password: str, new_password: str, *,
                    kdf: km.KdfParams = km.DEFAULT_KDF) -> None:
    """Authenticate with the old password, then re-wrap the DEK under a fresh salt."""
    keys = unlock_with_password(vault_path, old_password)
    _set_password(vault_path, keys, new_password, kdf)
    unlock_with_password(vault_path, new_password)           # final proof


def reset_password_with_recovery_key(vault_path: Path, recovery_key: str, new_password: str, *,
                                      kdf: km.KdfParams = km.DEFAULT_KDF) -> None:
    keys = unlock_with_recovery_key(vault_path, recovery_key)
    _set_password(vault_path, keys, new_password, kdf)
    unlock_with_password(vault_path, new_password)


def replace_recovery_key(vault_path: Path, password: str, new_recovery_key: str) -> None:
    """Install a new recovery key; the previous one stops working."""
    keys = unlock_with_password(vault_path, password)
    secret = parse_recovery_key(new_recovery_key)
    core = dict(keys.core)
    section, kek = _build_rec_section(keys.dek, keys.vault_id, secret)
    core["rec"] = section
    _rewrite_header(vault_path, keys, core, "rec", kek, _wrap_aad(b"rec", keys.vault_id, None))
    unlock_with_recovery_key(vault_path, new_recovery_key)
