"""Recovery key display panel, Recovery Options screen and 'new recovery key' flow."""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import vault_manager as vm
from security.recovery import generate_recovery_key, recovery_file_text
from ui import theme as T
from ui.dialogs import show_message
from ui.flow import FlowScreen, path_row, pick_vault, start_dir
from ui.icons import icon
from ui.widgets import AppButton, Banner, Label, PasswordField, font
from utils.error_handler import friendly_message


class RecoveryKeyPanel(ctk.CTkFrame):
    """Shows a recovery key with Copy / Save / Print and a 'I have saved it' checkbox."""

    def __init__(self, master, app, key: str, vault_name: str, on_confirm_change=None):
        super().__init__(master, fg_color="transparent")
        th, self.app, self.key, self.vault_name = app.theme, app, key, vault_name
        self._on_change = on_confirm_change

        card = ctk.CTkFrame(self, fg_color=th.surface, corner_radius=T.RADIUS, border_width=1,
                            border_color=th.primary)
        card.pack(fill="x")
        groups = key.split("-")
        lines = ["   ".join(groups[i:i + 5]) for i in range(0, len(groups), 5)]
        Label(card, th, "YOUR RECOVERY KEY", "small").pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(card, text="\n".join(lines), font=font(16, "bold", mono=True), text_color=th.text,
                     justify="left", anchor="w").pack(fill="x", padx=18, pady=(2, 14))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(12, 0))
        self.copy_btn = AppButton(row, th, "Copy", self._copy, kind="secondary", width=110, height=40)
        self.copy_btn.pack(side="left")
        AppButton(row, th, "Save as File…", self._save, kind="secondary", width=150, height=40
                  ).pack(side="left", padx=10)
        AppButton(row, th, "Print", self._print, kind="secondary", width=100, height=40).pack(side="left")

        Label(self, th, "If you forget your password, this key is the ONLY way to open your files. "
              "FolderLock does not keep a copy and nobody can recover it for you.", "small",
              wraplength=470).pack(fill="x", pady=(12, 8))
        self.var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="I have saved my recovery key in a safe place", variable=self.var,
                        command=self._changed, font=font(T.BODY, "bold"), text_color=th.text,
                        fg_color=th.primary, hover_color=th.primary_hover, checkmark_color=th.on_primary,
                        border_color=th.muted).pack(anchor="w")

    @property
    def confirmed(self) -> bool:
        return bool(self.var.get())

    def _changed(self) -> None:
        if self._on_change:
            self._on_change(self.confirmed)

    def _copy(self) -> None:
        self.app.clipboard_clear()
        self.app.clipboard_append(self.key)
        self.copy_btn.configure(text="Copied!")
        self.after(1800, lambda: self.copy_btn.winfo_exists() and self.copy_btn.configure(text="Copy"))
        self.after(60_000, self._clear_clipboard)          # do not leave the key on the clipboard

    def _clear_clipboard(self) -> None:
        try:
            if self.app.clipboard_get() == self.key:
                self.app.clipboard_clear()
        except tk.TclError:
            pass

    def _save(self) -> None:
        target = filedialog.asksaveasfilename(
            parent=self.app, title="Save your recovery key", defaultextension=".txt",
            initialfile="FolderLock Recovery Key.txt", initialdir=start_dir(self.app),
            filetypes=[("Text file", "*.txt")])
        if not target:
            return
        try:
            Path(target).write_text(recovery_file_text(self.key, self.vault_name), encoding="utf-8")
        except OSError as exc:
            show_message(self.app, "Could not save", friendly_message(exc), "warning")
            return
        show_message(self.app, "Recovery key saved",
                     f"Saved to:\n{target}\n\nStore it somewhere safe - ideally NOT on the same "
                     "computer or USB drive as the protected file.", "success")

    def _print(self) -> None:
        if not sys.platform.startswith("win"):
            show_message(self.app, "Print", "Use “Save as File…” and print the saved file.", "info")
            return
        try:
            path = Path(tempfile.mkdtemp()) / "FolderLock Recovery Key.txt"
            path.write_text(recovery_file_text(self.key, self.vault_name), encoding="utf-8")
            os.startfile(str(path), "print")                  # type: ignore[attr-defined]
        except OSError:
            show_message(self.app, "Could not print",
                         "Please use “Save as File…” and print the saved file instead.", "warning")


class _OptionRow(ctk.CTkButton):
    def __init__(self, master, th: T.Theme, title: str, desc: str, icon_name: str, command):
        super().__init__(master, text=f"{title}\n{desc}", command=command, fg_color=th.surface,
                         hover_color=th.surface_alt, text_color=th.text, corner_radius=T.RADIUS,
                         height=84, anchor="w", border_width=1, border_color=th.border,
                         image=icon(icon_name, th.icon, 38, accent=th.surface), compound="left",
                         font=font(T.BODY, "bold"))
        self._text_label.configure(justify="left")


class RecoveryScreen(FlowScreen):
    def __init__(self, master, app, **_):
        super().__init__(master, app)
        th = self.th
        inner = self.start_step("Recovery Options", "Get back into your files if you forgot your password.",
                                hero="lifebuoy")
        for title, desc, ic, target, kw in (
            ("Open my files with the recovery key", "Unlock a protected file without the password",
             "unlock", "unlock", {"mode": "recovery"}),
            ("Set a new password with the recovery key", "Forgot your password? Choose a new one",
             "key", "change_password", {"mode": "reset"}),
            ("Create a new recovery key", "Replace your recovery key (the old one stops working)",
             "lifebuoy", "new_recovery_key", {}),
        ):
            _OptionRow(inner, th, title, desc, ic, lambda t=target, k=kw: self.app.navigate(t, **k)
                       ).pack(fill="x", pady=5)
        Banner(inner, th, "If you lose BOTH your password and your recovery key, your files cannot be "
               "recovered by anyone. FolderLock has no hidden backdoor or master password.",
               "info", 520).pack(fill="x", pady=(14, 0))
        self.buttons(inner, back=self.go_home, back_text="Back")


class NewRecoveryKeyScreen(FlowScreen):
    def __init__(self, master, app, **_):
        super().__init__(master, app)
        self.vault: Path | None = None
        self.password = ""
        self.new_key = ""
        self.select_step()

    def select_step(self) -> None:
        th = self.th
        inner = self.start_step("New Recovery Key",
                                "Choose the protected file and enter its password. You will then get a "
                                "new recovery key; the old one will stop working.", hero="lifebuoy")
        if self.vault:
            path_row(inner, th, self.vault.name, "vault").pack(fill="x", pady=(0, 10))
        AppButton(inner, th, "Choose Protected File…" if not self.vault else "Choose a Different File…",
                  self._choose, kind="secondary" if self.vault else "primary", width=290,
                  icon_name="folder").pack(anchor="w")
        self.pw = PasswordField(inner, th, "Enter password", on_enter=self._check)
        self.pw.pack(fill="x", pady=(14, 0))
        self.msg = ctk.CTkFrame(inner, fg_color="transparent")
        self.msg.pack(fill="x")
        self.buttons(inner, back=self.go_home, back_text="Cancel", on_next=self._check, next_text="Continue",
                     next_enabled=bool(self.vault))

    def _choose(self) -> None:
        picked = pick_vault(self.app)
        if picked:
            self.vault = picked
            self.select_step()

    def _check(self) -> None:
        if not self.vault:
            return
        password = self.pw.get()
        for w in self.msg.winfo_children():
            w.destroy()

        def job(_p, _c):
            vm.unlock_with_password(self.vault, password)
            return True

        def ok(_):
            self.password, self.new_key = password, generate_recovery_key()
            self.key_step()

        def fail(_e, message):
            self.error_banner(self.msg, message)

        self.app.runner.run(job, on_success=ok, on_error=fail)

    def key_step(self) -> None:
        th = self.th
        inner = self.start_step("Your New Recovery Key", "Save this key now. It replaces the old one only "
                                "after you confirm below.", hero="lifebuoy")
        self.panel = RecoveryKeyPanel(inner, self.app, self.new_key, self.vault.name, self._confirmed)
        self.panel.pack(fill="x")
        self.msg2 = ctk.CTkFrame(inner, fg_color="transparent")
        self.msg2.pack(fill="x")
        self.apply_btn = self.buttons(inner, back=self.go_home, back_text="Cancel", on_next=self._apply,
                                      next_text="Use This Key", next_enabled=False)

    def _confirmed(self, ok: bool) -> None:
        self.apply_btn.configure(state="normal" if ok else "disabled")

    def _apply(self) -> None:
        self.apply_btn.configure(state="disabled", text="Working…")
        vault, password, key = self.vault, self.password, self.new_key

        def job(_p, _c):
            vm.replace_recovery_key(vault, password, key)

        def ok(_):
            self.password = ""
            show_message(self.app, "Recovery Key Updated",
                         "Your new recovery key is active. The previous key no longer works.", "success")
            self.go_home()

        def fail(_e, message):
            self.apply_btn.configure(state="normal", text="Use This Key")
            self.error_banner(self.msg2, message)

        self.app.runner.run(job, on_success=ok, on_error=fail)
