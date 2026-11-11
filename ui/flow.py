"""Shared base for multi-step screens plus native file/folder pickers."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import vault_manager as vm
from ui import theme as T
from ui.dialogs import show_message
from ui.icons import icon
from ui.widgets import AppButton, Banner, Label, page_header
from utils.error_handler import FolderLockError, friendly_message
from utils.paths import default_start_dir


class FlowScreen(ctk.CTkFrame):
    """A screen whose ``body`` is rebuilt for each step."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app, self.th = app, app.theme
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=0, column=0, sticky="nsew", padx=T.PAD + 8, pady=T.PAD)

    # -- building blocks
    def clear(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()

    def start_step(self, title: str, subtitle: str = "", hero: str | None = None) -> ctk.CTkFrame:
        """Clear the body and lay out a hero icon (left) and a content column (right)."""
        self.clear()
        th = self.th
        self.body.grid_columnconfigure(1, weight=1)
        if hero:
            side = ctk.CTkFrame(self.body, fg_color="transparent", width=120)
            side.grid(row=0, column=0, sticky="n", padx=(0, 26), pady=(6, 0))
            ctk.CTkLabel(side, text="", image=icon(hero, th.icon, 84, accent=th.bg)).pack()
        col = ctk.CTkFrame(self.body, fg_color="transparent")
        col.grid(row=0, column=1, sticky="nsew")
        col.grid_columnconfigure(0, weight=1)
        page_header(col, th, title, subtitle)
        inner = ctk.CTkFrame(col, fg_color="transparent")
        inner.pack(fill="both", expand=True, pady=(16, 0))
        return inner

    def buttons(self, parent, *, back=None, back_text="Back", next_text="Next", on_next=None,
                next_enabled: bool = True, next_icon: str | None = None, width: int = 150) -> AppButton | None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(22, 0))
        nxt = None
        if on_next:
            nxt = AppButton(row, self.th, next_text, on_next, width=width, icon_name=next_icon)
            nxt.pack(side="right")
            if not next_enabled:
                nxt.configure(state="disabled")
        if back:
            AppButton(row, self.th, back_text, back, kind="secondary", width=120
                      ).pack(side="right", padx=(0, 12))
        return nxt

    def error_banner(self, parent, text: str, icon_name: str = "warning") -> Banner:
        banner = Banner(parent, self.th, text, icon_name)
        banner.pack(fill="x", pady=(12, 0))
        return banner

    def go_home(self) -> None:
        self.app.show("dashboard")


# --------------------------------------------------------------------------- #
def start_dir(app) -> str:
    saved = app.settings.get("default_destination")
    return saved if saved and Path(saved).is_dir() else default_start_dir()


def pick_vault(app) -> Path | None:
    """Native file dialog for .flock files, then a quick format check."""
    chosen = filedialog.askopenfilename(
        parent=app, title="Choose a FolderLock vault", initialdir=start_dir(app),
        filetypes=[("FolderLock vault", "*.flock"), ("All files", "*.*")])
    if not chosen:
        return None
    path = Path(chosen)
    try:
        vm.inspect_vault(path)
    except FolderLockError as exc:
        show_message(app, "This file cannot be opened", exc.user_message, "warning")
        return None
    except OSError as exc:
        show_message(app, "This file cannot be opened", friendly_message(exc), "warning")
        return None
    return path


def pick_folder(app, title: str, initial: str | None = None) -> Path | None:
    chosen = filedialog.askdirectory(parent=app, title=title, initialdir=initial or start_dir(app),
                                     mustexist=True)
    return Path(chosen) if chosen else None


def reveal_in_explorer(path: Path) -> None:
    """Open the containing folder (selecting the item on Windows)."""
    try:
        if sys.platform.startswith("win"):
            if path.is_dir():
                os.startfile(str(path))                      # type: ignore[attr-defined]
            else:
                subprocess.Popen(["explorer", "/select,", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path if path.is_dir() else path.parent)])
        else:
            subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])
    except OSError:
        pass


def success_badge(parent, th: T.Theme, size: int = 92) -> ctk.CTkLabel:
    """Emerald circle with a white check (as in the 'Folder Locked Successfully' mockup)."""
    from PIL import Image, ImageDraw
    ss = 6
    px = size * ss
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, px - 1, px - 1], fill=th.success)
    pts = [(0.27 * px, 0.52 * px), (0.43 * px, 0.68 * px), (0.74 * px, 0.34 * px)]
    d.line(pts, fill="#FFFFFF", width=int(0.085 * px), joint="curve")
    for x, y in (pts[0], pts[-1]):                     # round line caps
        r = 0.0425 * px
        d.ellipse([x - r, y - r, x + r, y + r], fill="#FFFFFF")
    img = img.resize((size, size), Image.LANCZOS)
    return ctk.CTkLabel(parent, text="", image=ctk.CTkImage(img, img, size=(size, size)))


def path_row(parent, th: T.Theme, path_text: str, icon_name: str = "folder") -> ctk.CTkFrame:
    """Read-only rounded path box like 'D:\\MyPrivateData' in the mockup."""
    row = ctk.CTkFrame(parent, fg_color=th.surface_alt, corner_radius=T.RADIUS_SMALL,
                       border_width=1, border_color=th.border)
    ctk.CTkLabel(row, text="", image=icon(icon_name, th.muted, 18, accent=th.surface_alt)
                 ).pack(side="left", padx=(12, 6), pady=10)
    Label(row, th, path_text, "body", wraplength=420).pack(side="left", fill="x", expand=True, padx=(0, 12))
    return row
