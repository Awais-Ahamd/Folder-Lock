"""About screen."""
from __future__ import annotations

import customtkinter as ctk
from PIL import Image

from ui import theme as T
from ui.dialogs import show_welcome
from ui.widgets import AppButton, Card, Label
from utils.paths import resource_path


class AboutScreen(ctk.CTkFrame):
    def __init__(self, master, app, **_):
        super().__init__(master, fg_color="transparent")
        th = app.theme
        self.grid_columnconfigure(0, weight=1)
        col = ctk.CTkFrame(self, fg_color="transparent")
        col.grid(row=0, column=0, pady=(T.PAD + 10, 0))
        logo = Image.open(resource_path("assets/logo.png"))
        ctk.CTkLabel(col, text="", image=ctk.CTkImage(logo, logo, size=(120, 120))).pack()
        Label(col, th, T.APP_NAME, "title", anchor="center", justify="center").pack(pady=(8, 0))
        Label(col, th, f"Version {T.APP_VERSION}", "muted", anchor="center", justify="center").pack()
        Label(col, th, T.APP_DESCRIPTION, "body", anchor="center", justify="center", wraplength=460
              ).pack(pady=(14, 18))

        card = Card(col, th)
        card.pack(fill="x", padx=10)
        for label, value in (("Application", T.APP_NAME), ("Version", T.APP_VERSION),
                             ("Technology", "Python"),
                             ("Developer", "Awais Ahmad")):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=5)
            Label(row, th, label, "small", width=110).pack(side="left")
            Label(row, th, value, "body", wraplength=320).pack(side="left", fill="x", expand=True)
        card.pack_configure(pady=(0, 14))

        AppButton(col, th, "Show Welcome Guide", lambda: show_welcome(app), kind="secondary", width=210
                  ).pack(pady=(6, 0))
