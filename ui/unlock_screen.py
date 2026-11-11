"""Unlock Folder workflow.

    choose vault (skipped when a .flock file was double-clicked)
      -> ONE screen: password + "restore into" location (defaults to the vault's own folder)
      -> restore with progress -> done
"""
from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from core import vault_manager as vm
from ui import theme as T
from ui.dialogs import show_message
from ui.flow import (
    FlowScreen, path_row, pick_folder, pick_vault, reveal_in_explorer, success_badge,
)
from ui.icons import icon
from ui.widgets import AppButton, Label, PasswordField, ProgressPanel, format_size
from utils.error_handler import OperationCancelled


class UnlockScreen(FlowScreen):
    def __init__(self, master, app, mode: str = "password", vault: Path | str | None = None, **_):
        super().__init__(master, app)
        self.mode = mode                       # "password" | "recovery"
        self.vault: Path | None = Path(vault) if vault else None
        self.dest: Path | None = None
        self.restored: Path | None = None
        self.root_name = ""
        if self.vault:
            self.credential_step()             # double-clicked file: go straight to the password
        else:
            self.select_step()

    # ------------------------------------------------------------ destination default
    def default_destination(self) -> Path:
        """Saved default if the user set one, otherwise the folder that holds the vault."""
        saved = self.app.settings.get("default_destination")
        if saved and Path(saved).is_dir():
            return Path(saved)
        return self.vault.parent

    # ------------------------------------------------------------ 1. choose vault
    def select_step(self) -> None:
        th = self.th
        inner = self.start_step("Unlock Folder", "Choose the protected file (.flock) you want to open.",
                                hero="unlock")
        if self.vault:
            path_row(inner, th, str(self.vault), "vault").pack(fill="x")
            Label(inner, th, f"Size: {format_size(self.vault.stat().st_size)}", "small"
                  ).pack(fill="x", pady=(6, 0))
        AppButton(inner, th, "Choose Protected File…" if not self.vault else "Choose a Different File…",
                  self._choose, kind="primary" if not self.vault else "secondary", width=290,
                  icon_name="folder").pack(anchor="w", pady=(14, 0))
        self.buttons(inner, back=self.go_home, back_text="Cancel", on_next=self._to_credentials,
                     next_enabled=bool(self.vault))

    def _choose(self) -> None:
        picked = pick_vault(self.app)
        if picked:
            self.vault = picked
            self.dest = None
            self.select_step()

    def _to_credentials(self) -> None:
        self.dest = None
        self.credential_step()

    # ------------------------------------------------------------ 2. password + destination
    def credential_step(self) -> None:
        th = self.th
        pw = self.mode == "password"
        if self.dest is None:
            self.dest = self.default_destination()
        inner = self.start_step("Unlock Folder",
                                "Enter your password to unlock the folder." if pw else
                                "Enter your recovery key to unlock the folder.", hero="unlock")
        path_row(inner, th, self.vault.name, "vault").pack(fill="x", pady=(0, 12))
        self.field = PasswordField(inner, th, "Enter password" if pw else "Recovery key (XXXX-XXXX-…)",
                                   on_enter=self._unlock, leading_icon="lock" if pw else "key", secret=pw)
        self.field.pack(fill="x")

        Label(inner, th, "Restore your folder into:", "small").pack(fill="x", pady=(16, 4))
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        box = ctk.CTkFrame(row, fg_color=th.surface_alt, corner_radius=T.RADIUS_SMALL, border_width=1,
                           border_color=th.border)
        box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(box, text="", image=icon("folder", th.muted, 18, accent=th.surface_alt)
                     ).pack(side="left", padx=(12, 6), pady=9)
        self.dest_label = Label(box, th, str(self.dest), "body", wraplength=330)
        self.dest_label.pack(side="left", fill="x", expand=True, padx=(0, 12))
        AppButton(row, th, "Change…", self._change_dest, kind="secondary", width=100, height=40
                  ).pack(side="left", padx=(10, 0))

        self.msg = ctk.CTkFrame(inner, fg_color="transparent")
        self.msg.pack(fill="x")
        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(fill="x", pady=(20, 0))
        self.unlock_btn = AppButton(btns, th, "Unlock", self._unlock, width=150, icon_name="unlock")
        self.unlock_btn.pack(side="right")
        AppButton(btns, th, "Cancel", self.go_home, kind="secondary", width=110).pack(side="right", padx=12)
        ctk.CTkButton(btns, text="Forgot password? Use recovery key" if pw else "Use my password instead",
                      fg_color="transparent", hover_color=th.surface_alt, text_color=th.icon, width=10,
                      font=ctk.CTkFont(size=T.SMALL, underline=True), command=self._toggle).pack(side="left")
        self.field.focus()

    def _change_dest(self) -> None:
        picked = pick_folder(self.app, "Choose where to restore your files", str(self.dest))
        if picked:
            self.dest = picked
            self.dest_label.configure(text=str(picked))

    def _toggle(self) -> None:
        self.mode = "recovery" if self.mode == "password" else "password"
        self.credential_step()

    def _unlock(self) -> None:
        secret = self.field.get()
        for w in self.msg.winfo_children():
            w.destroy()
        if not secret.strip():
            self.error_banner(self.msg, "Please enter your password." if self.mode == "password"
                              else "Please enter your recovery key.")
            return
        self.unlock_btn.configure(state="disabled", text="Unlocking…")
        vault, mode = self.vault, self.mode

        def job(_p, _c):
            keys = (vm.unlock_with_password(vault, secret) if mode == "password"
                    else vm.unlock_with_recovery_key(vault, secret))
            return keys, vm.peek_root_name(vault, keys)

        def ok(result):
            keys, self.root_name = result
            self.field.clear()
            self.start_restore(keys)

        def fail(_e, message):
            self.unlock_btn.configure(state="normal", text="Unlock")
            self.field.clear()
            self.field.focus()
            self.error_banner(self.msg, message)

        self.app.runner.run(job, on_success=ok, on_error=fail)

    # ------------------------------------------------------------ 3. restore
    def start_restore(self, keys: vm.VaultKeys) -> None:
        self.clear()
        th = self.th
        self.body.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self.body, text="", image=icon("unlock", th.icon, 84, th.bg)
                     ).grid(row=0, column=0, sticky="n", padx=(0, 26), pady=(6, 0))
        holder = ctk.CTkFrame(self.body, fg_color="transparent")
        holder.grid(row=0, column=1, sticky="nsew")
        self.progress = ProgressPanel(holder, th, self._cancel)
        self.progress.pack(fill="x", pady=(30, 0))
        self.progress.set("Password accepted. Unlocking your files…", 0.0, "Restoring your folder")
        vault, dest = self.vault, self.dest

        def job(progress, cancel):
            return vm.extract_vault(vault, keys, dest, progress=progress, cancel=cancel)

        self.app.runner.run(job, on_progress=self._on_progress, on_success=self._done, on_error=self._failed)

    def _cancel(self) -> None:
        self.progress.cancel_btn.configure(state="disabled", text="Cancelling…")
        self.app.runner.cancel()

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        frac = (done / total) if total else 1.0
        if phase == "Restoring":
            self.progress.set("Decrypting and restoring your files…", 0.7 * frac)
        else:
            self.progress.set("Checking that every restored file is correct…", 0.7 + 0.3 * frac)

    def _failed(self, exc: BaseException, message: str) -> None:
        if isinstance(exc, OperationCancelled):
            show_message(self.app, "Cancelled", "Nothing was restored. Your protected file is untouched.", "info")
        else:
            show_message(self.app, "Could not restore the folder", message, "warning",
                         "Nothing was restored and your protected file was not changed. "
                         "Try again and choose a different “Restore into” folder if needed.")
        self.credential_step()

    # ------------------------------------------------------------ 4. done
    def _done(self, restored: Path) -> None:
        self.restored = restored
        th = self.th
        self.clear()
        self.body.grid_columnconfigure(0, weight=1)
        col = ctk.CTkFrame(self.body, fg_color="transparent")
        col.grid(row=0, column=0, sticky="n", pady=(40, 0))
        success_badge(col, th).pack()
        Label(col, th, "Folder Unlocked Successfully!", "title", justify="center", anchor="center"
              ).pack(pady=(16, 2))
        Label(col, th, "Your files were restored and checked.", "muted", justify="center",
              anchor="center").pack()
        Label(col, th, str(restored), "small", justify="center", anchor="center", wraplength=520
              ).pack(pady=(8, 4))
        if restored.name != self.root_name:
            Label(col, th, f"A folder named “{self.root_name}” already existed there, so nothing was "
                  "overwritten - your files are in the new folder above.", "small", justify="center",
                  anchor="center", wraplength=520).pack(pady=(0, 4))
        row = ctk.CTkFrame(col, fg_color="transparent")
        row.pack(pady=(16, 0))
        AppButton(row, th, "Open Folder", lambda: reveal_in_explorer(restored), width=170,
                  icon_name="folder").pack(side="left", padx=6)
        AppButton(row, th, "OK", self.go_home, kind="secondary", width=140).pack(side="left", padx=6)
