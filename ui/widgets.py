"""Reusable themed widgets shared by all screens."""
from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from security.password_manager import check_password
from ui import theme as T
from ui.icons import icon


def font(size: int = T.BODY, weight: str = "normal", mono: bool = False) -> ctk.CTkFont:
    return ctk.CTkFont(family=T.mono_family() if mono else T.font_family(), size=size, weight=weight)


# --------------------------------------------------------------------------- #
class Card(ctk.CTkFrame):
    def __init__(self, master, th: T.Theme, **kw):
        kw.setdefault("corner_radius", T.RADIUS)
        kw.setdefault("fg_color", th.surface)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", th.border)
        super().__init__(master, **kw)


class Label(ctk.CTkLabel):
    """Label with the theme's heading / body / muted looks."""

    def __init__(self, master, th: T.Theme, text: str = "", kind: str = "body", **kw):
        styles = {
            "title": dict(size=T.TITLE, weight="bold", color=th.text),
            "heading": dict(size=T.HEADING, weight="bold", color=th.text),
            "body": dict(size=T.BODY, weight="normal", color=th.text),
            "muted": dict(size=T.BODY, weight="normal", color=th.muted),
            "small": dict(size=T.SMALL, weight="normal", color=th.muted),
            "success": dict(size=T.BODY, weight="bold", color=th.success_text),
            "bold": dict(size=T.BODY, weight="bold", color=th.text),
        }[kind]
        kw.setdefault("font", font(styles["size"], styles["weight"]))
        kw.setdefault("text_color", styles["color"])
        kw.setdefault("anchor", "w")
        kw.setdefault("justify", "left")
        super().__init__(master, text=text, **kw)


class AppButton(ctk.CTkFrame):
    """Rounded button with a subtle raised edge. kind: primary | secondary | ghost."""

    def __init__(self, master, th: T.Theme, text: str, command: Callable | None = None,
                 kind: str = "primary", icon_name: str | None = None, width: int = 150,
                 height: int = 44, tooltip: str | None = None):
        super().__init__(master, fg_color="transparent", corner_radius=0, width=width, height=height + 3)
        self.th, self.kind = th, kind
        if kind != "ghost":      # subtle raised edge: a darker rounded layer offset 3px below the button
            ctk.CTkFrame(self, fg_color=th.shadow, corner_radius=T.RADIUS_SMALL + 2, width=width,
                         height=height).place(x=0, y=3)
        if kind == "primary":
            fg, hover, tc, border = th.primary, th.primary_hover, th.on_primary, 0
        elif kind == "secondary":
            fg, hover, tc, border = th.surface_alt, th.border, th.text, 1
        else:
            fg, hover, tc, border = "transparent", th.surface_alt, th.primary if th.name != "Light" else th.icon, 0
        self._tc = tc
        img = None
        if icon_name:
            ic = tc if kind != "secondary" else th.icon
            img = icon(icon_name, ic, 20, accent=fg if fg != "transparent" else th.bg)
        self.button = ctk.CTkButton(
            self, text=text, command=command, width=width, height=height,
            corner_radius=T.RADIUS_SMALL + 2, fg_color=fg, hover_color=hover, text_color=tc,
            text_color_disabled=th.muted, border_width=border, border_color=th.border,
            font=font(T.BUTTON, "bold"), image=img, compound="left")
        self.button.place(x=0, y=0)
        self.pack_propagate(False)
        self.grid_propagate(False)
        if tooltip:
            Tooltip(self.button, th, tooltip)

    def configure(self, require_redraw=False, **kw):  # noqa: D401
        inner = {k: kw.pop(k) for k in ("state", "text", "command") if k in kw}
        if inner:
            self.button.configure(**inner)
        if kw:
            super().configure(require_redraw=require_redraw, **kw)


class PasswordField(ctk.CTkFrame):
    """Rounded password box with a lock icon and a show/hide eye (as in the mockup)."""

    def __init__(self, master, th: T.Theme, placeholder: str = "Enter password",
                 on_change: Callable[[], None] | None = None, on_enter: Callable[[], None] | None = None,
                 leading_icon: str = "lock", secret: bool = True):
        super().__init__(master, fg_color=th.surface_alt, corner_radius=T.RADIUS_SMALL,
                         border_width=1, border_color=th.border, height=46)
        self.th = th
        self._shown = not secret
        self.var = tk.StringVar()
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text="", image=icon(leading_icon, th.muted, 18, accent=th.surface_alt)
                     ).grid(row=0, column=0, padx=(12, 4), pady=6)
        self.entry = ctk.CTkEntry(self, textvariable=self.var, placeholder_text=placeholder,
                                  show="" if self._shown else "•", border_width=0,
                                  fg_color="transparent", text_color=th.text,
                                  placeholder_text_color=th.muted, height=38, font=font(T.BODY))
        self.entry.grid(row=0, column=1, sticky="ew", padx=2, pady=4)
        self.eye = ctk.CTkButton(self, text="", width=34, height=34, fg_color="transparent",
                                 hover_color=th.border, corner_radius=8, command=self.toggle,
                                 image=icon("eye_off" if secret else "eye", th.muted, 20, accent=th.surface_alt))
        self.eye.grid(row=0, column=2, padx=(2, 8))
        if secret:
            Tooltip(self.eye, th, "Show or hide what you type")
        else:
            self.eye.grid_remove()
        if on_change:
            self.var.trace_add("write", lambda *_: on_change())
        if on_enter:
            self.entry.bind("<Return>", lambda _e: on_enter())

    def toggle(self) -> None:
        self._shown = not self._shown
        self.entry.configure(show="" if self._shown else "•")
        self.eye.configure(image=icon("eye" if self._shown else "eye_off", self.th.muted, 20,
                                      accent=self.th.surface_alt))

    def get(self) -> str:
        return self.var.get()

    def clear(self) -> None:
        self.var.set("")

    def focus(self) -> None:
        self.entry.focus_set()


class StrengthMeter(ctk.CTkFrame):
    def __init__(self, master, th: T.Theme):
        super().__init__(master, fg_color="transparent")
        self.th = th
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        Label(row, th, "Password Strength:", "small").pack(side="left")
        self.bar = ctk.CTkProgressBar(row, width=170, height=10, corner_radius=5,
                                      fg_color=th.surface_alt, progress_color=th.muted)
        self.bar.set(0)
        self.bar.pack(side="left", padx=12)
        self.level = Label(row, th, "", "bold")
        self.level.pack(side="left")
        self.advice = Label(self, th, "", "small", wraplength=420)
        self.advice.pack(fill="x", pady=(4, 0))

    def update_for(self, password: str) -> None:
        r = check_password(password)
        color = self.th.muted if r.score <= 1 else (self.th.primary if r.score < 4 else self.th.success)
        self.bar.configure(progress_color=color)
        self.bar.set(r.fraction if password else 0)
        self.level.configure(text=r.label, text_color=self.th.success_text if r.score == 4 else self.th.text)
        self.advice.configure(text=r.advice if password else "")


class Banner(ctk.CTkFrame):
    """Information / warning strip (neutral surface with an icon - no extra accent colours)."""

    def __init__(self, master, th: T.Theme, text: str, icon_name: str = "warning", wraplength: int = 460):
        super().__init__(master, fg_color=th.surface_alt, corner_radius=T.RADIUS_SMALL,
                         border_width=1, border_color=th.border)
        ctk.CTkLabel(self, text="", image=icon(icon_name, th.icon, 22, accent=th.surface_alt)
                     ).pack(side="left", padx=(12, 8), pady=10)
        self.label = ctk.CTkLabel(self, text=text, font=font(T.SMALL + 1), text_color=th.text,
                                  justify="left", anchor="w", wraplength=wraplength)
        self.label.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=10)

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)


class ProgressPanel(ctk.CTkFrame):
    """Progress bar + current-operation text + safe Cancel button."""

    def __init__(self, master, th: T.Theme, on_cancel: Callable[[], None]):
        super().__init__(master, fg_color="transparent")
        self.th = th
        self.title = Label(self, th, "Working…", "heading")
        self.title.pack(fill="x")
        self.status = Label(self, th, "Starting…", "muted", wraplength=460)
        self.status.pack(fill="x", pady=(4, 14))
        self.bar = ctk.CTkProgressBar(self, height=14, corner_radius=7, fg_color=th.surface_alt,
                                      progress_color=th.primary)
        self.bar.set(0)
        self.bar.pack(fill="x")
        self.percent = Label(self, th, "0%", "small")
        self.percent.pack(fill="x", pady=(6, 14))
        self.cancel_btn = AppButton(self, th, "Cancel", on_cancel, kind="secondary", width=120)
        self.cancel_btn.pack(anchor="w")
        Label(self, th, "Cancelling is safe: your original files are never changed.", "small"
              ).pack(fill="x", pady=(8, 0))

    def set(self, status: str, fraction: float, title: str | None = None) -> None:
        if title:
            self.title.configure(text=title)
        self.status.configure(text=status)
        fraction = max(0.0, min(1.0, fraction))
        self.bar.set(fraction)
        self.percent.configure(text=f"{int(fraction * 100)}%")


class Tooltip:
    """Small hover tip for non-technical users."""

    def __init__(self, widget, th: T.Theme, text: str, delay: int = 500):
        self.widget, self.th, self.text, self.delay = widget, th, text, delay
        self._tip: tk.Toplevel | None = None
        self._job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None) -> None:
        self._cancel()
        self._job = self.widget.after(self.delay, self._show)

    def _cancel(self) -> None:
        if self._job:
            self.widget.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        if self._tip or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self.text, bg=self.th.surface_alt, fg=self.th.text,
                 relief="solid", borderwidth=1, padx=8, pady=4,
                 font=(T.font_family(), T.SMALL)).pack()

    def _hide(self, _e=None) -> None:
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


def page_header(master, th: T.Theme, title: str, subtitle: str = "") -> None:
    Label(master, th, title, "title").pack(fill="x")
    if subtitle:
        Label(master, th, subtitle, "muted", wraplength=520).pack(fill="x", pady=(4, 0))


def format_size(n: int) -> str:
    size = float(n)
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "bytes" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} bytes"
