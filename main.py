"""FolderLock entry point.

``FolderLock.exe --selftest <result-file>`` runs a headless end-to-end encryption
check (used by the build pipeline to prove the packaged exe contains every
dependency) and writes ``OK`` or an error to the given file.
"""
from __future__ import annotations

import multiprocessing
import sys


def selftest(result_path: str) -> int:
    """Create, verify, tamper-check and restore a real vault using the production settings."""
    import os
    import tempfile
    from pathlib import Path

    try:
        from core import vault_manager as vm
        from security.recovery import generate_recovery_key
        from utils.error_handler import CorruptedVaultError, WrongPasswordError

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "SelfTest"
            (src / "sub").mkdir(parents=True)
            payload = os.urandom(2_500_000)
            (src / "a.txt").write_text("hello", encoding="utf-8")
            (src / "sub" / "b.bin").write_bytes(payload)
            key = generate_recovery_key()
            vault = root / "SelfTest.flock"
            vm.create_vault(src, vault, "Self-test password 123!", key)        # Argon2id, AES-256-GCM
            try:
                vm.unlock_with_password(vault, "wrong password")
                raise AssertionError("wrong password was accepted")
            except WrongPasswordError:
                pass
            keys = vm.unlock_with_recovery_key(vault, key)
            out = root / "out"
            out.mkdir()
            restored = vm.extract_vault(vault, keys, out)
            assert (restored / "a.txt").read_text(encoding="utf-8") == "hello"
            assert (restored / "sub" / "b.bin").read_bytes() == payload
            data = bytearray(vault.read_bytes())
            data[len(data) // 2] ^= 1
            vault.write_bytes(bytes(data))
            try:
                vm.extract_vault(vault, vm.unlock_with_password(vault, "Self-test password 123!"), out)
                raise AssertionError("tampering was not detected")
            except CorruptedVaultError:
                pass
        message = "OK"
        code = 0
    except Exception as exc:  # noqa: BLE001
        message, code = f"FAILED: {type(exc).__name__}: {exc}", 1
    Path(result_path).write_text(message, encoding="utf-8")
    return code


def main() -> None:
    multiprocessing.freeze_support()          # required for frozen Windows executables
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))

    from ui.app import run
    # Double-clicking a .flock file passes its path as the first argument.
    vault_arg = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    try:
        run(vault_arg)
    except Exception as exc:  # noqa: BLE001 - last-resort net; never show a traceback to users
        from utils.error_handler import log_exception
        log_exception(exc)
        try:
            import tkinter
            from tkinter import messagebox
            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror(
                "FolderLock",
                "FolderLock ran into a problem and needs to close.\n"
                "Your files were not changed.")
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
