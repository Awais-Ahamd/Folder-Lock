# FolderLock

Protect your private folders with secure password-based encryption.
Portable, offline, no installation: **one file, `FolderLock.exe`.**

## For everyday users

1. Copy **FolderLock.exe** anywhere (Desktop, USB stick, another PC) and double-click it.
2. **Lock Folder** → choose a folder → choose a password → **save your recovery key** → Lock.
   You get one protected file ending in `.flock`.
3. **Unlock Folder** → choose the `.flock` file → enter your password → choose where to restore.
4. **Fastest way:** just **double-click the `.flock` file**. FolderLock opens on the password screen and your folder
   is restored next to the `.flock` file (you can press *Change…* to pick another place).
   After your first lock, FolderLock offers to turn this on (or use *Settings → Open with Double-Click*).
   It only affects your own Windows account and needs no administrator rights. If you move `FolderLock.exe`,
   just start it once and it re-links itself.

Good to know:

* Your original folder is **never deleted automatically**. After locking, FolderLock asks whether to keep or delete it.
* **Keep your recovery key safe.** If you forget your password, it is the only way back in. Without the password
  *and* the key, nobody can recover your files.
* The `.flock` file can be copied to any Windows PC; you only need the password (or recovery key).
* Windows SmartScreen may say "Windows protected your PC" because the program is not code-signed.
  Click **More info → Run anyway** if you trust where you got it.

## Getting FolderLock.exe

A Windows `.exe` can only be built on Windows. Pick one:

* **GitHub (no setup):** push this folder to a GitHub repository → *Actions → Build FolderLock.exe → Run workflow*.
  Download `FolderLock.exe` from the run's artifacts. The workflow runs all tests and a packaged self-test first.
* **Your own Windows PC:** install Python 3.12 from python.org, then double-click **`build_windows.bat`**.
  Result: `dist\FolderLock.exe`.

## For developers

```
pip install -r requirements.txt
python main.py                 # run from source
python -m pytest -q            # 100+ tests (crypto, tamper, path traversal, interruption, recovery)
python build.py                # tests + one-file build + packaged self-test  -> dist/FolderLock.exe
FolderLock.exe --selftest out.txt   # headless end-to-end check; writes "OK" to out.txt
```

### Project layout

```
main.py                  entry point (+ --selftest)
security/                key_manager (Argon2id, wrapping), encryption (chunked AES-GCM),
                         password_manager (rules/strength), recovery (recovery key)
core/                    vault_format (file layout), vault_manager (create/unlock/restore/change password),
                         folder_manager (scan, safe paths, cleanup)
ui/                      app (window, navigation), dashboard, lock_screen, unlock_screen, password_screen,
                         recovery_screen, settings, about, dialogs, widgets, icons, theme, worker
database/settings_db.py  non-secret preferences (SQLite)
utils/                   paths, error_handler (friendly messages), validators live in security/core modules
tests/                   pytest suite
tools/make_assets.py     regenerates assets/logo.png and icon.ico
```

The encryption engine (`security/`, `core/`) has **no GUI imports** and can be used on its own.

### Modifying the program

* **Colours / fonts / spacing:** `ui/theme.py`. The four brand colours are at the top; do not change them.
* **App name, version, developer text:** constants at the bottom of `ui/theme.py`.
* **Texts and layouts:** each screen is one file in `ui/`. Steps are methods (`select_step`, `password_step`, …).
* **Password rules:** `security/password_manager.py` (`MIN_LENGTH`, scoring).
* **Encryption strength:** `security/key_manager.py` → `DEFAULT_KDF`. Cost parameters are stored per vault, so old
  vaults keep working. Never lower them. Changing the *file format* requires bumping `FORMAT_VERSION`
  in `core/vault_format.py`.
* **Logo/icon:** edit `tools/make_assets.py`, then `python tools/make_assets.py`.

### Rebuilding the executable

`python build.py` (Windows). It uses `FolderLock.spec` (one-file, windowed, no console, no UPX, no admin rights,
bundles CustomTkinter data and the Argon2 native module, embeds icon and version info).

### Release checklist (clean Windows 10 / 11 machines)

- [ ] Copy `FolderLock.exe` to a PC **without Python**; it starts with no missing-DLL errors.
- [ ] Works with the network disabled.
- [ ] Lock a folder, copy the `.flock` to another PC, unlock it there.
- [ ] Wrong password shows "Incorrect password. Your files are still protected."
- [ ] Recovery key: open a vault and set a new password with it.
- [ ] Lock/unlock a multi-GB folder; cancel mid-way; confirm no leftover files.
- [ ] Optional: sign the exe with a code-signing certificate to remove the SmartScreen warning.

See **SECURITY.md** for the cryptographic design, vault format, recovery and limitations.
