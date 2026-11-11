"""Exceptions and friendly, non-technical error messages.

Every error that can reach the user is converted to plain language here.
Raw Python tracebacks are only written to the (secret-free) log file and are
never shown in the interface.
"""
from __future__ import annotations

import errno
import logging
import traceback

from utils.paths import app_data_dir

_logger = logging.getLogger("folderlock")


def _setup_logging() -> None:
    if _logger.handlers:
        return
    _logger.setLevel(logging.ERROR)
    try:
        handler: logging.Handler = logging.FileHandler(
            app_data_dir() / "error.log", encoding="utf-8"
        )
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _logger.addHandler(handler)


class FolderLockError(Exception):
    """Base class. ``user_message`` is always safe and friendly to display."""

    default_message = "Something went wrong. Your original files were not changed."

    def __init__(self, user_message: str | None = None):
        self.user_message = user_message or self.default_message
        super().__init__(self.user_message)


class WrongPasswordError(FolderLockError):
    default_message = "Incorrect password. Your files are still protected."


class WrongRecoveryKeyError(FolderLockError):
    default_message = (
        "That recovery key does not match this vault. "
        "Please check it carefully and try again."
    )


class InvalidVaultError(FolderLockError):
    default_message = "This is not a valid FolderLock vault file."


class CorruptedVaultError(FolderLockError):
    default_message = (
        "This vault is damaged or has been modified, so it cannot be opened safely. "
        "Nothing was restored."
    )


class UnsupportedVersionError(FolderLockError):
    default_message = (
        "This vault was created by a newer version of FolderLock. "
        "Please use the latest FolderLock to open it."
    )


class InsufficientSpaceError(FolderLockError):
    default_message = (
        "There is not enough free space on the disk. "
        "Free some space or choose another location, then try again."
    )


class OperationCancelled(FolderLockError):
    default_message = "The operation was cancelled. Your original files were not changed."


class UnsafePathError(FolderLockError):
    default_message = (
        "The vault contains an unsafe file name and was not opened. "
        "Nothing was restored."
    )


class SourceFolderError(FolderLockError):
    default_message = "FolderLock cannot read the selected folder."


class DestinationError(FolderLockError):
    default_message = "FolderLock cannot write to the chosen location."


class VerificationError(FolderLockError):
    default_message = (
        "The safety check failed, so FolderLock did not finish. "
        "Your original files were not changed."
    )


def friendly_message(exc: BaseException) -> str:
    """Return a plain-language message for any exception."""
    if isinstance(exc, FolderLockError):
        return exc.user_message
    if isinstance(exc, PermissionError):
        return (
            "Windows did not allow FolderLock to access a file or folder. "
            "Close any programs using it, or choose a location you own, then try again."
        )
    if isinstance(exc, FileNotFoundError):
        return "A file or folder could not be found. It may have been moved or deleted."
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return InsufficientSpaceError.default_message
    if isinstance(exc, MemoryError):
        return (
            "This computer does not have enough free memory to open this vault. "
            "Close other programs and try again."
        )
    log_exception(exc)
    return FolderLockError.default_message


def log_exception(exc: BaseException) -> None:
    """Write the traceback (never passwords or keys) to the local log file."""
    _setup_logging()
    _logger.error("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
