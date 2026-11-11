"""Path helpers: bundled resources, per-user data folder, unique names."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Locate a bundled resource both in development and inside the PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / relative


def app_data_dir() -> Path:
    """Local, non-essential runtime data (settings, log). Vaults never depend on it."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(
        Path.home() / ".local" / "share"
    )
    path = Path(base) / "FolderLock"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path(tempfile.gettempdir()) / "FolderLock"
        path.mkdir(parents=True, exist_ok=True)
    return path


def unique_path(path: Path, suffix_label: str = "") -> Path:
    """Return ``path`` or, if it exists, ``path (2)``, ``path (3)`` ... Never overwrites."""
    if not path.exists():
        return path
    stem, ext = path.stem, path.suffix
    if path.is_dir():
        stem, ext = path.name, ""
    label = f" {suffix_label}" if suffix_label else ""
    n = 2
    while True:
        candidate = path.with_name(f"{stem}{label} ({n}){ext}")
        if not candidate.exists():
            return candidate
        n += 1


def default_start_dir() -> str:
    for candidate in (Path.home() / "Documents", Path.home()):
        if candidate.is_dir():
            return str(candidate)
    return str(Path.home())
