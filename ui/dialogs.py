"""Themed modal dialogs (message, confirm) and the first-run welcome guide."""
from __future__ import annotations

import sys
import tkinter as tk

import customtkinter as ctk

from ui import theme as T
from ui.icons import icon
from ui.widgets import AppButton, Label, font
from utils.paths import resource_path


class Modal(ctk.CTkToplevel):
    def __init__(self, app, title: str, width: int = 480):
        th = app.theme
        super().__init__(app, fg_color=th.bg)
        self.app, self.th, self.result = app, th, False
        self.title(title)
        self.resizable(False, False)
        self.transient(app)
        self._width = width
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        if sys.platform.startswith("win"):           # CTkToplevel resets the icon after 200 ms
            self.after(250, self._set_icon)

    def _set_icon(self) -> None:
        try:
            self.iconbitmap(str(resource_path("assets/icon.ico")))
        except tk.TclError:
            pass

    def show(self) -> None:
        self.update_idletasks()
        w, h = self._width, max(self.winfo_reqheight(), 150)
        x = self.app.winfo_rootx() + (self.app.winfo_width() - w) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - h) // 3
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_set()
        self.wait_window()

    def _close(self, result: bool = False) -> None:
        self.result = result
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def _dialog(app, title: str, message: str, icon_name: str, buttons: list[tuple[str, bool, str]],
            detail: str = "") -> bool:
    th = app.theme
    dlg = Modal(app, title)
    body = ctk.CTkFrame(dlg, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=T.PAD, pady=T.PAD)
    head = ctk.CTkFrame(body, fg_color="transparent")
    head.pack(fill="x")
    color = th.success if icon_name == "check" else th.icon
    ctk.CTkLabel(head, text="", image=icon(icon_name, color, 36, accent=th.bg)).pack(side="left", padx=(0, 14))
    Label(head, th, title, "heading", wraplength=360).pack(side="left", fill="x", expand=True)
    Label(body, th, message, "body", wraplength=430).pack(fill="x", pady=(14, 0))
    if detail:
        Label(body, th, detail, "small", wraplength=430).pack(fill="x", pady=(8, 0))
    row = ctk.CTkFrame(body, fg_color="transparent")
    row.pack(fill="x", pady=(20, 0))
    for text, result, kind in reversed(buttons):
        AppButton(row, th, text, lambda r=result: dlg._close(r), kind=kind,
                  width=140 if len(text) < 14 else 190).pack(side="right", padx=(10, 0))
    dlg.show()
    return dlg.result


def show_message(app, title: str, message: str, kind: str = "info", detail: str = "") -> None:
    icon_name = {"success": "check", "warning": "warning", "error": "warning"}.get(kind, "info")
    _dialog(app, title, message, icon_name, [("OK", True, "primary")], detail)


def ask_confirm(app, title: str, message: str, yes: str = "Continue", no: str = "Cancel",
                detail: str = "") -> bool:
    return _dialog(app, title, message, "warning", [(no, False, "secondary"), (yes, True, "primary")], detail)


# --------------------------------------------------------------------------- #
class LockDemo(ctk.CTkFrame):
    """A small picture showing what locking and unlocking do."""

    def __init__(self, master, th: T.Theme):
        super().__init__(master, fg_color=th.surface, corner_radius=T.RADIUS, border_width=1,
                         border_color=th.border)
        for row, (label, left, right, caption) in enumerate((
                ("Lock", ("folder", "Your folder"), ("lock", "One protected file"), "needs your password to open"),
                ("Unlock", ("lock", "Protected file"), ("folder", "Your folder"), "restored exactly as it was"))):
            line = ctk.CTkFrame(self, fg_color="transparent")
            line.pack(fill="x", padx=18, pady=(14 if row == 0 else 4, 14 if row == 1 else 4))
            Label(line, th, label, "bold", width=64).pack(side="left")
            for i, (name, text) in enumerate((left, right)):
                cell = ctk.CTkFrame(line, fg_color=th.surface_alt, corner_radius=T.RADIUS_SMALL)
                cell.pack(side="left", padx=4)
                ctk.CTkLabel(cell, text=text, image=icon(name, th.icon, 28, accent=th.surface_alt),
                             compound="top", font=font(T.SMALL), text_color=th.text, width=130
                             ).pack(padx=6, pady=8)
                if i == 0:
                    ctk.CTkLabel(line, text="", image=icon("arrow", th.success, 28, accent=th.surface)
                                 ).pack(side="left", padx=2)
            Label(line, th, caption, "small", wraplength=130).pack(side="left", padx=10)


def show_welcome(app) -> None:
    th = app.theme
    pages = [
        ("Welcome to FolderLock",
         "FolderLock protects your private folders with a password. Everything works on this "
         "computer only - no internet and no account are needed.", None),
        ("Locking and unlocking",
         "Locking turns a folder into one protected file (ending in .flock). "
         "Unlocking with your password gives you the folder back, exactly as it was.", "demo"),
        ("Keep your recovery key safe",
         "When you lock a folder you also get a recovery key. If you ever forget your password, "
         "the recovery key is the only way back in. Save it somewhere safe - nobody, including "
         "us, can open your files without your password or recovery key.", None),
    ]
    dlg = Modal(app, "Welcome", width=560)
    body = ctk.CTkFrame(dlg, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=T.PAD, pady=T.PAD)
    state = {"i": 0}

    def render() -> None:
        for child in body.winfo_children():
            child.destroy()
        title, text, extra = pages[state["i"]]
        ctk.CTkLabel(body, text="", image=icon("lock", th.icon, 44, accent=th.bg)).pack(anchor="w")
        Label(body, th, title, "title", wraplength=500).pack(fill="x", pady=(10, 6))
        Label(body, th, text, "muted", wraplength=500).pack(fill="x")
        if extra == "demo":
            LockDemo(body, th).pack(fill="x", pady=(14, 0))
        Label(body, th, f"Step {state['i'] + 1} of {len(pages)}", "small").pack(fill="x", pady=(16, 0))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(8, 0))
        last = state["i"] == len(pages) - 1
        AppButton(row, th, "Get Started" if last else "Next", (dlg._close if last else advance),
                  width=150).pack(side="right")
        if state["i"] > 0:
            AppButton(row, th, "Back", back, kind="secondary", width=110).pack(side="right", padx=10)
        dlg.geometry("")
        dlg.update_idletasks()

    def advance() -> None:
        state["i"] += 1
        render()

    def back() -> None:
        state["i"] -= 1
        render()

    render()
    dlg.show()
