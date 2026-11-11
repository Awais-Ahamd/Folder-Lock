"""Key management: Argon2id derivation, AES-256-GCM key wrapping, sub-keys.

Key architecture
----------------
* A random 256-bit **data-encryption key (DEK)** is generated per vault.
* The user's password is turned into a **key-encryption key (KEK)** with
  Argon2id (memory-hard, fresh random salt per vault / per password change).
* The DEK is stored only in *wrapped* (AES-256-GCM encrypted) form, once under
  the password KEK and once under the recovery-key KEK.
* From the DEK two independent sub-keys are derived with HKDF-SHA256:
  one for encrypting data chunks, one for authenticating the header (HMAC).

Changing the password therefore only re-wraps the DEK; files are not
re-encrypted.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import unicodedata
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

KEY_SIZE = 32          # AES-256
SALT_SIZE = 16
NONCE_SIZE = 12


@dataclass(frozen=True)
class KdfParams:
    """Argon2id cost parameters. Stored in each vault header."""

    time_cost: int = 3
    memory_kib: int = 256 * 1024     # 256 MiB
    parallelism: int = 4

    # Upper bounds protect against hostile vault files that would exhaust memory.
    MAX_TIME = 20
    MAX_MEMORY_KIB = 1024 * 1024     # 1 GiB
    MAX_PARALLELISM = 16

    def validate(self) -> "KdfParams":
        if not (1 <= self.time_cost <= self.MAX_TIME
                and 8 <= self.memory_kib <= self.MAX_MEMORY_KIB
                and 1 <= self.parallelism <= self.MAX_PARALLELISM):
            raise ValueError("KDF parameters out of range")
        return self

    def to_dict(self) -> dict:
        return {"alg": "argon2id", "t": self.time_cost,
                "m": self.memory_kib, "p": self.parallelism}

    @classmethod
    def from_dict(cls, d: dict) -> "KdfParams":
        if d.get("alg") != "argon2id":
            raise ValueError("unsupported KDF")
        return cls(int(d["t"]), int(d["m"]), int(d["p"])).validate()


DEFAULT_KDF = KdfParams()


def random_bytes(n: int) -> bytes:
    """Cryptographically secure random bytes (OS CSPRNG)."""
    return os.urandom(n)


def normalize_password(password: str) -> bytes:
    """Unicode-normalise (NFKC) so the same typed password works on every PC."""
    return unicodedata.normalize("NFKC", password).encode("utf-8")


def derive_password_kek(password: str, salt: bytes, params: KdfParams) -> bytes:
    """Argon2id(password, salt) -> 32-byte key-encryption key."""
    params.validate()
    return hash_secret_raw(
        secret=normalize_password(password),
        salt=salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_kib,
        parallelism=params.parallelism,
        hash_len=KEY_SIZE,
        type=Type.ID,
    )


def derive_recovery_kek(recovery_secret: bytes, salt: bytes) -> bytes:
    """The recovery key is 256 random bits, so HKDF is sufficient (no stretching needed)."""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_SIZE, salt=salt,
                info=b"FolderLock recovery KEK v1").derive(recovery_secret)


def generate_dek() -> bytes:
    return random_bytes(KEY_SIZE)


def wrap_key(kek: bytes, dek: bytes, aad: bytes) -> tuple[bytes, bytes]:
    """Encrypt (wrap) the DEK. Returns (nonce, ciphertext+tag)."""
    nonce = random_bytes(NONCE_SIZE)
    return nonce, AESGCM(kek).encrypt(nonce, dek, aad)


def unwrap_key(kek: bytes, nonce: bytes, wrapped: bytes, aad: bytes) -> bytes:
    """Decrypt the DEK. Raises ``cryptography.exceptions.InvalidTag`` if the KEK is wrong."""
    return AESGCM(kek).decrypt(nonce, wrapped, aad)


def derive_subkeys(dek: bytes) -> tuple[bytes, bytes]:
    """Return (data_key, header_mac_key), cryptographically independent."""
    def _one(info: bytes) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=KEY_SIZE, salt=None, info=info).derive(dek)

    return _one(b"FolderLock data key v1"), _one(b"FolderLock header MAC key v1")


def header_mac(mac_key: bytes, message: bytes) -> bytes:
    return hmac.new(mac_key, b"FolderLock header v1|" + message, hashlib.sha256).digest()


def constant_time_equal(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)
