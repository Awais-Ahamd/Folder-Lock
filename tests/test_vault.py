"""Vault creation/restore, tamper resistance, safe extraction, interruption safety."""
import hashlib
import os
import struct
import time
import tracemalloc

import pytest

from core import folder_manager as fm
from core import vault_manager as vm
from core.vault_format import BODY_OFFSET, PARTIAL_MARKER, SLOT_OFFSETS, SLOT_SIZE, decode_slot
from security import key_manager as km
from security.encryption import ChunkEncryptor
from security.recovery import generate_recovery_key
from tests.conftest import PASSWORD, tree_snapshot
from utils.error_handler import (
    CorruptedVaultError, InsufficientSpaceError, InvalidVaultError, OperationCancelled,
    SourceFolderError, UnsafePathError, UnsupportedVersionError, WrongPasswordError,
)


@pytest.fixture
def vault(tmp_path, sample_folder, fast_kdf, recovery_key):
    path = tmp_path / "vault.flock"
    vm.create_vault(sample_folder, path, PASSWORD, recovery_key, kdf=fast_kdf)
    return path


def restore(vault_path, tmp_path, password=PASSWORD, name="out"):
    keys = vm.unlock_with_password(vault_path, password)
    out = tmp_path / name
    out.mkdir(exist_ok=True)
    return vm.extract_vault(vault_path, keys, out)


# ------------------------------------------------------------------ round trip
def test_roundtrip_preserves_structure_content_and_names(vault, sample_folder, tmp_path):
    restored = restore(vault, tmp_path)
    assert restored.name == sample_folder.name
    assert tree_snapshot(restored) == tree_snapshot(sample_folder)
    assert (restored / "docs" / "nested" / "empty_dir").is_dir()          # empty dirs kept
    assert (restored / "zero.dat").stat().st_size == 0                      # empty files kept
    assert (restored / "docs" / "ünïcode – файл.txt").exists()


def test_modification_times_preserved(vault, tmp_path):
    restored = restore(vault, tmp_path)
    assert (restored / "readme.txt").stat().st_mtime_ns == 1_600_000_000_000_000_000


def test_source_folder_never_modified(tmp_path, sample_folder, fast_kdf, recovery_key):
    before = tree_snapshot(sample_folder)
    vm.create_vault(sample_folder, tmp_path / "v.flock", PASSWORD, recovery_key, kdf=fast_kdf)
    assert tree_snapshot(sample_folder) == before


def test_vault_contains_no_plaintext(vault):
    blob = vault.read_bytes()
    assert b"hello world" not in blob
    assert b"readme.txt" not in blob
    assert b"Private Data" not in blob


def test_two_vaults_of_same_folder_differ(tmp_path, sample_folder, fast_kdf, recovery_key):
    a, b = tmp_path / "a.flock", tmp_path / "b.flock"
    vm.create_vault(sample_folder, a, PASSWORD, recovery_key, kdf=fast_kdf)
    vm.create_vault(sample_folder, b, PASSWORD, recovery_key, kdf=fast_kdf)
    assert a.read_bytes()[BODY_OFFSET:] != b.read_bytes()[BODY_OFFSET:]      # fresh DEK + nonces
    assert a.read_bytes()[:BODY_OFFSET] != b.read_bytes()[:BODY_OFFSET]      # fresh salts


def test_vault_is_portable_after_copy(vault, tmp_path):
    import shutil
    elsewhere = tmp_path / "usb"
    elsewhere.mkdir()
    shutil.copy(vault, elsewhere / "moved.flock")
    assert restore(elsewhere / "moved.flock", tmp_path, name="o2").exists()


def test_restore_never_overwrites_existing_folder(vault, sample_folder, tmp_path):
    out = tmp_path / "dest"
    out.mkdir()
    existing = out / sample_folder.name
    existing.mkdir()
    (existing / "keep.txt").write_text("precious")
    keys = vm.unlock_with_password(vault, PASSWORD)
    restored = vm.extract_vault(vault, keys, out)
    assert restored != existing
    assert (existing / "keep.txt").read_text() == "precious"
    assert (existing.iterdir().__next__()).name == "keep.txt"
    assert len(list(existing.iterdir())) == 1
    assert (restored / "readme.txt").exists()


def test_refuses_to_overwrite_existing_vault(vault, sample_folder, fast_kdf, recovery_key):
    before = vault.read_bytes()
    with pytest.raises(Exception):
        vm.create_vault(sample_folder, vault, PASSWORD, recovery_key, kdf=fast_kdf)
    assert vault.read_bytes() == before


def test_empty_folder_roundtrip(tmp_path, fast_kdf, recovery_key):
    src = tmp_path / "Empty"
    src.mkdir()
    v = tmp_path / "e.flock"
    vm.create_vault(src, v, PASSWORD, recovery_key, kdf=fast_kdf)
    assert restore(v, tmp_path).is_dir()


def test_vault_file_inside_source_is_excluded(tmp_path, sample_folder, fast_kdf, recovery_key):
    v = sample_folder / "inside.flock"
    res = vm.create_vault(sample_folder, v, PASSWORD, recovery_key, kdf=fast_kdf)
    restored = restore(v, tmp_path)
    assert not (restored / "inside.flock").exists()
    assert res.stats.files == 4


# ------------------------------------------------------------------ passwords
def test_wrong_password_message_and_no_output(vault, tmp_path):
    with pytest.raises(WrongPasswordError) as e:
        vm.unlock_with_password(vault, "not the password")
    assert e.value.user_message == "Incorrect password. Your files are still protected."


def test_empty_password_rejected(vault):
    with pytest.raises(WrongPasswordError):
        vm.unlock_with_password(vault, "")


def test_password_change_old_stops_new_works(vault, fast_kdf, tmp_path):
    vm.change_password(vault, PASSWORD, "Another Strong Pass 77!", kdf=fast_kdf)
    with pytest.raises(WrongPasswordError):
        vm.unlock_with_password(vault, PASSWORD)
    assert restore(vault, tmp_path, "Another Strong Pass 77!").exists()


def test_password_change_does_not_touch_encrypted_body(vault, fast_kdf):
    body = vault.read_bytes()[BODY_OFFSET:]
    vm.change_password(vault, PASSWORD, "Another Strong Pass 77!", kdf=fast_kdf)
    assert vault.read_bytes()[BODY_OFFSET:] == body
    assert vault.stat().st_size == len(body) + BODY_OFFSET


def test_password_change_uses_fresh_salt(vault, fast_kdf):
    before = vm.unlock_with_password(vault, PASSWORD).core["pw"]["salt"]
    vm.change_password(vault, PASSWORD, "Another Strong Pass 77!", kdf=fast_kdf)
    after = vm.unlock_with_password(vault, "Another Strong Pass 77!").core["pw"]["salt"]
    assert before != after


def test_failed_password_change_leaves_vault_intact(vault, fast_kdf):
    snapshot = vault.read_bytes()
    with pytest.raises(WrongPasswordError):
        vm.change_password(vault, "wrong old password", "Another Strong Pass 77!", kdf=fast_kdf)
    assert vault.read_bytes() == snapshot
    vm.unlock_with_password(vault, PASSWORD)


def test_crash_after_new_slot_written_still_opens(vault, fast_kdf):
    """Interrupted password change: new slot written, old slot not yet mirrored."""
    keys = vm.unlock_with_password(vault, PASSWORD)
    core = dict(keys.core)
    section, _ = vm._build_pw_section(keys.dek, keys.vault_id, "Another Strong Pass 77!", fast_kdf)
    core["pw"] = section
    slot = vm.encode_slot(vm._make_payload(core, keys.generation + 1, keys.mac_key))
    with open(vault, "r+b") as f:
        f.seek(SLOT_OFFSETS[1 - keys.slot_index])
        f.write(slot)
    # Both the new and the previous password open the vault; nothing is lost.
    vm.unlock_with_password(vault, "Another Strong Pass 77!")
    vm.unlock_with_password(vault, PASSWORD)


def test_torn_header_slot_falls_back_to_good_slot(vault):
    with open(vault, "r+b") as f:                    # simulate a half-written slot A
        f.seek(SLOT_OFFSETS[0] + 100)
        f.write(os.urandom(500))
    vm.unlock_with_password(vault, PASSWORD)


# ------------------------------------------------------------------ tamper / corruption
def flip(path, offset):
    data = bytearray(path.read_bytes())
    data[offset] ^= 0x01
    path.write_bytes(bytes(data))


def test_any_body_bit_flip_is_detected(vault, tmp_path):
    size = vault.stat().st_size
    for offset in (BODY_OFFSET + 2, BODY_OFFSET + 5, BODY_OFFSET + 4000, size // 2, size - 1, size - 20):
        copy = tmp_path / f"c{offset}.flock"
        copy.write_bytes(vault.read_bytes())
        flip(copy, offset)
        keys = vm.unlock_with_password(copy, PASSWORD)
        out = tmp_path / f"o{offset}"
        out.mkdir()
        with pytest.raises(CorruptedVaultError):
            vm.extract_vault(copy, keys, out)
        assert list(out.iterdir()) == []                        # nothing exposed, staging removed


def test_header_tamper_is_detected(vault):
    """Flipping bytes inside both header slots can never yield a silently-modified header."""
    for slot_off in SLOT_OFFSETS:
        for delta in (10, 60, 200, 400):
            data = bytearray(vault.read_bytes())
            data[slot_off + delta] ^= 0xFF
            vault.write_bytes(bytes(data))
    with pytest.raises((CorruptedVaultError, WrongPasswordError)):
        vm.unlock_with_password(vault, PASSWORD)


def test_header_mac_rejects_valid_checksum_but_edited_fields(vault):
    """An attacker who recomputes the (unkeyed) slot checksum still cannot alter the header."""
    keys = vm.unlock_with_password(vault, PASSWORD)
    for slot_index in (0, 1):
        raw = vault.read_bytes()[SLOT_OFFSETS[slot_index]:SLOT_OFFSETS[slot_index] + SLOT_SIZE]
        payload = decode_slot(raw)
        payload["core"]["chunk"] = 65536                     # tampered parameter
        data = bytearray(vault.read_bytes())
        data[SLOT_OFFSETS[slot_index]:SLOT_OFFSETS[slot_index] + SLOT_SIZE] = vm.encode_slot(payload)
        vault.write_bytes(bytes(data))
    with pytest.raises(CorruptedVaultError):
        vm.unlock_with_password(vault, PASSWORD)


def test_truncated_vault_rejected(vault, tmp_path):
    size = vault.stat().st_size
    for cut in (size - 1, size - 100, size // 2, BODY_OFFSET + 30):
        copy = tmp_path / f"t{cut}.flock"
        copy.write_bytes(vault.read_bytes()[:cut])
        keys = vm.unlock_with_password(copy, PASSWORD)
        out = tmp_path / f"to{cut}"
        out.mkdir()
        with pytest.raises(CorruptedVaultError):
            vm.extract_vault(copy, keys, out)
        assert list(out.iterdir()) == []


def test_header_only_file_rejected(vault, tmp_path):
    copy = tmp_path / "h.flock"
    copy.write_bytes(vault.read_bytes()[:BODY_OFFSET])
    with pytest.raises(InvalidVaultError):
        vm.unlock_with_password(copy, PASSWORD)


def test_appended_garbage_rejected(vault, tmp_path):
    with open(vault, "ab") as f:
        f.write(os.urandom(64))
    keys = vm.unlock_with_password(vault, PASSWORD)
    out = tmp_path / "o"
    out.mkdir()
    with pytest.raises(CorruptedVaultError):
        vm.extract_vault(vault, keys, out)


def test_random_file_is_not_a_vault(tmp_path):
    junk = tmp_path / "junk.flock"
    junk.write_bytes(os.urandom(100_000))
    with pytest.raises(InvalidVaultError):
        vm.inspect_vault(junk)
    text = tmp_path / "notes.flock"
    text.write_text("just some text")
    with pytest.raises(InvalidVaultError):
        vm.inspect_vault(text)


def test_missing_vault_file(tmp_path):
    with pytest.raises(InvalidVaultError):
        vm.inspect_vault(tmp_path / "nope.flock")


def test_newer_format_version_rejected(vault):
    data = bytearray(vault.read_bytes())
    data[8:10] = struct.pack(">H", 99)
    vault.write_bytes(bytes(data))
    with pytest.raises(UnsupportedVersionError):
        vm.inspect_vault(vault)


# ------------------------------------------------------------------ path traversal
def forge_vault(path, entries, password, fast_kdf, root="Evil"):
    """Build a *validly authenticated* vault containing arbitrary entry paths."""
    dek, vid = km.generate_dek(), km.random_bytes(16)
    pw, _ = vm._build_pw_section(dek, vid, password, fast_kdf)
    rec, _ = vm._build_rec_section(dek, vid, km.random_bytes(32))
    core = {"vault_id": vid.hex(), "pw": pw, "rec": rec, "chunk": 65536, "created": 0}
    data_key, mac_key = km.derive_subkeys(dek)
    slot = vm.encode_slot(vm._make_payload(core, 1, mac_key))
    with open(path, "wb") as f:
        f.write(vm.encode_preamble() + slot + slot)
        enc = ChunkEncryptor(f, data_key, vid, 65536)
        rb = root.encode()
        enc.write(b"R" + struct.pack(">I", len(rb)) + rb)
        files = 0
        for rel, content in entries:
            rb2 = rel.encode()
            enc.write(b"F" + struct.pack(">I", len(rb2)) + rb2 + struct.pack(">Qq", len(content), 0))
            enc.write(content + hashlib.sha256(content).digest())
            files += 1
        enc.write(b"E" + struct.pack(">QQQ", files, 0, sum(len(c) for _, c in entries)))
        enc.finish()


@pytest.mark.parametrize("evil", [
    "../escape.txt", "a/../../escape.txt", "/etc/escape.txt", "C:/Windows/escape.txt",
    "..\\escape.txt", "a\\..\\escape.txt", "./x.txt", "a//b.txt", "CON", "aux.txt",
    "trailing.", "bad\x01name", "x/", "", "a/b:stream",
])
def test_path_traversal_and_unsafe_names_rejected(tmp_path, fast_kdf, evil):
    v = tmp_path / "evil.flock"
    forge_vault(v, [(evil, b"pwned")], PASSWORD, fast_kdf)
    out = tmp_path / "dest"
    out.mkdir()
    keys = vm.unlock_with_password(v, PASSWORD)
    with pytest.raises((UnsafePathError, CorruptedVaultError)):
        vm.extract_vault(v, keys, out)
    assert list(out.iterdir()) == []
    assert not (tmp_path / "escape.txt").exists()
    assert not list(tmp_path.glob("**/escape.txt"))


def test_unsafe_root_name_rejected(tmp_path, fast_kdf):
    v = tmp_path / "evil.flock"
    forge_vault(v, [("ok.txt", b"x")], PASSWORD, fast_kdf, root="../Outside")
    out = tmp_path / "dest"
    out.mkdir()
    with pytest.raises(UnsafePathError):
        vm.extract_vault(v, vm.unlock_with_password(v, PASSWORD), out)


def test_duplicate_entries_rejected(tmp_path, fast_kdf):
    v = tmp_path / "dup.flock"
    forge_vault(v, [("a.txt", b"1"), ("A.TXT", b"2")], PASSWORD, fast_kdf)
    out = tmp_path / "dest"
    out.mkdir()
    with pytest.raises(CorruptedVaultError):
        vm.extract_vault(v, vm.unlock_with_password(v, PASSWORD), out)
    assert list(out.iterdir()) == []


def test_safe_join_blocks_escape(tmp_path):
    for bad in ("../x", "a/../../x", "/abs", "a/./b"):
        with pytest.raises(UnsafePathError):
            fm.safe_join(tmp_path, bad)
    assert fm.safe_join(tmp_path, "a/b/c.txt") == tmp_path / "a" / "b" / "c.txt"


# ------------------------------------------------------------------ interruption / cancel
def test_cancel_during_encryption_leaves_nothing_behind(tmp_path, sample_folder, fast_kdf, recovery_key):
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 3

    target = tmp_path / "c.flock"
    before = tree_snapshot(sample_folder)
    with pytest.raises(OperationCancelled):
        vm.create_vault(sample_folder, target, PASSWORD, recovery_key, kdf=fast_kdf, cancel=cancel)
    assert not target.exists()
    assert not [p for p in tmp_path.iterdir() if PARTIAL_MARKER in p.name]
    assert tree_snapshot(sample_folder) == before


def test_cancel_during_restore_leaves_nothing_behind(vault, tmp_path):
    keys = vm.unlock_with_password(vault, PASSWORD)
    out = tmp_path / "o"
    out.mkdir()
    n = {"i": 0}

    def cancel():
        n["i"] += 1
        return n["i"] > 4

    with pytest.raises(OperationCancelled):
        vm.extract_vault(vault, keys, out, cancel=cancel)
    assert list(out.iterdir()) == []


def test_crash_leftovers_are_cleaned_and_never_confused_with_vaults(tmp_path, sample_folder, fast_kdf, recovery_key):
    stale = tmp_path / f"old.flock{PARTIAL_MARKER}deadbeef"
    stale.write_bytes(b"half written")
    stale_dir = tmp_path / f"{fm.RESTORE_STAGING_PREFIX}cafebabe"
    (stale_dir / "X").mkdir(parents=True)
    keep = tmp_path / "important.txt"
    keep.write_text("mine")
    vm.create_vault(sample_folder, tmp_path / "new.flock", PASSWORD, recovery_key, kdf=fast_kdf)
    assert not stale.exists() and not stale_dir.exists()
    assert keep.read_text() == "mine"


def test_failed_encryption_leaves_source_and_no_vault(tmp_path, sample_folder, fast_kdf, recovery_key, monkeypatch):
    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(vm.os, "fsync", boom)
    target = tmp_path / "f.flock"
    with pytest.raises(OSError):
        vm.create_vault(sample_folder, target, PASSWORD, recovery_key, kdf=fast_kdf)
    assert not target.exists()
    assert not [p for p in tmp_path.iterdir() if PARTIAL_MARKER in p.name]
    assert (sample_folder / "readme.txt").exists()


def test_failed_verification_blocks_vault_creation(tmp_path, sample_folder, fast_kdf, recovery_key, monkeypatch):
    def bad_verify(*a, **k):
        raise vm.VerificationError()
    monkeypatch.setattr(vm, "_verify_new_vault", bad_verify)
    target = tmp_path / "v.flock"
    with pytest.raises(vm.VerificationError):
        vm.create_vault(sample_folder, target, PASSWORD, recovery_key, kdf=fast_kdf)
    assert not target.exists()


def test_insufficient_space_detected(tmp_path, sample_folder, fast_kdf, recovery_key, monkeypatch):
    import collections
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(fm.shutil, "disk_usage", lambda p: usage(100, 100, 10))
    with pytest.raises(InsufficientSpaceError):
        vm.create_vault(sample_folder, tmp_path / "v.flock", PASSWORD, recovery_key, kdf=fast_kdf)
    assert not (tmp_path / "v.flock").exists()


def test_source_file_changing_during_lock_is_reported(tmp_path, sample_folder, fast_kdf, recovery_key):
    big = sample_folder / "docs" / "nested" / "data.bin"
    seen = {"done": False}

    def progress(phase, done, total):
        if phase == "Encrypting" and done > 0 and not seen["done"]:
            seen["done"] = True
            with open(big, "ab") as f:
                f.write(b"growing")
    with pytest.raises(SourceFolderError):
        vm.create_vault(sample_folder, tmp_path / "v.flock", PASSWORD, recovery_key,
                        kdf=fast_kdf, progress=progress)
    assert not (tmp_path / "v.flock").exists()


# ------------------------------------------------------------------ source handling
def test_symlinks_are_not_followed(tmp_path, fast_kdf, recovery_key):
    src = tmp_path / "S"
    src.mkdir()
    secret_outside = tmp_path / "outside.txt"
    secret_outside.write_text("outside data")
    (src / "real.txt").write_text("real")
    try:
        os.symlink(secret_outside, src / "link.txt")
        os.symlink(tmp_path, src / "dirlink")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    res = vm.create_vault(src, tmp_path / "s.flock", PASSWORD, recovery_key, kdf=fast_kdf)
    assert res.stats.skipped_links == 2
    restored = restore(tmp_path / "s.flock", tmp_path)
    assert sorted(p.name for p in restored.iterdir()) == ["real.txt"]


def test_missing_and_invalid_source_folders(tmp_path, fast_kdf, recovery_key):
    with pytest.raises(SourceFolderError):
        vm.create_vault(tmp_path / "missing", tmp_path / "v.flock", PASSWORD, recovery_key, kdf=fast_kdf)
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(SourceFolderError):
        vm.create_vault(f, tmp_path / "v.flock", PASSWORD, recovery_key, kdf=fast_kdf)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="permission bits not enforced")
def test_unreadable_folder_gives_friendly_error(tmp_path, fast_kdf, recovery_key):
    src = tmp_path / "locked"
    src.mkdir()
    (src / "f.txt").write_text("x")
    src.chmod(0)
    try:
        with pytest.raises(SourceFolderError):
            vm.create_vault(src, tmp_path / "v.flock", PASSWORD, recovery_key, kdf=fast_kdf)
    finally:
        src.chmod(0o755)


def test_remove_original_folder(tmp_path, sample_folder):
    fm.remove_folder(sample_folder)
    assert not sample_folder.exists()


# ------------------------------------------------------------------ large data / memory
def test_large_file_streams_with_low_memory(tmp_path, fast_kdf, recovery_key):
    src = tmp_path / "Big"
    src.mkdir()
    block = os.urandom(1024 * 1024)
    with open(src / "big.bin", "wb") as f:
        for _ in range(120):                         # 120 MiB
            f.write(block)
    v = tmp_path / "big.flock"
    tracemalloc.start()
    vm.create_vault(src, v, PASSWORD, recovery_key, kdf=fast_kdf)
    keys = vm.unlock_with_password(v, PASSWORD)
    out = tmp_path / "o"
    out.mkdir()
    restored = vm.extract_vault(v, keys, out)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 40 * 1024 * 1024, f"peak {peak / 1e6:.0f} MB - data is not being streamed"
    assert hashlib.sha256((restored / "big.bin").read_bytes()).digest() == \
        hashlib.sha256(block * 120).digest()


def test_progress_reaches_completion(tmp_path, sample_folder, fast_kdf, recovery_key):
    events = []
    vm.create_vault(sample_folder, tmp_path / "p.flock", PASSWORD, recovery_key, kdf=fast_kdf,
                    progress=lambda p, d, t: events.append((p, d, t)))
    phases = [e[0] for e in events]
    assert "Encrypting" in phases and "Verifying" in phases
    for phase in ("Encrypting", "Verifying"):
        last = [e for e in events if e[0] == phase][-1]
        assert last[1] == last[2]
