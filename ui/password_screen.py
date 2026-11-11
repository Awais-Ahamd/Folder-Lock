"""Password entry components and the Change Password / Reset Password screen."""
from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from core import vault_manager as vm
from security.password_manager import validate_new_password
from ui import theme as T
from ui.dialogs import show_message
from ui.flow import FlowScreen, path_row, pick_vault
from ui.widgets import AppButton, Label, PasswordField, StrengthMeter


class PasswordPair(ctk.CTkFrame):
    """Enter + confirm fields with a live strength meter (mockup: 'Set Password')."""

    def __init__(self, master, th: T.Theme, on_enter=None, enter_label: str = "Enter password",
                 confirm_label: str = "Confirm password", on_edit=None):
        super().__init__(master, fg_color="transparent")
        self.th = th
        self._on_edit = on_edit
        self.meter = StrengthMeter(self, th)
        self.first = PasswordField(self, th, enter_label, on_change=self._changed)
        self.first.pack(fill="x")
        self.second = PasswordField(self, th, confirm_label, on_enter=on_enter, on_change=self._changed)
        self.second.pack(fill="x", pady=(10, 12))
        self.meter.pack(fill="x")

    def _changed(self) -> None:
        self.meter.update_for(self.first.get())
        if self._on_edit:
            self._on_edit()

    def validate(self) -> tuple[str | None, str | None]:
        """Return ``(password, None)`` or ``(None, friendly error message)``."""
        pw = self.first.get()
        error = validate_new_password(pw, self.second.get())
        return (None, error) if error else (pw, None)

    def clear(self) -> None:
        self.first.clear()
        self.second.clear()

    def focus(self) -> None:
        self.first.focus()


class ChangePasswordScreen(FlowScreen):
    """mode='change' (needs the current password) or 'reset' (needs the recovery key)."""

    def __init__(self, master, app, mode: str = "change", **_):
        super().__init__(master, app)
        self.mode = mode
        self.vault: Path | None = None
        self.select_step()

    # ---------------------------------------------------------------- step 1
    def select_step(self) -> None:
        th = self.th
        inner = self.start_step(
            "Change Password" if self.mode == "change" else "Set a New Password",
            "Choose the protected file (.flock) whose password you want to change."
            if self.mode == "change" else
            "Forgot your password? Choose the protected file and use your recovery key to set a new one.",
            hero="key")
        if self.vault:
            path_row(inner, th, str(self.vault), "vault").pack(fill="x")
        AppButton(inner, th, "Choose Protected File…" if not self.vault else "Choose a Different File…",
                  self._choose, kind="primary" if not self.vault else "secondary",
                  width=290, icon_name="folder").pack(anchor="w", pady=(12, 0))
        self.buttons(inner, back=self.go_home, back_text="Cancel", on_next=self.form_step,
                     next_enabled=bool(self.vault))

    def _choose(self) -> None:
        picked = pick_vault(self.app)
        if picked:
            self.vault = picked
            self.select_step()

    # ---------------------------------------------------------------- step 2
    def form_step(self) -> None:
        th = self.th
        change = self.mode == "change"
        inner = self.start_step(
            "Change Password" if change else "Set a New Password",
            "Enter your current password, then choose a new one." if change else
            "Type your recovery key, then choose a new password.", hero="key")
        path_row(inner, th, self.vault.name, "vault").pack(fill="x", pady=(0, 12))
        self.current = PasswordField(
            inner, th, "Current password" if change else "Recovery key (XXXX-XXXX-…)",
            leading_icon="lock" if change else "key", secret=change)
        self.current.pack(fill="x")
        Label(inner, th, "New password", "bold").pack(fill="x", pady=(14, 6))
        self.pair = PasswordPair(inner, th, on_enter=self._apply, enter_label="Enter new password",
                                 confirm_label="Confirm new password", on_edit=lambda: self._message(""))
        self.pair.pack(fill="x")
        self.msg_holder = ctk.CTkFrame(inner, fg_color="transparent")
        self.msg_holder.pack(fill="x")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(18, 0))
        self.apply_btn = AppButton(row, th, "Change Password" if change else "Set Password",
                                   self._apply, width=190)
        self.apply_btn.pack(side="right")
        AppButton(row, th, "Back", self.select_step, kind="secondary", width=110).pack(side="right", padx=12)
        link = ctk.CTkButton(row, text="Forgot password? Use recovery key" if change else "I remember my password",
                             fg_color="transparent", hover_color=th.surface_alt, text_color=th.icon,
                             font=ctk.CTkFont(size=T.SMALL, underline=True), width=10, command=self._toggle_mode)
        link.pack(side="left")
        self.current.focus()

    def _toggle_mode(self) -> None:
        self.mode = "reset" if self.mode == "change" else "change"
        self.form_step()

    def _message(self, text: str) -> None:
        for w in self.msg_holder.winfo_children():
            w.destroy()
        if text:
            self.error_banner(self.msg_holder, text)

    def _apply(self) -> None:
        secret = self.current.get()
        if not secret.strip():
            self._message("Please enter your current password." if self.mode == "change"
                          else "Please enter your recovery key.")
            return
        new_pw, error = self.pair.validate()
        if error:
            self._message(error)
            return
        self._message("")
        self.apply_btn.configure(state="disabled", text="Working…")
        vault, mode = self.vault, self.mode

        def job(_progress, _cancel):
            if mode == "change":
                vm.change_password(vault, secret, new_pw)
            else:
                vm.reset_password_with_recovery_key(vault, secret, new_pw)

        def ok(_):
            self.pair.clear()
            self.current.clear()
            show_message(self.app, "Password Changed",
                         "Your new password is ready to use. Your files were not touched.",
                         "success",
                         "Tip: copies of this vault made before the change can still be opened "
                         "with the old password.")
            self.go_home()

        def fail(_exc, message):
            self.apply_btn.configure(state="normal", text="Change Password" if mode == "change" else "Set Password")
            self._message(message)

        self.app.runner.run(job, on_success=ok, on_error=fail)
