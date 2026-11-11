"""Double-click support: file association (fake registry) and the direct-to-password GUI flow."""
import os
import sys
import time
from pathlib import Path

import pytest

from core import vault_manager as vm
from tests.conftest import PASSWORD, tree_snapshot
from utils import file_association as fa


# ------------------------------------------------------------------ fake Windows registry
class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    KEY_READ = 1
    REG_SZ = 1

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    class _Key:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def CreateKeyEx(self, root, path, _res, _access):
        assert root == self.HKEY_CURRENT_USER                      # never HKLM => no admin needed
        return self._Key(path)

    def OpenKey(self, root, path):
        assert root == self.HKEY_CURRENT_USER
        if not any(p == path for p, _ in self.store):
            raise FileNotFoundError(path)
        return self._Key(path)

    def SetValueEx(self, key, name, _res, _type, value):
        self.store[(key.path, name)] = value

    def QueryValueEx(self, key, name):
        return self.store[(key.path, name)], self.REG_SZ

    def DeleteKey(self, root, path):
        keys = [k for k in self.store if k[0] == path]
        if not keys:
            raise FileNotFoundError(path)
        for k in keys:
            del self.store[k]


@pytest.fixture
def fake_registry(monkeypatch):
    reg = FakeWinreg()
    monkeypatch.setattr(fa, "_winreg", lambda: reg)
    monkeypatch.setattr(fa, "is_supported", lambda: True)
    monkeypatch.setattr(fa, "_notify_shell", lambda: None)
    return reg


def test_register_writes_only_current_user_classes(fake_registry):
    fa.register()
    paths = {p for p, _ in fake_registry.store}
    assert all(p.startswith(r"Software\Classes") for p in paths)
    assert fake_registry.store[(r"Software\Classes\.flock", "")] == "FolderLock.Vault"
    cmd = fake_registry.store[(r"Software\Classes\FolderLock.Vault\shell\open\command", "")]
    assert cmd.endswith('"%1"') and cmd == fa.open_command()


def test_is_registered_tracks_current_program_path(fake_registry, monkeypatch):
    assert not fa.is_registered()
    fa.register()
    assert fa.is_registered()
    monkeypatch.setattr(fa, "open_command", lambda: '"C:\\Elsewhere\\FolderLock.exe" "%1"')
    assert not fa.is_registered()                       # exe moved => stale, app will refresh it


def test_unregister_removes_everything(fake_registry):
    fa.register()
    fa.unregister()
    assert fake_registry.store == {}
    assert not fa.is_registered()
    fa.unregister()                                     # harmless when already removed


def test_frozen_command_points_at_the_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"D:\Apps\FolderLock.exe")
    assert fa.open_command() == r'"D:\Apps\FolderLock.exe" "%1"'
    assert fa._icon_value() == r'"D:\Apps\FolderLock.exe",0'


# ------------------------------------------------------------------ GUI: double-click straight to password
def _make_app(tmp_path, vault_path):
    import tkinter
    from database.settings_db import SettingsDB
    from ui.app import FolderLockApp
    from ui.icons import icon
    icon.cache_clear()                                  # cached images belong to a previous (destroyed) window
    db = SettingsDB(tmp_path / "s.db")
    db.set("welcome_seen", "1")
    db.set("auto_lock", "0")
    try:
        return FolderLockApp(db, open_vault=str(vault_path))
    except tkinter.TclError as exc:
        if "display" in str(exc).lower():
            pytest.skip(f"no display available: {exc}")
        raise


def _pump(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.02)


def _wait(app, cond, timeout=60):
    end = time.time() + timeout
    while time.time() < end and not cond():
        _pump(app, 0.1)
    assert cond(), "timed out"


@pytest.fixture
def vault(tmp_path, sample_folder, fast_kdf, recovery_key):
    protected = tmp_path / "Protected"
    protected.mkdir()
    path = protected / "My Private Data.flock"
    vm.create_vault(sample_folder, path, PASSWORD, recovery_key, kdf=fast_kdf)
    return path


def test_double_click_opens_password_screen_and_restores_next_to_vault(tmp_path, vault, sample_folder):
    app = _make_app(tmp_path, vault)
    try:
        _pump(app, 0.6)
        screen = app._screen
        assert type(screen).__name__ == "UnlockScreen"
        assert screen.vault == vault
        assert hasattr(screen, "field")                         # already on the password screen
        assert screen.dest == vault.parent                      # default: where the locked file lives

        screen.field.var.set(PASSWORD)
        screen._unlock()
        _wait(app, lambda: screen.restored is not None)
        assert screen.restored.parent == vault.parent
        assert tree_snapshot(screen.restored) == tree_snapshot(sample_folder)
    finally:
        app.destroy()


def test_wrong_password_stays_on_screen_with_friendly_message(tmp_path, vault):
    app = _make_app(tmp_path, vault)
    try:
        _pump(app, 0.6)
        screen = app._screen
        screen.field.var.set("definitely wrong")
        screen._unlock()
        _wait(app, lambda: len(screen.msg.winfo_children()) > 0)
        texts = [w.label.cget("text") for w in screen.msg.winfo_children()]
        assert texts == ["Incorrect password. Your files are still protected."]
        assert screen.restored is None
    finally:
        app.destroy()


def test_existing_folder_is_not_overwritten_when_double_clicking(tmp_path, vault, sample_folder):
    existing = vault.parent / sample_folder.name
    existing.mkdir()
    (existing / "keep.txt").write_text("mine")
    app = _make_app(tmp_path, vault)
    try:
        _pump(app, 0.6)
        screen = app._screen
        screen.field.var.set(PASSWORD)
        screen._unlock()
        _wait(app, lambda: screen.restored is not None)
        assert screen.restored != existing
        assert (existing / "keep.txt").read_text() == "mine"
    finally:
        app.destroy()


def test_default_destination_setting_is_respected(tmp_path, vault):
    chosen = tmp_path / "elsewhere"
    chosen.mkdir()
    app = _make_app(tmp_path, vault)
    try:
        _pump(app, 0.6)
        app.settings.set("default_destination", str(chosen))
        app.open_vault_file(vault)
        _pump(app, 0.3)
        assert app._screen.dest == chosen
    finally:
        app.destroy()


def test_invalid_file_argument_does_not_crash(tmp_path, monkeypatch):
    junk = tmp_path / "junk.flock"
    junk.write_bytes(os.urandom(50_000))
    shown = []
    import ui.app as app_module
    monkeypatch.setattr(app_module, "show_message", lambda *a, **k: shown.append(a[1]))
    app = _make_app(tmp_path, junk)
    try:
        _pump(app, 0.6)
        assert shown == ["This file cannot be opened"]
        assert type(app._screen).__name__ == "Dashboard"
    finally:
        app.destroy()
