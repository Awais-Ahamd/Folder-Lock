"""Optional, per-user Windows file association so a double-click on a ``.flock`` file opens FolderLock.

* Writes only under HKEY_CURRENT_USER\\Software\\Classes - **no administrator rights needed**.
* Strictly opt-in (a Settings switch, or a one-time offer after the first lock). Vaults work
  without it; it only adds convenience.
* Fully reversible with :func:`unregister`.
"""
from __future__ import annotations

import sys
from pathlib import Path

EXT = ".flock"
PROG_ID = "FolderLock.Vault"
_CLASSES = r"Software\Classes"


def is_supported() -> bool:
    return sys.platform.startswith("win")


def _winreg():                       # separate function so tests can substitute a fake registry
    import winreg
    return winreg


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def open_command() -> str:
    """The command Windows runs for a double-clicked vault (``%1`` = the file)."""
    if _frozen():
        return f'"{sys.executable}" "%1"'
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    exe = Path(sys.executable)
    runner = exe.with_name("pythonw.exe")
    return f'"{runner if runner.exists() else exe}" "{main_py}" "%1"'


def _icon_value() -> str:
    if _frozen():
        return f'"{sys.executable}",0'
    return str(Path(__file__).resolve().parent.parent / "assets" / "icon.ico")


def _set(w, path: str, value: str, name: str = "") -> None:
    with w.CreateKeyEx(w.HKEY_CURRENT_USER, path, 0, w.KEY_SET_VALUE) as key:
        w.SetValueEx(key, name, 0, w.REG_SZ, value)


def register() -> None:
    """Make ``.flock`` files open with this copy of FolderLock (current user only)."""
    w = _winreg()
    _set(w, f"{_CLASSES}\\{EXT}", PROG_ID)
    _set(w, f"{_CLASSES}\\{EXT}", "application/x-folderlock-vault", "Content Type")
    _set(w, f"{_CLASSES}\\{PROG_ID}", "FolderLock protected folder")
    _set(w, f"{_CLASSES}\\{PROG_ID}\\DefaultIcon", _icon_value())
    _set(w, f"{_CLASSES}\\{PROG_ID}\\shell\\open\\command", open_command())
    _notify_shell()


def is_registered() -> bool:
    """True when ``.flock`` currently opens *this* copy of FolderLock."""
    if not is_supported():
        return False
    try:
        w = _winreg()
        with w.OpenKey(w.HKEY_CURRENT_USER, f"{_CLASSES}\\{PROG_ID}\\shell\\open\\command") as key:
            value, _ = w.QueryValueEx(key, "")
        return value == open_command()
    except OSError:
        return False


def unregister() -> None:
    w = _winreg()
    for path in (f"{_CLASSES}\\{PROG_ID}\\shell\\open\\command", f"{_CLASSES}\\{PROG_ID}\\shell\\open",
                 f"{_CLASSES}\\{PROG_ID}\\shell", f"{_CLASSES}\\{PROG_ID}\\DefaultIcon",
                 f"{_CLASSES}\\{PROG_ID}", f"{_CLASSES}\\{EXT}"):
        try:
            w.DeleteKey(w.HKEY_CURRENT_USER, path)
        except OSError:
            pass
    _notify_shell()


def _notify_shell() -> None:
    """Tell Explorer the associations changed so icons/double-click update immediately."""
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
    except Exception:  # noqa: BLE001
        pass
