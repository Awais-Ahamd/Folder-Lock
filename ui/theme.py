"""Colours, fonts and spacing. Change the look of the whole app from this file.

The four approved brand colours never change. Dark/Blue/Light themes only vary
the neutral background and surface shades behind them.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

# ----- Approved palette (do not change) ---------------------------------------
ICE_BLUE = "#48B8F8"
SOFT_WHITE = "#F1F5F9"
EMERALD = "#19C995"
MUTED_GRAY = "#9BAFC4"


@dataclass(frozen=True)
class Theme:
    name: str
    mode: str            # customtkinter appearance: "dark" | "light"
    bg: str              # window background
    sidebar: str
    surface: str         # cards
    surface_alt: str     # inputs, secondary buttons
    border: str
    shadow: str          # button "raised" edge
    text: str            # headings / labels  (Soft White on dark themes)
    muted: str           # secondary text     (Muted Gray on dark themes)
    primary: str         # Ice Blue
    primary_hover: str
    on_primary: str      # text drawn on Ice Blue
    success: str         # Emerald Green
    success_text: str
    icon: str            # default icon colour


DARK = Theme("Dark", "dark", bg="#0F1B2D", sidebar="#0B1523", surface="#1B2A41",
             surface_alt="#243650", border="#2F4562", shadow="#0A1220", text=SOFT_WHITE,
             muted=MUTED_GRAY, primary=ICE_BLUE, primary_hover="#6CC8FA", on_primary="#0B1523",
             success=EMERALD, success_text=EMERALD, icon=ICE_BLUE)

BLUE = Theme("Blue", "dark", bg="#0E2440", sidebar="#0A1B32", surface="#173254",
             surface_alt="#1F4068", border="#2D5683", shadow="#08162B", text=SOFT_WHITE,
             muted=MUTED_GRAY, primary=ICE_BLUE, primary_hover="#6CC8FA", on_primary="#0A1B32",
             success=EMERALD, success_text=EMERALD, icon=ICE_BLUE)

# Light theme: Soft White surfaces. Muted Gray is too pale for body text on white, so a
# darker shade of the same hue is used for secondary text to keep contrast accessible.
LIGHT = Theme("Light", "light", bg=SOFT_WHITE, sidebar="#E1E9F1", surface="#FFFFFF",
              surface_alt="#E6EDF4", border="#C5D3E1", shadow="#B6C6D8", text="#0F1B2D",
              muted="#4E6379", primary=ICE_BLUE, primary_hover="#2FA9EE", on_primary="#0B1523",
              success=EMERALD, success_text="#0B7A5B", icon="#1B8FD6")

THEMES = {t.name: t for t in (DARK, LIGHT, BLUE)}


def font_family() -> str:
    return "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"


def mono_family() -> str:
    return "Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono"


# Type scale (points)
TITLE, HEADING, BODY, SMALL, BUTTON = 26, 18, 14, 12, 14
RADIUS, RADIUS_SMALL = 16, 10
PAD = 24

APP_NAME = "FolderLock"
APP_VERSION = "1.0.0"
APP_TAGLINE = "Lock • Protect • Secure"
APP_DESCRIPTION = "Protect your private folders with secure password-based encryption."
APP_DEVELOPER = "FolderLock Project"        # shown on the About screen; edit freely
