"""Settings storage, friendly messages and helpers."""
import errno

from database.settings_db import SettingsDB
from utils.error_handler import (
    CorruptedVaultError, FolderLockError, InsufficientSpaceError, WrongPasswordError, friendly_message,
)
from utils.paths import unique_path


def test_settings_roundtrip_and_defaults(tmp_path):
    db = SettingsDB(tmp_path / "s.db")
    assert db.get("theme") == "Dark"
    db.set("theme", "Light")
    assert SettingsDB(tmp_path / "s.db").get("theme") == "Light"
    assert db.get_int("auto_lock_minutes") == 10


def test_settings_reject_unknown_keys_and_hold_no_secrets(tmp_path):
    import pytest
    db = SettingsDB(tmp_path / "s.db")
    with pytest.raises(KeyError):
        db.set("password", "hunter2")


def test_friendly_messages_never_expose_tracebacks():
    assert friendly_message(WrongPasswordError()) == "Incorrect password. Your files are still protected."
    assert "damaged" in friendly_message(CorruptedVaultError())
    assert "space" in friendly_message(InsufficientSpaceError())
    assert "permission" in friendly_message(PermissionError("x")).lower() or \
           "allow" in friendly_message(PermissionError("x")).lower()
    assert "not enough free space" in friendly_message(OSError(errno.ENOSPC, "full"))
    generic = friendly_message(RuntimeError("Traceback secret internals"))
    assert "Traceback" not in generic and "internals" not in generic


def test_every_error_class_has_user_message():
    for cls in FolderLockError.__subclasses__():
        assert cls().user_message


def test_unique_path_never_overwrites(tmp_path):
    p = tmp_path / "a.flock"
    p.write_text("x")
    q = unique_path(p)
    assert q != p and not q.exists()
