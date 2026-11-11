# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build definition for FolderLock (ONE portable, windowed executable).
#
# Build with:   python build.py        (or:  pyinstaller FolderLock.spec --noconfirm)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
IS_WINDOWS = sys.platform.startswith("win")

datas = [(str(ROOT / "assets"), "assets")]
binaries = []
hiddenimports = []

# CustomTkinter ships themes/fonts as data files that must travel inside the exe.
datas += collect_data_files("customtkinter")
datas += collect_data_files("darkdetect")

# Argon2 uses a compiled CFFI extension; collect it explicitly so the exe never
# needs anything installed on the user's PC.
for package in ("argon2", "_argon2_cffi_bindings", "cryptography"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden
hiddenimports += collect_submodules("argon2")
hiddenimports += ["_cffi_backend", "sqlite3"]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "numpy", "matplotlib", "pandas", "scipy", "IPython", "unittest", "pydoc",
              "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FolderLock",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX-packed exes trigger more antivirus false positives
    runtime_tmpdir=None,
    console=False,                  # windowed: no command prompt window
    disable_windowed_traceback=True,
    argv_emulation=False,
    uac_admin=False,                # never asks for administrator rights
    icon=str(ROOT / "assets" / "icon.ico") if IS_WINDOWS else None,
    version=str(ROOT / "tools" / "version_info.txt") if IS_WINDOWS else None,
)
