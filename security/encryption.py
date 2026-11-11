"""Chunked authenticated encryption (AES-256-GCM) for large data streams.

Design
------
The whole folder is serialised into one logical byte stream which is cut into
chunks (default 1 MiB). Each chunk is sealed with AES-256-GCM:

* **Nonce** = 96-bit big-endian chunk counter. The data key is unique per
  vault and the counter never repeats, so a (key, nonce) pair is never reused.
* **AAD** = vault_id || counter || final-flag. This authenticates the chunk's
  position (reordering / duplication / dropping fails) and which chunk is the
  last one (truncation and appended data fail).
* On disk a chunk is ``uint32 ciphertext_length || ciphertext+tag``.

Nothing is decrypted into a file until its chunk has been authenticated, and
only the current chunk is ever held in memory.
"""
from __future__ import annotations

import struct
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from utils.error_handler import CorruptedVaultError

CHUNK_SIZE = 1024 * 1024
TAG_SIZE = 16
_MAX_COUNTER = 2 ** 48          # far below the 2**96 nonce space; keeps nonces unique


def _nonce(counter: int) -> bytes:
    return counter.to_bytes(12, "big")


def _aad(vault_id: bytes, counter: int, final: bool) -> bytes:
    return vault_id + counter.to_bytes(8, "big") + (b"\x01" if final else b"\x00")


class ChunkEncryptor:
    """File-like writer: ``write()`` plaintext, ``finish()`` seals the last chunk."""

    def __init__(self, out: BinaryIO, data_key: bytes, vault_id: bytes,
                 chunk_size: int = CHUNK_SIZE):
        self._out = out
        self._aes = AESGCM(data_key)
        self._vault_id = vault_id
        self._chunk_size = chunk_size
        self._buf = bytearray()
        self._counter = 0
        self._finished = False

    def write(self, data: bytes) -> None:
        if self._finished:
            raise ValueError("stream already finished")
        self._buf += data
        # Keep > chunk_size buffered so the final chunk is always still pending.
        while len(self._buf) > self._chunk_size:
            self._seal(bytes(self._buf[:self._chunk_size]), final=False)
            del self._buf[:self._chunk_size]

    def finish(self) -> None:
        if self._finished:
            return
        self._seal(bytes(self._buf), final=True)
        self._buf.clear()
        self._finished = True

    def _seal(self, plaintext: bytes, final: bool) -> None:
        if self._counter >= _MAX_COUNTER:
            raise ValueError("chunk counter exhausted")
        ct = self._aes.encrypt(_nonce(self._counter), plaintext,
                               _aad(self._vault_id, self._counter, final))
        self._out.write(struct.pack(">I", len(ct)))
        self._out.write(ct)
        self._counter += 1


class ChunkDecryptor:
    """Reads and authenticates chunks from ``start`` to ``end`` of an open file."""

    def __init__(self, src: BinaryIO, start: int, end: int, data_key: bytes,
                 vault_id: bytes, chunk_size: int = CHUNK_SIZE):
        self._src = src
        self._end = end
        self._aes = AESGCM(data_key)
        self._vault_id = vault_id
        self._chunk_size = chunk_size
        self._counter = 0
        self._buf = bytearray()
        self._final_seen = False
        self._src.seek(start)

    def _next_chunk(self) -> None:
        if self._final_seen:
            raise CorruptedVaultError()
        pos = self._src.tell()
        if pos >= self._end:
            raise CorruptedVaultError()          # truncated: no final chunk
        head = self._src.read(4)
        if len(head) != 4:
            raise CorruptedVaultError()
        (length,) = struct.unpack(">I", head)
        if not (TAG_SIZE <= length <= self._chunk_size + TAG_SIZE):
            raise CorruptedVaultError()
        ct = self._src.read(length)
        if len(ct) != length:
            raise CorruptedVaultError()
        final = self._src.tell() >= self._end
        try:
            plain = self._aes.decrypt(_nonce(self._counter), ct,
                                      _aad(self._vault_id, self._counter, final))
        except InvalidTag as exc:
            raise CorruptedVaultError() from exc
        self._counter += 1
        self._final_seen = final
        self._buf += plain

    def read(self, n: int) -> bytes:
        """Return exactly ``n`` authenticated bytes or raise ``CorruptedVaultError``."""
        while len(self._buf) < n:
            self._next_chunk()
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def assert_fully_consumed(self) -> None:
        """The stream must end exactly where the last authenticated chunk ends."""
        while not self._final_seen and not self._buf:
            self._next_chunk()                   # raises if truncated or tampered
        if not self._final_seen or self._buf:
            raise CorruptedVaultError()
