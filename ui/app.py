"""Main window: sidebar navigation, screen switching, theme, inactivity auto-close."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from core import vault_manager as vm
from database.settings_db import SettingsDB
from ui import theme as T
from ui.dialogs import ask_confirm, show_message, show_welcome
from ui.icons import icon
from ui.widgets import Label, font
from ui.worker import TaskRunner
from utils import file_association as fa
from utils.error_handler import FolderLockError, friendly_message
from utils.paths import resource_path


class FolderLockApp(ctk.CTk):
    def __init__(self, settings: SettingsDB | None = None, open_vault: str | Path | None = None):
        super().__init__()
        self.settings = settings or SettingsDB()
        self.runner = TaskRunner(self)
        self.theme = T.THEMES.get(self.settings.get("theme"), T.DARK)
        self._screen: ctk.CTkFrame | None = None
        self._current = "dashboard"
        self._current_kw: dict = {}
        self._idle_job = None

        self.title(T.APP_NAME)
        self.geometry("960x660")
        self.minsize(820, 600)
        try:
            self.iconbitmap(str(resource_path("assets/icon.ico")))
        except tk.TclError:
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        for seq in ("<Key>", "<Motion>", "<Button>"):
            self.bind_all(seq, self._activity, add="+")

        self._build_shell()
        self.show("dashboard")
        self._activity()
        self._refresh_file_association()
        if open_vault:                       # a .flock file was double-clicked / passed on the command line
            self.after(150, lambda: self.open_vault_file(open_vault))
        elif not self.settings.get_bool("welcome_seen"):
            self.after(400, self._first_run)

    # ------------------------------------------------------------------ opening a vault directly
    def open_vault_file(self, path: str | Path) -> None:
        """Jump straight to the password screen for a vault file."""
        vault = Path(path)
        try:
            vm.inspect_vault(vault)
        except FolderLockError as exc:
            show_message(self, "This file cannot be opened", exc.user_message, "warning")
            return
        except OSError as exc:
            show_message(self, "This file cannot be opened", friendly_message(exc), "warning")
            return
        self.show("unlock", vault=str(vault))
        self.lift()
        self.focus_force()

    def _refresh_file_association(self) -> None:
        """If the user opted in, keep double-click working after the exe is moved/copied."""
        if self.settings.get_bool("file_association") and fa.is_supported() and not fa.is_registered():
            try:
                fa.register()
            except OSError:
                pass

    # ------------------------------------------------------------------ layout
    def _build_shell(self) -> None:
        th = self.theme
        ctk.set_appearance_mode(th.mode)
        self.configure(fg_color=th.bg)
        for child in self.winfo_children():
            if isinstance(child, (ctk.CTkFrame,)):
                child.destroy()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, fg_color=th.sidebar, corner_radius=0, width=210)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        self.sidebar = side
        from PIL import Image
        logo = Image.open(resource_path("assets/logo.png"))
        ctk.CTkLabel(side, text="", image=ctk.CTkImage(logo, logo, size=(92, 92))).pack(pady=(26, 4))
        ctk.CTkLabel(side, text=T.APP_NAME, font=font(24, "bold"), text_color=th.text).pack()
        ctk.CTkLabel(side, text=T.APP_TAGLINE, font=font(T.SMALL), text_color=th.muted).pack(pady=(0, 22))

        self._nav: dict[str, ctk.CTkButton] = {}
        for key, label, ic in (("dashboard", "Home", "home"), ("settings", "Settings", "settings"),
                               ("about", "About", "info")):
            btn = ctk.CTkButton(side, text="  " + label, anchor="w", height=42, corner_radius=T.RADIUS_SMALL,
                                font=font(T.BODY, "bold"), fg_color="transparent",
                                hover_color=th.surface_alt, text_color=th.text, image=icon(ic, th.icon, 20, th.sidebar),
                                command=lambda k=key: self.navigate(k))
            btn.pack(fill="x", padx=14, pady=3)
            self._nav[key] = btn
        ctk.CTkLabel(side, text=f"Version {T.APP_VERSION}", font=font(T.SMALL), text_color=th.muted
                     ).pack(side="bottom", pady=14)

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=(8, 8), pady=8)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _highlight(self, key: str) -> None:
        th = self.theme
        active = {"dashboard": "dashboard", "settings": "settings", "about": "about"}.get(key)
        for k, btn in self._nav.items():
            on = k == active
            btn.configure(fg_color=th.surface if on else "transparent",
                          text_color=th.primary if on and th.name != "Light" else th.text)

    # ------------------------------------------------------------------ navigation
    def navigate(self, name: str, **kw) -> None:
        """User-initiated navigation (blocked while an operation is running)."""
        if self.runner.busy:
            show_message(self, "Please wait", "FolderLock is busy. You can cancel the operation "
                         "safely with the Cancel button.", "info")
            return
        self.show(name, **kw)

    def show(self, name: str, **kw) -> None:
        from ui.about import AboutScreen
        from ui.dashboard import Dashboard
        from ui.lock_screen import LockScreen
        from ui.password_screen import ChangePasswordScreen
        from ui.recovery_screen import NewRecoveryKeyScreen, RecoveryScreen
        from ui.settings import SettingsScreen
        from ui.unlock_screen import UnlockScreen

        screens = {
            "dashboard": Dashboard, "lock": LockScreen, "unlock": UnlockScreen,
            "change_password": ChangePasswordScreen, "recovery": RecoveryScreen,
            "new_recovery_key": NewRecoveryKeyScreen, "settings": SettingsScreen, "about": AboutScreen,
        }
        if self._screen is not None:
            self._screen.destroy()
        self._current, self._current_kw = name, kw
        self._screen = screens[name](self.content, self, **kw)
        self._screen.grid(row=0, column=0, sticky="nsew")
        self._highlight("dashboard" if name not in ("settings", "about") else name)

    # ------------------------------------------------------------------ theme
    def apply_theme(self, name: str) -> None:
        self.settings.set("theme", name)
        self.theme = T.THEMES[name]
        self._build_shell()
        self._screen = None
        self.show(self._current, **self._current_kw)

    # ------------------------------------------------------------------ inactivity
    def _activity(self, _event=None) -> None:
        if self._idle_job is not None:
            self.after_cancel(self._idle_job)
            self._idle_job = None
        if self.settings.get_bool("auto_lock"):
            ms = self.settings.get_int("auto_lock_minutes") * 60_000
            self._idle_job = self.after(ms, self._idle_timeout)

    def _idle_timeout(self) -> None:
        """Close the app after inactivity so nothing typed stays in memory.
        This does NOT encrypt anything; it only ends this program session."""
        self._idle_job = None
        if self.runner.busy:
            self._activity()
            return
        self.destroy()

    def _first_run(self) -> None:
        show_welcome(self)
        self.settings.set("welcome_seen", "1")

    # ------------------------------------------------------------------ closing
    def on_close(self) -> None:
        if self.runner.busy:
            if not ask_confirm(self, "FolderLock is still working",
                               "Closing now will stop the current operation. Your original files "
                               "will not be changed, and unfinished temporary files are removed.",
                               yes="Stop and close", no="Keep working"):
                return
            self.runner.cancel()
            self.runner.wait(8.0)
        self.destroy()


def run(open_vault: str | None = None) -> None:
    if sys.platform.startswith("win"):
        try:                                    # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    ctk.set_default_color_theme("blue")
    app = FolderLockApp(open_vault=open_vault)
    app.mainloop()
