"""Folder scanning, safe-path validation, disk-space checks and cleanup."""
from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path

from core.vault_format import PARTIAL_MARKER
from utils.error_handler import (
    InsufficientSpaceError, SourceFolderError, UnsafePathError,
)

RESTORE_STAGING_PREFIX = ".folderlock_restore_"
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_PATH_LEN = 4096


@dataclass
class FileEntry:
    rel: str            # POSIX-style relative path
    abs: Path
    size: int
    mtime_ns: int


@dataclass
class FolderScan:
    root: Path
    dirs: list[str] = field(default_factory=list)
    files: list[FileEntry] = field(default_factory=list)
    skipped_links: int = 0

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


# --------------------------------------------------------------------------- #
# Safe names
# --------------------------------------------------------------------------- #
def validate_component(name: str) -> None:
    """A single file/folder name must be harmless on every supported OS."""
    if (not name or name in (".", "..") or "/" in name or "\\" in name or ":" in name
            or "\x00" in name or any(ord(c) < 32 for c in name)
            or name != name.rstrip(" .")
            or name.split(".")[0].upper() in _WINDOWS_RESERVED
            or any(c in name for c in '<>"|?*')):
        raise UnsafePathError()


def validate_relative_path(rel: str) -> tuple[str, ...]:
    """Reject absolute paths, drive letters, traversal and odd names. Returns the parts."""
    if not rel or len(rel) > _MAX_PATH_LEN or rel.startswith("/"):
        raise UnsafePathError()
    parts = tuple(rel.split("/"))
    for part in parts:
        validate_component(part)
    return parts


def safe_join(root: Path, rel: str) -> Path:
    """Join and prove the result stays inside ``root`` (defence in depth)."""
    parts = validate_relative_path(rel)
    target = root.joinpath(*parts)
    root_abs = os.path.abspath(root)
    if os.path.commonpath([root_abs, os.path.abspath(target)]) != root_abs:
        raise UnsafePathError()
    return target


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def _is_link(path: str) -> bool:
    """Symlinks and Windows junctions/reparse points are never followed."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)   # FILE_ATTRIBUTE_REPARSE_POINT


def check_source_folder(folder: Path) -> None:
    """Friendly accessibility check before anything starts."""
    if not folder.exists():
        raise SourceFolderError("The selected folder could not be found.")
    if not folder.is_dir():
        raise SourceFolderError("Please select a folder, not a file.")
    if not os.access(folder, os.R_OK | os.X_OK):
        raise SourceFolderError(
            "FolderLock does not have permission to read this folder. "
            "Choose a folder you own (for example, inside Documents)."
        )
    if folder.parent == folder:
        raise SourceFolderError("Please choose a folder, not a whole drive.")


def scan_folder(folder: Path, exclude: set[Path] | None = None) -> FolderScan:
    """Collect all directories and files. Raises ``SourceFolderError`` on unreadable items."""
    check_source_folder(folder)
    exclude_abs = {os.path.abspath(p) for p in (exclude or set())}
    scan = FolderScan(root=folder)

    def onerror(err: OSError) -> None:
        raise SourceFolderError(
            f"FolderLock cannot read “{getattr(err, 'filename', '') or folder}”. "
            "Close any program using it or check your permissions."
        )

    for dirpath, dirnames, filenames in os.walk(folder, topdown=True, onerror=onerror,
                                                 followlinks=False):
        dirnames.sort()
        kept = []
        for d in dirnames:
            full = os.path.join(dirpath, d)
            if _is_link(full):
                scan.skipped_links += 1
                continue
            kept.append(d)
            scan.dirs.append(Path(os.path.relpath(full, folder)).as_posix())
        dirnames[:] = kept
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if os.path.abspath(full) in exclude_abs or PARTIAL_MARKER in name:
                continue
            if _is_link(full):
                scan.skipped_links += 1
                continue
            try:
                st = os.stat(full)
            except OSError as exc:
                onerror(exc)
            if not stat.S_ISREG(st.st_mode):
                scan.skipped_links += 1
                continue
            rel = Path(os.path.relpath(full, folder)).as_posix()
            scan.files.append(FileEntry(rel, Path(full), st.st_size, st.st_mtime_ns))

    for rel in scan.dirs + [f.rel for f in scan.files]:
        validate_relative_path(rel)
    validate_component(folder.name or "")
    return scan


# --------------------------------------------------------------------------- #
# Disk space and cleanup
# --------------------------------------------------------------------------- #
def ensure_free_space(directory: Path, needed_bytes: int) -> None:
    """Require the data size plus a safety margin to be free."""
    margin = 64 * 1024 * 1024 + needed_bytes // 50
    try:
        free = shutil.disk_usage(directory).free
    except OSError:
        return          # cannot determine; real write errors are still handled
    if free < needed_bytes + margin:
        raise InsufficientSpaceError()


def _on_rm_error(func, path, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_folder(folder: Path) -> None:
    """Delete a folder tree (ordinary deletion - NOT a secure erase)."""
    shutil.rmtree(folder, onerror=_on_rm_error)


def remove_staging(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def cleanup_stale_files(directory: Path) -> int:
    """Remove leftovers of interrupted FolderLock operations in ``directory``.

    Only files/folders carrying FolderLock's own temporary markers are touched;
    they are never valid vaults and never contain the user's only copy of data.
    """
    removed = 0
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return 0
    for entry in entries:
        try:
            if PARTIAL_MARKER in entry.name and entry.is_file(follow_symlinks=False):
                os.remove(entry.path)
                removed += 1
            elif entry.name.startswith(RESTORE_STAGING_PREFIX) and entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
