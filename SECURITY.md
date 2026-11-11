# FolderLock — Security & Recovery Documentation

## Summary

| Item | Choice |
|---|---|
| Encryption | AES-256-GCM (authenticated), via the `cryptography` library |
| Password hashing / key derivation | **Argon2id**, 256 MiB memory, 3 passes, 4 lanes, random 16-byte salt per vault |
| Data key | Random 256-bit key per vault (never derived from the password directly) |
| Recovery | Random 256-bit recovery key; independently wraps the same data key |
| Large files | Streamed in 1 MiB authenticated chunks — never loaded fully into memory |
| Stored passwords | **None.** The password is never written anywhere. Only a wrapped key is stored. |
| Backdoors / master keys | **None.** |

## How the password is "hashed and protected"

The password is never stored, not even as a hash. Instead:

1. Your password is Unicode-normalised (NFKC) and fed to **Argon2id** with a random salt. Argon2id is memory-hard,
   so every guess costs an attacker ~256 MiB of RAM and about 0.5–1 s on a modern PC, which makes large-scale GPU/ASIC
   guessing very expensive.
2. The result is a *key-encryption key*. It decrypts (unwraps) the vault's random *data key* using AES-256-GCM.
3. If the password is wrong, the AES-GCM authentication tag fails and nothing is revealed. That tag check *is* the
   password check.

Changing the password creates a new salt and re-wraps the same data key; no file is re-encrypted.

## What is protected, and how tamper-proof it is

* **Every chunk** is authenticated. Its nonce is a never-repeating counter, and its associated data contains the vault
  id, the chunk position and a "last chunk" flag. Therefore modified, reordered, duplicated, dropped, truncated or
  appended data is **detected**, and nothing is exposed.
* **File names, folder structure and sizes are encrypted** (they live inside the authenticated stream). The
  vault leaks only its total size.
* **Each file** carries its own SHA-256 inside the encrypted stream, and the end-of-archive record authenticates the
  total file/folder/byte counts.
* **The header** (KDF parameters, salts, wrapped keys) is authenticated by an HMAC keyed from the data key.
* Restoring is **staged**: files are written to a hidden temporary folder, re-hashed from disk, and only then moved
  into place. A failed or cancelled restore leaves nothing behind.
* **Path traversal** (`..`, absolute paths, drive letters, `:` streams, reserved Windows names, duplicates) is
  rejected on extraction, even for vaults created by someone who knows the password. Symlinks are never created or
  followed.
* Existing files/folders are **never overwritten**; FolderLock restores to a new "(restored)" folder instead.

## Vault format (`.flock`, version 1)

```
0       16 bytes   preamble: "FLOCKVLT", version (uint16), flags, reserved
16      8192       header slot A
8208    8192       header slot B
16400   ...        body: AES-256-GCM chunks  [uint32 length][ciphertext+tag] ...
```

Header slot = `uint32 length | canonical JSON | SHA-256 | padding`. The JSON holds `generation`, `core`
(vault id, password section {Argon2id params, salt, nonce, wrapped DEK}, recovery section {salt, nonce, wrapped DEK},
chunk size, creation time) and `mac` (HMAC-SHA-256 over `core` + generation).

Two slots make password changes crash-safe: the new header is written to the inactive slot, read back and verified,
and only then copied over the old slot. The highest-generation intact slot wins.

Plaintext stream (inside the chunks): `R` root name, `D` directories, `F` files (path, size, mtime, content,
SHA-256), `E` end marker with counts. Full details are in `core/vault_format.py`.

**Versioning:** the version is in the preamble. Newer unknown versions are refused with a clear message.

## Recovery

When you lock a folder, FolderLock generates a **recovery key** (14 groups of 4 characters). It must be saved
(copy / save file / print) and confirmed before encryption starts.

* The recovery key **independently** unwraps the same data key. Either the password **or** the recovery key opens
  the vault.
* The key itself is **not stored** in the vault, only a copy of the data key encrypted by it.
* Use *Recovery Options* to: open a vault with the key, set a new password with the key, or create a new recovery
  key (the old one then stops working).
* **If both the password and the recovery key are lost, the data cannot be recovered by anyone.** There is no reset
  link, no master password, and no support backdoor. This is a deliberate security property.

## Honest limitations

* **Weak passwords are the main risk.** FolderLock enforces a minimum strength, but a short, guessable password
  can still be attacked offline against a copied `.flock` file. Use a long passphrase.
* **Copies of an old vault stay openable with the old password.** Changing the password re-wraps the key; it
  does not re-encrypt data. If a password was exposed, restore the folder and lock it again to get a fresh data key.
* **Deleting the original folder is not a secure erase.** On SSDs, in backups, shadow copies or with recovery tools,
  remnants can remain. FolderLock says so and never deletes anything without explicit confirmation.
* **A compromised computer** (keylogger, malware, someone watching) defeats any password-based tool. Passwords and
  keys also exist in RAM while in use; Python cannot guarantee wiping them.
* **Auto Lock only closes the program after inactivity** (clearing anything typed). It does not encrypt folders.
* **Unsigned executable:** Windows SmartScreen may warn "Windows protected your PC" because the exe is not
  code-signed. Choose *More info → Run anyway* only if you built or downloaded it from a source you trust. FolderLock
  does not try to bypass this; a code-signing certificate removes the warning.
* Shortcuts/symlinks inside a folder are skipped (never followed), and FolderLock tells you how many were skipped.
* File timestamps are preserved; NTFS permissions, alternate data streams and hidden/read-only attributes are not.

## Reporting a problem

Please do not include real passwords, recovery keys or private files. An error log without secrets is kept at
`%LOCALAPPDATA%\FolderLock\error.log`.
