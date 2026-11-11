"""Recovery key generation and parsing.

A recovery key is 256 random bits shown as 13 groups of 4 base-32 characters
plus a 4-character checksum group, e.g.::

    ABCD-EFGH-...-WXYZ-K7QD

The checksum only catches typing mistakes; it adds no security. The key itself
is never stored in the vault - only a copy of the DEK wrapped by a key derived
from it.
"""
from __future__ import annotations

import base64
import hashlib

from security.key_manager import random_bytes

RECOVERY_BYTES = 32
_CONFUSABLE = str.maketrans({"0": "O", "1": "I", "8": "B"})


class InvalidRecoveryKeyFormat(ValueError):
    """The text is not shaped like a recovery key (typo / incomplete)."""


def _checksum(secret: bytes) -> str:
    return base64.b32encode(hashlib.sha256(b"FLRK" + secret).digest()[:3]).decode()[:4]


def generate_recovery_key() -> str:
    secret = random_bytes(RECOVERY_BYTES)
    body = base64.b32encode(secret).decode().rstrip("=")       # 52 chars
    groups = [body[i:i + 4] for i in range(0, len(body), 4)]
    groups.append(_checksum(secret))
    return "-".join(groups)


def parse_recovery_key(text: str) -> bytes:
    """Return the 32 secret bytes, or raise :class:`InvalidRecoveryKeyFormat`."""
    cleaned = "".join(ch for ch in text.upper() if ch.isalnum()).translate(_CONFUSABLE)
    if len(cleaned) != 56:
        raise InvalidRecoveryKeyFormat("The recovery key should have 14 groups of 4 characters.")
    body, check = cleaned[:52], cleaned[52:]
    try:
        secret = base64.b32decode(body + "====")
    except Exception as exc:  # noqa: BLE001
        raise InvalidRecoveryKeyFormat("The recovery key contains invalid characters.") from exc
    if len(secret) != RECOVERY_BYTES or check != _checksum(secret):
        raise InvalidRecoveryKeyFormat(
            "The recovery key has a typing mistake. Please check each group of characters."
        )
    return secret


def recovery_file_text(key: str, vault_name: str) -> str:
    """Printable text for 'Save recovery key' / 'Print'."""
    return (
        "FOLDERLOCK RECOVERY KEY\n"
        "=======================\n\n"
        f"Vault: {vault_name}\n\n"
        f"Recovery key:\n\n    {key}\n\n"
        "Keep this paper or file somewhere SAFE and PRIVATE (not next to the vault).\n"
        "Anyone who has this key can open the vault.\n"
        "If you lose BOTH your password and this key, your files can NEVER be recovered.\n"
    )
