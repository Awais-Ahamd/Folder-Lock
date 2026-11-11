"""Tiny SQLite key/value store for *non-security* preferences only.

No passwords, keys, or vault data are ever stored here, and vaults never need
this file - deleting it just resets the preferences.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from utils.paths import app_data_dir

DEFAULTS: dict[str, str] = {
    "theme": "Dark",                 # Dark | Light | Blue
    "auto_lock": "1",                # close the app after inactivity
    "auto_lock_minutes": "10",
    "default_destination": "",
    "welcome_seen": "0",
    "file_association": "0",         # double-click .flock opens FolderLock (opt-in, current user only)
    "assoc_offered": "0",            # the one-time offer after the first lock was shown
}
ALLOWED_THEMES = ("Dark", "Light", "Blue")


class SettingsDB:
    def __init__(self, path: Path | None = None):
        self._lock = threading.Lock()
        self._memory: dict[str, str] = {}
        try:
            self._conn: sqlite3.Connection | None = sqlite3.connect(
                str(path or app_data_dir() / "settings.db"), check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self._conn.commit()
        except (sqlite3.Error, OSError):
            self._conn = None            # fall back to in-memory settings for this run

    def get(self, key: str) -> str:
        with self._lock:
            if self._conn is not None:
                try:
                    row = self._conn.execute(
                        "SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
                    if row:
                        return row[0]
                except sqlite3.Error:
                    pass
            return self._memory.get(key, DEFAULTS.get(key, ""))

    def set(self, key: str, value: str) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        value = str(value)
        with self._lock:
            self._memory[key] = value
            if self._conn is not None:
                try:
                    self._conn.execute(
                        "INSERT INTO settings(key, value) VALUES(?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
                    self._conn.commit()
                except sqlite3.Error:
                    pass

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    def get_int(self, key: str, minimum: int = 1, maximum: int = 240) -> int:
        try:
            return max(minimum, min(maximum, int(self.get(key))))
        except ValueError:
            return int(DEFAULTS.get(key, "10"))
