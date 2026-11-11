"""Lock Folder workflow: choose -> password -> recovery key -> confirm -> encrypt -> done."""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import folder_manager as fm
from core import vault_manager as vm
from core.vault_format import VAULT_EXTENSION
from security.recovery import generate_recovery_key
from ui import theme as T
from ui.dialogs import ask_confirm, show_message
from ui.flow import (
    FlowScreen, path_row, pick_folder, reveal_in_explorer, start_dir, success_badge,
)
from ui.icons import icon
from ui.password_screen import PasswordPair
from ui.recovery_screen import RecoveryKeyPanel
from ui.widgets import AppButton, Banner, Card, Label, ProgressPanel, format_size
from utils import file_association as fa
from utils.error_handler import FolderLockError, OperationCancelled, friendly_message
from utils.paths import unique_path


class LockScreen(FlowScreen):
    def __init__(self, master, app, **_):
        super().__init__(master, app)
        self.folder: Path | None = None
        self.scan_text = ""
        self.password = ""
        self.recovery_key = ""
        self.vault_path: Path | None = None
        self.result: vm.CreateResult | None = None
        self.select_step()

    # ------------------------------------------------------------ 1. choose folder
    def select_step(self) -> None:
        th = self.th
        inner = self.start_step("Lock Folder", "Choose the folder you want to protect.", hero="folder")
        if self.folder:
            path_row(inner, th, str(self.folder)).pack(fill="x")
            Label(inner, th, f"Folder name: {self.folder.name}", "bold").pack(fill="x", pady=(10, 0))
            Label(inner, th, self.scan_text, "muted").pack(fill="x", pady=(2, 0))
        else:
            Label(inner, th, "FolderLock will turn the folder into one protected file. "
                  "Your original folder is not changed.", "muted", wraplength=480).pack(fill="x")
        AppButton(inner, th, "Choose Folder…" if not self.folder else "Choose a Different Folder…",
                  self._choose, kind="primary" if not self.folder else "secondary", width=290,
                  icon_name="folder").pack(anchor="w", pady=(14, 0))
        self.msg = ctk.CTkFrame(inner, fg_color="transparent")
        self.msg.pack(fill="x")
        self.buttons(inner, back=self.go_home, back_text="Cancel", on_next=self.password_step,
                     next_enabled=bool(self.folder))

    def _choose(self) -> None:
        picked = pick_folder(self.app, "Choose the folder to lock")
        if not picked:
            return
        try:
            fm.check_source_folder(picked)
        except FolderLockError as exc:
            self.folder = None
            self.select_step()
            self.error_banner(self.msg, exc.user_message)
            return
        self.folder = picked
        self.scan_text = "Checking the folder…"
        self.select_step()

        def job(_p, _c):
            scan = fm.scan_folder(picked)
            return scan

        def ok(scan: fm.FolderScan):
            note = f"{len(scan.files)} file{'s' if len(scan.files) != 1 else ''}, {format_size(scan.total_bytes)}"
            if scan.skipped_links:
                note += f"  •  {scan.skipped_links} shortcut(s) will be skipped"
            self.scan_text = note
            if self.folder == picked:
                self.select_step()

        def fail(_e, message):
            self.folder, self.scan_text = None, ""
            self.select_step()
            self.error_banner(self.msg, message)

        self.app.runner.run(job, on_success=ok, on_error=fail)

    # ------------------------------------------------------------ 2. password
    def password_step(self) -> None:
        th = self.th
        inner = self.start_step("Set Password", "Create a strong password to protect your folder.", hero="lock")
        self.msg = ctk.CTkFrame(inner, fg_color="transparent")
        self.pair = PasswordPair(inner, th, on_enter=self._password_next, on_edit=self._clear_msg)
        self.pair.pack(fill="x")
        Label(inner, th, "Tip: a short sentence of several words is strong and easy to remember.",
              "small").pack(fill="x", pady=(10, 0))
        self.msg.pack(fill="x")
        self.buttons(inner, back=self.select_step, on_next=self._password_next, next_text="Set Password")
        self.pair.focus()

    def _clear_msg(self) -> None:
        for w in self.msg.winfo_children():
            w.destroy()

    def _password_next(self) -> None:
        pw, error = self.pair.validate()
        for w in self.msg.winfo_children():
            w.destroy()
        if error:
            self.error_banner(self.msg, error)
            return
        self.password = pw
        self.recovery_step()

    # ------------------------------------------------------------ 3. recovery key
    def recovery_step(self) -> None:
        th = self.th
        if not self.recovery_key:
            self.recovery_key = generate_recovery_key()
        inner = self.start_step("Save Your Recovery Key",
                                "Keep this key safe. It lets you open your files if you forget your password.",
                                hero="lifebuoy")
        self.panel = RecoveryKeyPanel(inner, self.app, self.recovery_key, self.folder.name, self._key_confirmed)
        self.panel.pack(fill="x")
        self.next_btn = self.buttons(inner, back=self.password_step, on_next=self.confirm_step,
                                     next_enabled=False)

    def _key_confirmed(self, ok: bool) -> None:
        self.next_btn.configure(state="normal" if ok else "disabled")

    # ------------------------------------------------------------ 4. confirm
    def confirm_step(self) -> None:
        th = self.th
        if self.vault_path is None:
            dest = self.app.settings.get("default_destination")
            base = Path(dest) if dest and Path(dest).is_dir() else self.folder.parent
            self.vault_path = unique_path(base / f"{self.folder.name}{VAULT_EXTENSION}")
        inner = self.start_step("Lock Folder", "Are you sure you want to lock this folder?", hero="lock")
        path_row(inner, th, str(self.folder)).pack(fill="x")
        Banner(inner, th, "The folder will be encrypted and will only be accessible with your password "
               "(or your recovery key). Its contents are copied into a single protected file; your "
               "original folder stays untouched until you decide what to do with it.", "warning", 480
               ).pack(fill="x", pady=(12, 0))
        Label(inner, th, "The protected file will be saved as:", "small").pack(fill="x", pady=(14, 4))
        path_row(inner, th, str(self.vault_path), "vault").pack(fill="x")
        ctk.CTkButton(inner, text="Change location…", fg_color="transparent", hover_color=th.surface_alt,
                      text_color=th.icon, width=10, anchor="w", command=self._change_location,
                      font=ctk.CTkFont(size=T.SMALL, underline=True)).pack(anchor="w", pady=(2, 0))
        self.buttons(inner, back=self.recovery_step, on_next=self.start_locking,
                     next_text="Lock Folder", next_icon="lock", width=170)

    def _change_location(self) -> None:
        chosen = filedialog.asksaveasfilename(
            parent=self.app, title="Where should the protected file be saved?", defaultextension=VAULT_EXTENSION,
            initialfile=self.vault_path.name, initialdir=str(self.vault_path.parent),
            filetypes=[("FolderLock vault", f"*{VAULT_EXTENSION}")], confirmoverwrite=False)
        if not chosen:
            return
        path = Path(chosen)
        if path.suffix.lower() != VAULT_EXTENSION:
            path = path.with_suffix(VAULT_EXTENSION)
        self.vault_path = unique_path(path)          # never overwrite an existing file
        self.confirm_step()

    # ------------------------------------------------------------ 5. encrypt
    def start_locking(self) -> None:
        self.clear()
        th = self.th
        self.body.grid_columnconfigure(1, weight=1)
        holder = ctk.CTkFrame(self.body, fg_color="transparent")
        holder.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.body, text="", image=icon("folder", th.icon, 84, th.bg)
                     ).grid(row=0, column=0, sticky="n", padx=(0, 26), pady=(6, 0))
        self.progress = ProgressPanel(holder, th, self._cancel)
        self.progress.pack(fill="x", pady=(30, 0))
        self.progress.set("Preparing secure keys…", 0.0, "Protecting your folder")
        folder, vault, pw, key = self.folder, self.vault_path, self.password, self.recovery_key

        def job(progress, cancel):
            return vm.create_vault(folder, vault, pw, key, progress=progress, cancel=cancel)

        self.app.runner.run(job, on_progress=self._on_progress, on_success=self._done, on_error=self._failed)

    def _cancel(self) -> None:
        self.progress.cancel_btn.configure(state="disabled", text="Cancelling…")
        self.app.runner.cancel()

    def _on_progress(self, phase: str, done: int, total: int) -> None:
        frac = (done / total) if total else 1.0
        if phase == "Encrypting":
            self.progress.set(f"Encrypting your files…  ({format_size(done)} of {format_size(total)})", 0.5 * frac)
        else:
            self.progress.set("Checking that everything was protected correctly…", 0.5 + 0.5 * frac)

    def _failed(self, exc: BaseException, message: str) -> None:
        self.password = ""
        if isinstance(exc, OperationCancelled):
            show_message(self.app, "Cancelled", "Nothing was changed. Your original folder is untouched.", "info")
            self.confirm_step() if self.folder else self.go_home()
            return
        show_message(self.app, "Could not lock the folder",
                     message, "warning", "Your original folder was not changed and no protected file was kept.")
        self.vault_path = None
        self.confirm_step()

    # ------------------------------------------------------------ 6. done
    def _done(self, result: vm.CreateResult) -> None:
        self.result, self.password = result, ""
        th = self.th
        self.clear()
        self.body.grid_columnconfigure(0, weight=1)
        col = ctk.CTkFrame(self.body, fg_color="transparent")
        col.grid(row=0, column=0, sticky="n", pady=(10, 0))
        success_badge(col, th).pack()
        Label(col, th, "Folder Locked Successfully!", "title", justify="center", anchor="center"
              ).pack(pady=(16, 2))
        Label(col, th, "Your folder is now protected.", "muted", justify="center", anchor="center").pack()
        s = result.stats
        Label(col, th, f"{s.files} files protected  •  saved as {result.vault_path.name} "
              f"({format_size(result.vault_bytes)})", "small", justify="center", anchor="center",
              wraplength=520).pack(pady=(6, 14))

        card = Card(col, th)
        card.pack(fill="x", padx=10)
        Label(card, th, "What about the original folder?", "bold").pack(fill="x", padx=18, pady=(14, 2))
        Label(card, th, "It is still on this computer, unprotected. You can keep it, or delete it so only "
              "the protected file remains. Deleting is your choice - FolderLock never does it on its own.",
              "small", wraplength=500).pack(fill="x", padx=18)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=14)
        self.keep_btn = AppButton(row, th, "Keep Original", self._keep, kind="secondary", width=150)
        self.keep_btn.pack(side="left")
        self.del_btn = AppButton(row, th, "Delete Original…", self._delete_original, kind="secondary", width=180)
        self.del_btn.pack(side="left", padx=10)
        self.decision = Label(card, th, "", "success")

        row2 = ctk.CTkFrame(col, fg_color="transparent")
        row2.pack(pady=(16, 0))
        AppButton(row2, th, "Show Protected File", lambda: reveal_in_explorer(result.vault_path),
                  kind="secondary", width=190).pack(side="left", padx=6)
        AppButton(row2, th, "OK", self.go_home, width=140).pack(side="left", padx=6)
        self.after(700, self._offer_double_click)

    def _offer_double_click(self) -> None:
        """One-time, opt-in offer so a double-click on the .flock file opens FolderLock."""
        s = self.app.settings
        if (not self.winfo_exists() or not fa.is_supported() or s.get_bool("file_association")
                or s.get_bool("assoc_offered")):
            return
        s.set("assoc_offered", "1")
        if ask_confirm(self.app, "Open protected folders with a double-click?",
                       "FolderLock can open your protected files (.flock) when you double-click them. "
                       "You would just type your password and your folder is restored.",
                       yes="Yes, enable it", no="Not now",
                       detail="This only affects your Windows account and needs no administrator rights. "
                              "You can turn it off any time in Settings."):
            try:
                fa.register()
                s.set("file_association", "1")
            except OSError:
                show_message(self.app, "Could not enable it",
                             "Windows did not allow the change. You can try again from Settings.", "warning")

    def _decide(self, text: str) -> None:
        self.decision.configure(text=text)
        self.decision.pack(fill="x", padx=18, pady=(0, 12))

    def _keep(self) -> None:
        self._decide("✓ Your original folder was kept.")

    def _delete_original(self) -> None:
        folder, vault = self.folder, self.result.vault_path
        if not ask_confirm(
            self.app, "Delete the original folder?",
            f"“{folder.name}” and everything inside it will be removed from this computer.\n\n"
            "Before you continue, make sure you can open the protected file and that your "
            "recovery key is saved.",
            yes="Delete Original Folder", no="Keep It",
            detail="Note: deleting files in the normal way does not securely erase them. On SSDs, "
                   "in backups or with special recovery tools, remnants may remain."):
            return
        if not vault.exists():
            show_message(self.app, "Protected file missing",
                         "The protected file could not be found, so the original was NOT deleted.", "warning")
            return
        self.del_btn.configure(state="disabled", text="Deleting…")
        self.keep_btn.configure(state="disabled")

        def job(_p, _c):
            fm.remove_folder(folder)

        def ok(_):
            self._decide("✓ The original folder was deleted.")
            self.del_btn.configure(text="Deleted")

        def fail(_e, message):
            self.del_btn.configure(state="normal", text="Delete Original…")
            self.keep_btn.configure(state="normal")
            show_message(self.app, "Could not delete everything", message, "warning",
                         "The protected file is safe. You can delete the folder yourself in File Explorer.")

        self.app.runner.run(job, on_success=ok, on_error=fail)
