"""Build the portable executable.

    python build.py            -> dist/FolderLock.exe  (Windows)

Steps: install-check, regenerate assets if missing, run the tests, run PyInstaller
(one-file, windowed), then run the packaged program's built-in self-test.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*cmd: str) -> None:
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    if sys.version_info < (3, 10):
        print("Please build with Python 3.10 or newer (3.12 recommended).")
        return 1
    if not (ROOT / "assets" / "logo.png").exists() or not (ROOT / "assets" / "icon.ico").exists():
        run(sys.executable, "tools/make_assets.py")

    if "--skip-tests" not in sys.argv:
        run(sys.executable, "-m", "pytest", "-q")

    run(sys.executable, "-m", "PyInstaller", "FolderLock.spec", "--noconfirm", "--clean")

    exe = ROOT / "dist" / ("FolderLock.exe" if sys.platform.startswith("win") else "FolderLock")
    if not exe.exists():
        print("Build failed: executable not found.")
        return 1

    result = Path(tempfile.mkdtemp()) / "selftest.txt"
    print("> running the packaged self-test ...", flush=True)
    subprocess.run([str(exe), "--selftest", str(result)], check=False, timeout=300)
    outcome = result.read_text(encoding="utf-8") if result.exists() else "no result written"
    if outcome != "OK":
        print("Packaged self-test FAILED:", outcome)
        return 1

    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    print(f"\nBuild complete: {exe}  ({exe.stat().st_size / 1e6:.1f} MB)")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
