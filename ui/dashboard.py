"""Home screen: welcome, short description and the main actions (as in the mockup)."""
from __future__ import annotations

import customtkinter as ctk
from PIL import Image

from ui import theme as T
from ui.icons import icon
from ui.widgets import Label, Tooltip, font
from utils.paths import resource_path


class Tile(ctk.CTkButton):
    """Large rounded action tile with icon, title and one-line description."""

    def __init__(self, master, th: T.Theme, title: str, desc: str, icon_name: str, command,
                 primary: bool = False, tip: str = ""):
        fg = th.primary if primary else th.surface
        hover = th.primary_hover if primary else th.surface_alt
        tc = th.on_primary if primary else th.text
        ic = th.on_primary if primary else th.icon
        super().__init__(master, text=f"{title}\n{desc}", command=command, fg_color=fg, hover_color=hover,
                         text_color=tc, corner_radius=T.RADIUS, height=104, anchor="w",
                         border_width=0 if primary else 1, border_color=th.border,
                         image=icon(icon_name, ic, 44, accent=fg), compound="left",
                         font=font(T.BODY + 1, "bold"))
        # CTkButton cannot style two text lines differently; the second line is kept short.
        self._text_label.configure(justify="left")
        if tip:
            Tooltip(self, th, tip)


class Dashboard(ctk.CTkFrame):
    def __init__(self, master, app, **_):
        super().__init__(master, fg_color="transparent")
        th = app.theme
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=T.PAD, pady=(T.PAD + 6, 6))
        header.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        Label(left, th, "Welcome to FolderLock!", "title").pack(fill="x")
        Label(left, th, "Keep your private data safe and secure.", "muted").pack(fill="x", pady=(2, 0))
        Label(left, th, "Your folders are protected with strong encryption and a password only you know.",
              "small", wraplength=480).pack(fill="x", pady=(10, 0))
        logo = Image.open(resource_path("assets/logo.png"))
        ctk.CTkLabel(header, text="", image=ctk.CTkImage(logo, logo, size=(96, 96))
                     ).grid(row=0, column=1, sticky="e", padx=(10, 0))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="nsew", padx=T.PAD, pady=(18, 8))
        self.grid_rowconfigure(1, weight=1)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="tiles")
        tiles = [
            ("Lock Folder", "Protect your folder", "lock", "lock", True,
             "Choose a folder and protect it with a password"),
            ("Unlock Folder", "Access your files", "unlock", "unlock", True,
             "Open a protected .flock file with your password"),
            ("Change Password", "Update your password", "key", "change_password", False,
             "Set a new password for an existing protected file"),
            ("Recovery Options", "Recover access", "lifebuoy", "recovery", False,
             "Use your recovery key if you forgot your password"),
        ]
        for i, (title, desc, ic, target, primary, tip) in enumerate(tiles):
            Tile(grid, th, title, desc, ic, lambda t=target: app.navigate(t), primary, tip
                 ).grid(row=i // 2, column=i % 2, sticky="nsew", padx=8, pady=8)
            grid.grid_rowconfigure(i // 2, weight=0)

        Label(self, th, "Tip: keep your recovery key in a safe place. Without your password or "
              "recovery key, protected files cannot be opened by anyone.", "small", wraplength=640
              ).grid(row=2, column=0, sticky="ew", padx=T.PAD + 8, pady=(4, 14))
