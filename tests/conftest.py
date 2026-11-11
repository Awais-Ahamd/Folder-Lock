import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from security.key_manager import KdfParams  # noqa: E402
from security.recovery import generate_recovery_key  # noqa: E402

PASSWORD = "correct horse battery staple"
FAST_KDF = KdfParams(time_cost=1, memory_kib=64, parallelism=1)   # tests only; never used in the app


@pytest.fixture
def fast_kdf():
    return FAST_KDF


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def recovery_key():
    return generate_recovery_key()


@pytest.fixture
def sample_folder(tmp_path):
    root = tmp_path / "My Private Data"
    (root / "docs" / "nested" / "empty_dir").mkdir(parents=True)
    (root / "readme.txt").write_text("hello world", encoding="utf-8")
    (root / "docs" / "ünïcode – файл.txt").write_text("unicode name ok", encoding="utf-8")
    (root / "docs" / "nested" / "data.bin").write_bytes(os.urandom(2_500_000))
    (root / "zero.dat").write_bytes(b"")
    os.utime(root / "readme.txt", ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    return root


def tree_snapshot(root: Path) -> dict:
    """{relative path: bytes or None for directories} for comparing folders."""
    snap = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        snap[rel] = p.read_bytes() if p.is_file() else None
    return snap
