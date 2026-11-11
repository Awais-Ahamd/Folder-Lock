"""The .flock vault file format (version 1).

::

    offset 0       preamble (16 bytes)
                     8  magic        b"FLOCKVLT"
                     2  version      uint16 big-endian (currently 1)
                     2  flags        reserved (0)
                     4  reserved     (0)
    offset 16      header slot A  (8192 bytes)
    offset 8208    header slot B  (8192 bytes)
    offset 16400   body: sequence of AES-256-GCM chunks (see security/encryption.py)

Header slot::

    uint32 payload_length | payload (canonical JSON) | SHA-256(length||payload) | zero padding

The payload is ``{"generation": n, "core": {...}, "mac": hex}``. ``core`` holds
the vault id, Argon2id parameters, salts, and the DEK wrapped twice (password
and recovery key). ``mac`` is an HMAC-SHA-256 (keyed by a sub-key of the DEK)
over the canonical ``core`` and generation, so any tampering is detected once
the DEK is unwrapped.

Two slots make header updates (password change) crash-safe: the new header is
written to the *inactive* slot and verified before the old slot is replaced.
The highest-generation slot whose checksum is intact is the active one.

Plaintext stream inside the chunks (all integers big-endian)::

    'R' u32 name_len name                      root folder name
    'D' u32 path_len path                      directory (POSIX-style relative path)
    'F' u32 path_len path u64 size i64 mtime_ns  <size bytes>  <32-byte SHA-256>
    'E' u64 file_count u64 dir_count u64 total_bytes   end marker

Versioning: ``FORMAT_VERSION`` is bumped for incompatible changes. Newer
versions are refused with a clear message, never guessed at.
"""
from __future__ import annotations

import hashlib
import json
import struct
from typing import BinaryIO

from utils.error_handler import InvalidVaultError, UnsupportedVersionError

MAGIC = b"FLOCKVLT"
FORMAT_VERSION = 1
PREAMBLE_SIZE = 16
SLOT_SIZE = 8192
SLOT_OFFSETS = (PREAMBLE_SIZE, PREAMBLE_SIZE + SLOT_SIZE)
BODY_OFFSET = PREAMBLE_SIZE + 2 * SLOT_SIZE
VAULT_EXTENSION = ".flock"
PARTIAL_MARKER = ".flock.partial-"

# Plaintext stream record tags
TAG_ROOT, TAG_DIR, TAG_FILE, TAG_END = b"R", b"D", b"F", b"E"


def canonical(obj: object) -> bytes:
    """Deterministic JSON encoding used for MAC and AAD inputs."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def encode_preamble() -> bytes:
    return MAGIC + struct.pack(">HHI", FORMAT_VERSION, 0, 0)


def check_preamble(raw: bytes) -> int:
    if len(raw) != PREAMBLE_SIZE or raw[:8] != MAGIC:
        raise InvalidVaultError()
    (version,) = struct.unpack(">H", raw[8:10])
    if version > FORMAT_VERSION:
        raise UnsupportedVersionError()
    if version < 1:
        raise InvalidVaultError()
    return version


def encode_slot(payload: dict) -> bytes:
    raw = canonical(payload)
    body = struct.pack(">I", len(raw)) + raw
    blob = body + hashlib.sha256(body).digest()
    if len(blob) > SLOT_SIZE:
        raise ValueError("header too large")
    return blob + b"\x00" * (SLOT_SIZE - len(blob))


def decode_slot(raw: bytes) -> dict | None:
    """Return the payload dict, or ``None`` if the slot is empty/torn/damaged."""
    if len(raw) != SLOT_SIZE:
        return None
    (length,) = struct.unpack(">I", raw[:4])
    if length == 0 or length > SLOT_SIZE - 36:
        return None
    body, digest = raw[:4 + length], raw[4 + length:4 + length + 32]
    if hashlib.sha256(body).digest() != digest:
        return None
    try:
        payload = json.loads(body[4:])
    except ValueError:
        return None
    if not isinstance(payload, dict) or "core" not in payload or "mac" not in payload \
            or not isinstance(payload.get("generation"), int):
        return None
    return payload


def read_slots(f: BinaryIO) -> list[tuple[int, dict]]:
    """Read both slots; return ``[(slot_index, payload), ...]`` for the intact ones."""
    found = []
    for index, offset in enumerate(SLOT_OFFSETS):
        f.seek(offset)
        payload = decode_slot(f.read(SLOT_SIZE))
        if payload is not None:
            found.append((index, payload))
    return found
