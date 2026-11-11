"""Settings screen (matches the mockup: rows with actions, auto-lock switch, theme choice)."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from database.settings_db import ALLOWED_THEMES
from ui import theme as T
from ui.dialogs import show_message
from ui.flow import pick_folder
from ui.icons import icon
from ui.widgets import AppButton, Card, Label, Tooltip, font
from utils import file_association as fa


class SettingsScreen(ctk.CTkScrollableFrame):
    def __init__(self, master, app, **_):
        th = app.theme
        super().__init__(master, fg_color="transparent", scrollbar_button_color=th.surface_alt,
                         scrollbar_button_hover_color=th.border)
        self.app, self.th = app, th
        self.grid_columnconfigure(0, weight=1)
        Label(self, th, "Settings", "title").pack(fill="x", padx=T.PAD, pady=(T.PAD, 12))

        self._row("key", "Change Password", "Update the password of a protected file.",
                  AppButton(self._card(), th, "Change", lambda: app.navigate("change_password"),
                            width=120, height=38))
        self._row("lifebuoy", "Recovery Options", "Use or renew your recovery key.",
                  AppButton(self._card(), th, "Open", lambda: app.navigate("recovery"), width=120, height=38))
        if fa.is_supported():
            self._double_click_row()
        self._autolock_row()
        self._theme_row()
        self._destination_row()
        self._row("info", "Application Information", f"{T.APP_NAME} {T.APP_VERSION} - version, "
                  "technology and developer.",
                  AppButton(self._card(), th, "About", lambda: app.navigate("about"), width=120, height=38))

    # ---------------------------------------------------------------- helpers
    def _card(self) -> Card:
        card = Card(self, self.th, corner_radius=T.RADIUS)
        card.pack(fill="x", padx=T.PAD, pady=5)
        card.grid_columnconfigure(1, weight=1)
        self._last = card
        return card

    def _row(self, icon_name: str, title: str, desc: str, action) -> Card:
        # `action` was created with the card as parent; lay out the card contents now.
        card = self._last
        self._fill(card, icon_name, title, desc)
        action.grid(row=0, column=2, padx=16, pady=14, sticky="e")
        return card

    def _fill(self, card: Card, icon_name: str, title: str, desc: str) -> ctk.CTkFrame:
        th = self.th
        ctk.CTkLabel(card, text="", image=icon(icon_name, th.icon, 26, accent=th.surface)
                     ).grid(row=0, column=0, padx=(16, 10), pady=14)
        text = ctk.CTkFrame(card, fg_color="transparent")
        text.grid(row=0, column=1, sticky="w", pady=10)
        Label(text, th, title, "bold").pack(fill="x")
        Label(text, th, desc, "small", wraplength=360).pack(fill="x")
        return text

    # ---------------------------------------------------------------- double-click to open
    def _double_click_row(self) -> None:
        th = self.th
        card = self._card()
        self._fill(card, "unlock", "Open with Double-Click",
                   "Double-click a protected file (.flock) to open FolderLock at the password screen. "
                   "Affects only your Windows account.")
        self.assoc_var = tk.BooleanVar(value=fa.is_registered())
        ctk.CTkSwitch(card, text="", variable=self.assoc_var, command=self._toggle_assoc, width=46,
                      progress_color=th.primary, button_color=th.text, fg_color=th.border,
                      button_hover_color=th.text).grid(row=0, column=2, padx=16, pady=14, sticky="e")

    def _toggle_assoc(self) -> None:
        want = self.assoc_var.get()
        try:
            fa.register() if want else fa.unregister()
            self.app.settings.set("file_association", "1" if want else "0")
        except OSError:
            self.assoc_var.set(not want)
            show_message(self.app, "Could not change this setting",
                         "Windows did not allow the change. Please try again.", "warning")

    # ---------------------------------------------------------------- auto lock
    def _autolock_row(self) -> None:
        th, s = self.th, self.app.settings
        card = self._card()
        self._fill(card, "lock", "Auto Lock",
                   "Close FolderLock after a period of inactivity. This only closes the program - "
                   "it does not encrypt your folders.")
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=2, padx=16, pady=14, sticky="e")
        self.auto_var = tk.BooleanVar(value=s.get_bool("auto_lock"))
        self.minutes = ctk.CTkOptionMenu(
            right, values=["2", "5", "10", "15", "30", "60"], width=70, height=32,
            fg_color=th.surface_alt, button_color=th.border, button_hover_color=th.primary,
            text_color=th.text, dropdown_fg_color=th.surface, dropdown_text_color=th.text,
            command=self._set_minutes, font=font(T.SMALL))
        self.minutes.set(str(s.get_int("auto_lock_minutes")) if str(s.get_int("auto_lock_minutes")) in
                         ("2", "5", "10", "15", "30", "60") else "10")
        self.minutes.pack(side="left", padx=(0, 6))
        Label(right, th, "min", "small").pack(side="left", padx=(0, 12))
        ctk.CTkSwitch(right, text="", variable=self.auto_var, command=self._toggle_auto, width=46,
                      progress_color=th.primary, button_color=th.text, fg_color=th.border,
                      button_hover_color=th.text).pack(side="left")
        self._sync_minutes()

    def _toggle_auto(self) -> None:
        self.app.settings.set("auto_lock", "1" if self.auto_var.get() else "0")
        self._sync_minutes()
        self.app._activity()

    def _set_minutes(self, value: str) -> None:
        self.app.settings.set("auto_lock_minutes", value)
        self.app._activity()

    def _sync_minutes(self) -> None:
        self.minutes.configure(state="normal" if self.auto_var.get() else "disabled")

    # ---------------------------------------------------------------- theme
    def _theme_row(self) -> None:
        th = self.th
        card = self._card()
        self._fill(card, "settings", "Theme", "Choose how FolderLock looks.")
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=2, padx=16, pady=14, sticky="e")
        self.theme_var = tk.StringVar(value=self.app.settings.get("theme"))
        for name in ALLOWED_THEMES:
            ctk.CTkRadioButton(right, text=name, value=name, variable=self.theme_var, font=font(T.SMALL + 1),
                               text_color=th.text, fg_color=th.primary, hover_color=th.primary_hover,
                               border_color=th.muted, command=self._set_theme, radiobutton_width=18,
                               radiobutton_height=18).pack(anchor="w", pady=2)

    def _set_theme(self) -> None:
        if self.theme_var.get() != self.app.theme.name:
            self.app.apply_theme(self.theme_var.get())

    # ---------------------------------------------------------------- default destination
    def _destination_row(self) -> None:
        th, s = self.th, self.app.settings
        card = self._card()
        text = self._fill(card, "folder", "Default Destination",
                          "Where protected files are saved and folders are restored by default.")
        self.dest_label = Label(text, th, "", "small", wraplength=360)
        self.dest_label.pack(fill="x")
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=0, column=2, padx=16, pady=14, sticky="e")
        AppButton(right, th, "Choose…", self._choose_dest, width=110, height=38).pack(side="left")
        AppButton(right, th, "Reset", self._clear_dest, kind="secondary", width=80, height=38
                  ).pack(side="left", padx=(8, 0))
        self._refresh_dest()

    def _refresh_dest(self) -> None:
        value = self.app.settings.get("default_destination")
        self.dest_label.configure(text=f"Current: {value}" if value else "Current: not set (asks each time)")

    def _choose_dest(self) -> None:
        picked = pick_folder(self.app, "Choose the default destination")
        if picked:
            self.app.settings.set("default_destination", str(picked))
            self._refresh_dest()

    def _clear_dest(self) -> None:
        self.app.settings.set("default_destination", "")
        self._refresh_dest()
