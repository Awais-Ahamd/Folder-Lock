"""Password rules and strength estimation (offline, dependency-free)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

MIN_LENGTH = 10
MAX_LENGTH = 256

# A short list of the most abused passwords. Strength also falls with patterns.
_COMMON = {
    "password", "password1", "password123", "passw0rd", "123456789", "1234567890",
    "12345678", "qwertyuiop", "qwerty123", "iloveyou", "letmein", "welcome1",
    "admin123", "abc12345", "111111111", "000000000", "football", "baseball",
    "monkey123", "dragon123", "sunshine", "princess", "folderlock", "changeme",
}
_SEQUENCES = ["abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm", "0123456789"]

LEVELS = ("Too weak", "Weak", "Fair", "Good", "Strong")


@dataclass(frozen=True)
class PasswordCheck:
    score: int            # 0..4 index into LEVELS
    label: str
    fraction: float       # 0..1 for the strength bar
    acceptable: bool      # may it be used to protect a folder?
    advice: str           # friendly hint


def _entropy_bits(password: str) -> float:
    pool = 0
    if re.search(r"[a-z]", password):
        pool += 26
    if re.search(r"[A-Z]", password):
        pool += 26
    if re.search(r"\d", password):
        pool += 10
    if re.search(r"[^A-Za-z0-9]", password):
        pool += 33
    if not pool:
        return 0.0
    # Repeated characters add little; count distinct characters more heavily.
    distinct = len(set(password))
    effective_len = distinct + (len(password) - distinct) * 0.25
    bits = effective_len * math.log2(pool)
    lowered = password.lower()
    for seq in _SEQUENCES:
        for i in range(len(seq) - 3):
            chunk = seq[i:i + 4]
            if chunk in lowered or chunk[::-1] in lowered:
                bits -= 8
    return max(bits, 0.0)


def check_password(password: str) -> PasswordCheck:
    if not password:
        return PasswordCheck(0, "", 0.0, False, "Type a password to protect your folder.")
    if len(password) > MAX_LENGTH:
        return PasswordCheck(0, "Too long", 0.0, False, f"Please use at most {MAX_LENGTH} characters.")

    lowered = password.lower()
    if lowered in _COMMON or lowered.strip("0123456789") in _COMMON:
        return PasswordCheck(0, LEVELS[0], 0.1, False,
                             "This is a very common password. Please choose something unique.")
    if len(set(password)) <= 3:
        return PasswordCheck(0, LEVELS[0], 0.1, False, "Please use a greater variety of characters.")

    bits = _entropy_bits(password)
    if bits < 40:
        score = 0
    elif bits < 55:
        score = 1
    elif bits < 70:
        score = 2
    elif bits < 90:
        score = 3
    else:
        score = 4

    if len(password) < MIN_LENGTH:
        return PasswordCheck(min(score, 1), LEVELS[min(score, 1)], 0.2, False,
                             f"Use at least {MIN_LENGTH} characters. A short phrase of several words works well.")
    if score < 2:
        return PasswordCheck(score, LEVELS[score], 0.25 * (score + 1), False,
                             "Too easy to guess. Add more words, numbers or symbols.")
    advice = {2: "Acceptable. A longer password is safer.",
              3: "Good password.", 4: "Excellent password."}[score]
    return PasswordCheck(score, LEVELS[score], 0.25 * (score + 1) if score < 4 else 1.0, True, advice)


def validate_new_password(password: str, confirmation: str) -> str | None:
    """Return a friendly error message, or ``None`` if the password may be used."""
    if not password:
        return "Please enter a password."
    if password != confirmation:
        return "The two passwords do not match. Please type them again."
    result = check_password(password)
    if not result.acceptable:
        return result.advice
    return None
