"""Consistent line-style icons drawn with Pillow (no icon fonts or downloads needed)."""
from __future__ import annotations

import math
from functools import lru_cache

import customtkinter as ctk
from PIL import Image, ImageDraw

_BASE = 96          # canvas for drawing; downscaled with anti-aliasing
_SS = 4


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    s = _BASE * _SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img), s


def _u(v: float) -> float:
    """Convert a 0..1 coordinate to pixels."""
    return v * _BASE * _SS


def _draw(name: str, color: str, accent: str) -> Image.Image:
    img, d, s = _canvas()
    w = int(0.075 * s)
    P = lambda x, y: (_u(x), _u(y))      # noqa: E731

    def rrect(x0, y0, x1, y1, r, **kw):
        d.rounded_rectangle([*P(x0, y0), *P(x1, y1)], radius=_u(r), **kw)

    if name in ("lock", "unlock"):
        if name == "lock":
            d.arc([*P(0.30, 0.10), *P(0.70, 0.56)], 180, 360, fill=color, width=w)
            d.line([P(0.30, 0.33), P(0.30, 0.48)], fill=color, width=w)
            d.line([P(0.70, 0.33), P(0.70, 0.48)], fill=color, width=w)
        else:        # open padlock: shackle lifted on the right side
            d.arc([*P(0.30, 0.02), *P(0.70, 0.46)], 180, 360, fill=color, width=w)
            d.line([P(0.30, 0.24), P(0.30, 0.48)], fill=color, width=w)
            d.line([P(0.70, 0.24), P(0.70, 0.31)], fill=color, width=w)
        rrect(0.20, 0.44, 0.80, 0.88, 0.09, fill=color)
        d.ellipse([*P(0.44, 0.58), *P(0.56, 0.70)], fill=accent)
        d.rectangle([*P(0.475, 0.66), *P(0.525, 0.78)], fill=accent)
    elif name == "key":
        d.ellipse([*P(0.12, 0.14), *P(0.50, 0.52)], outline=color, width=w)
        d.line([P(0.45, 0.47), P(0.88, 0.90)], fill=color, width=w)
        d.line([P(0.70, 0.72), P(0.62, 0.80)], fill=color, width=w)
        d.line([P(0.81, 0.83), P(0.73, 0.91)], fill=color, width=w)
    elif name == "lifebuoy":
        d.ellipse([*P(0.10, 0.10), *P(0.90, 0.90)], outline=color, width=int(w * 1.5))
        d.ellipse([*P(0.34, 0.34), *P(0.66, 0.66)], outline=color, width=int(w * 0.9))
        for ang in (45, 135, 225, 315):
            r1, r2 = 0.17, 0.40
            a = math.radians(ang)
            d.line([P(0.5 + r1 * math.cos(a), 0.5 + r1 * math.sin(a)),
                    P(0.5 + r2 * math.cos(a), 0.5 + r2 * math.sin(a))], fill=color, width=int(w * 1.7))
    elif name == "home":
        d.polygon([P(0.50, 0.12), P(0.90, 0.48), P(0.80, 0.48), P(0.80, 0.86),
                   P(0.20, 0.86), P(0.20, 0.48), P(0.10, 0.48)], fill=color)
        d.rectangle([*P(0.43, 0.60), *P(0.57, 0.86)], fill=(0, 0, 0, 0))
    elif name == "settings":
        cx = cy = 0.5
        for i in range(8):
            a = math.radians(i * 45)
            ca, sa = math.cos(a), math.sin(a)
            pts = []
            for dr, dt in ((0.30, -0.10), (0.43, -0.07), (0.43, 0.07), (0.30, 0.10)):
                ang = a + dt * 2.2
                pts.append(P(cx + dr * math.cos(ang) * 1.0, cy + dr * math.sin(ang) * 1.0))
            d.polygon(pts, fill=color)
            del ca, sa
        d.ellipse([*P(0.18, 0.18), *P(0.82, 0.82)], fill=color)
        d.ellipse([*P(0.38, 0.38), *P(0.62, 0.62)], fill=(0, 0, 0, 0))
    elif name == "info":
        d.ellipse([*P(0.10, 0.10), *P(0.90, 0.90)], outline=color, width=w)
        d.ellipse([*P(0.44, 0.24), *P(0.56, 0.36)], fill=color)
        rrect(0.44, 0.44, 0.56, 0.72, 0.03, fill=color)
    elif name == "folder":
        d.polygon([P(0.08, 0.22), P(0.38, 0.22), P(0.46, 0.32), P(0.92, 0.32),
                   P(0.92, 0.80), P(0.08, 0.80)], fill=color)
        rrect(0.08, 0.36, 0.92, 0.80, 0.06, fill=color)
    elif name == "eye":
        d.arc([*P(0.06, 0.16), *P(0.94, 0.84)], 200, 340, fill=color, width=w)
        d.arc([*P(0.06, 0.16), *P(0.94, 0.84)], 20, 160, fill=color, width=w)
        d.ellipse([*P(0.36, 0.36), *P(0.64, 0.64)], fill=color)
    elif name == "eye_off":
        d.arc([*P(0.06, 0.16), *P(0.94, 0.84)], 200, 340, fill=color, width=w)
        d.arc([*P(0.06, 0.16), *P(0.94, 0.84)], 20, 160, fill=color, width=w)
        d.ellipse([*P(0.36, 0.36), *P(0.64, 0.64)], fill=color)
        d.line([P(0.16, 0.86), P(0.84, 0.14)], fill=color, width=int(w * 1.1))
    elif name == "check":
        d.line([P(0.20, 0.54), P(0.42, 0.74), P(0.80, 0.30)], fill=color, width=int(w * 1.5), joint="curve")
    elif name == "warning":
        d.polygon([P(0.50, 0.10), P(0.94, 0.86), P(0.06, 0.86)], fill=color)
        rrect(0.46, 0.34, 0.54, 0.62, 0.02, fill=accent)
        d.ellipse([*P(0.455, 0.67), *P(0.545, 0.76)], fill=accent)
    elif name == "arrow":
        d.line([P(0.14, 0.5), P(0.84, 0.5)], fill=color, width=w)
        d.line([P(0.60, 0.26), P(0.86, 0.5), P(0.60, 0.74)], fill=color, width=w, joint="curve")
    elif name == "back":
        d.line([P(0.86, 0.5), P(0.16, 0.5)], fill=color, width=w)
        d.line([P(0.40, 0.26), P(0.14, 0.5), P(0.40, 0.74)], fill=color, width=w, joint="curve")
    elif name == "vault":
        rrect(0.14, 0.10, 0.86, 0.90, 0.08, fill=color)
        d.ellipse([*P(0.36, 0.38), *P(0.64, 0.66)], fill=accent)
        d.rectangle([*P(0.46, 0.60), *P(0.54, 0.76)], fill=accent)
    else:
        raise ValueError(f"unknown icon {name}")
    return img.resize((_BASE, _BASE), Image.LANCZOS)


@lru_cache(maxsize=256)
def icon(name: str, color: str, size: int = 24, accent: str = "#0B1523") -> ctk.CTkImage:
    """A CTkImage of the named icon. ``accent`` is the colour of cut-out details."""
    img = _draw(name, color, accent)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
