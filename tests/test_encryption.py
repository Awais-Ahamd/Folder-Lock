"""Chunked AES-256-GCM stream: confidentiality, ordering, truncation, tampering."""
import io
import os
import struct

import pytest

from security import key_manager as km
from security.encryption import ChunkDecryptor, ChunkEncryptor
from utils.error_handler import CorruptedVaultError

CHUNK = 1024
VID = b"V" * 16
KEY = b"K" * 32


def seal(data: bytes, key=KEY, vid=VID, chunk=CHUNK) -> bytes:
    buf = io.BytesIO()
    enc = ChunkEncryptor(buf, key, vid, chunk)
    # feed in awkward pieces to exercise buffering
    for i in range(0, len(data), 333):
        enc.write(data[i:i + 333])
    enc.finish()
    return buf.getvalue()


def opener(blob: bytes, key=KEY, vid=VID, chunk=CHUNK, prefix=b""):
    f = io.BytesIO(prefix + blob)
    return ChunkDecryptor(f, len(prefix), len(prefix) + len(blob), key, vid, chunk)


def frames(blob: bytes):
    pos, out = 0, []
    while pos < len(blob):
        (n,) = struct.unpack(">I", blob[pos:pos + 4])
        out.append(blob[pos:pos + 4 + n])
        pos += 4 + n
    return out


@pytest.mark.parametrize("size", [0, 1, 1023, 1024, 1025, 2048, 5000])
def test_roundtrip_various_sizes(size):
    data = os.urandom(size)
    r = opener(seal(data))
    assert r.read(size) == data
    r.assert_fully_consumed()


def test_ciphertext_hides_plaintext():
    data = b"SECRET-MARKER-" * 500
    assert b"SECRET-MARKER" not in seal(data)


def test_same_plaintext_never_produces_same_ciphertext_chunks():
    blob = seal(b"A" * 4096)       # four identical plaintext chunks (+ final)
    bodies = [f[4:] for f in frames(blob)]
    assert len(set(bodies)) == len(bodies)          # unique nonces => unique ciphertexts


def test_wrong_key_rejected():
    with pytest.raises(CorruptedVaultError):
        opener(seal(b"x" * 100), key=b"Z" * 32).read(100)


def test_wrong_vault_id_rejected():
    with pytest.raises(CorruptedVaultError):
        opener(seal(b"x" * 100), vid=b"W" * 16).read(100)


def test_bit_flip_detected():
    blob = bytearray(seal(os.urandom(3000)))
    blob[40] ^= 1
    with pytest.raises(CorruptedVaultError):
        r = opener(bytes(blob))
        r.read(3000)


def test_truncation_at_chunk_boundary_detected():
    data = os.urandom(5000)
    fr = frames(seal(data))
    truncated = b"".join(fr[:-1])                    # drop the final chunk
    r = opener(truncated)
    with pytest.raises(CorruptedVaultError):
        r.read(5000)


def test_truncation_mid_chunk_detected():
    blob = seal(os.urandom(5000))
    with pytest.raises(CorruptedVaultError):
        opener(blob[:-10]).read(5000)


def test_chunk_reordering_detected():
    fr = frames(seal(os.urandom(4000)))
    swapped = fr[1] + fr[0] + b"".join(fr[2:])
    with pytest.raises(CorruptedVaultError):
        opener(swapped).read(4000)


def test_chunk_duplication_detected():
    fr = frames(seal(os.urandom(4000)))
    dup = fr[0] + fr[0] + b"".join(fr[1:])
    with pytest.raises(CorruptedVaultError):
        opener(dup).read(4000)


def test_appended_data_detected():
    blob = seal(b"hello" * 10)
    r = opener(blob + b"\x00\x00\x00\x20" + os.urandom(32))
    with pytest.raises(CorruptedVaultError):
        r.read(50)


def test_unconsumed_trailing_plaintext_detected():
    r = opener(seal(b"hello world"))
    r.read(5)
    with pytest.raises(CorruptedVaultError):
        r.assert_fully_consumed()


def test_reading_past_end_detected():
    r = opener(seal(b"abc"))
    with pytest.raises(CorruptedVaultError):
        r.read(10)


def test_hostile_length_field_rejected_without_allocating():
    blob = struct.pack(">I", 0xFFFFFFF0) + b"x" * 40
    with pytest.raises(CorruptedVaultError):
        opener(blob).read(1)


def test_offset_prefix_supported():
    data = os.urandom(2500)
    r = opener(seal(data), prefix=b"HEADER" * 10)
    assert r.read(2500) == data


# ---- key management ----
def test_argon2id_deterministic_and_salt_sensitive():
    p = km.KdfParams(1, 64, 1)
    salt = b"s" * 16
    k1 = km.derive_password_kek("pw", salt, p)
    assert k1 == km.derive_password_kek("pw", salt, p)
    assert k1 != km.derive_password_kek("pw", b"t" * 16, p)
    assert k1 != km.derive_password_kek("pW", salt, p)
    assert len(k1) == 32


def test_password_unicode_normalisation():
    p = km.KdfParams(1, 64, 1)
    salt = b"s" * 16
    composed, decomposed = "café-password", "café-password"
    assert km.derive_password_kek(composed, salt, p) == km.derive_password_kek(decomposed, salt, p)


def test_kdf_params_bounds_enforced():
    for bad in (km.KdfParams(0, 64, 1), km.KdfParams(1, 10 ** 9, 1), km.KdfParams(1, 64, 999)):
        with pytest.raises(ValueError):
            bad.validate()


def test_default_kdf_is_strong():
    assert km.DEFAULT_KDF.memory_kib >= 256 * 1024
    assert km.DEFAULT_KDF.time_cost >= 3


def test_subkeys_are_independent():
    a, b = km.derive_subkeys(b"D" * 32)
    assert a != b and a != b"D" * 32 and b != b"D" * 32
