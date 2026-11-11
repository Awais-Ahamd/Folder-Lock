"""Generate assets/logo.png and assets/icon.ico (shield + padlock) with Pillow.

Run:  python tools/make_assets.py
Uses only the approved palette (Ice Blue, Soft White, Emerald Green, Muted Gray)
on a dark navy base.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ICE, WHITE, EMERALD, GRAY = "#48B8F8", "#F1F5F9", "#19C995", "#9BAFC4"
NAVY, NAVY_LIGHT = "#0F1B2D", "#1B2A41"
SS = 4                      # supersampling factor for smooth edges


def draw_logo(size: int = 512) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def p(x: float, y: float) -> tuple[float, float]:
        return x * s, y * s

    # Shield outline (polygon approximating a curved shield)
    top = [(0.50, 0.04), (0.84, 0.15), (0.84, 0.50)]
    shield = [p(0.50, 0.04), p(0.86, 0.16), p(0.86, 0.52)]
    pts = [(0.50, 0.04), (0.86, 0.16), (0.86, 0.50), (0.82, 0.66), (0.72, 0.80),
           (0.50, 0.96), (0.28, 0.80), (0.18, 0.66), (0.14, 0.50), (0.14, 0.16)]
    d.polygon([p(*q) for q in pts], fill=ICE)
    inner = [(0.50, 0.10), (0.80, 0.20), (0.80, 0.50), (0.76, 0.64), (0.68, 0.75),
             (0.50, 0.89), (0.32, 0.75), (0.24, 0.64), (0.20, 0.50), (0.20, 0.20)]
    d.polygon([p(*q) for q in inner], fill=NAVY)
    del top, shield

    # Padlock shackle
    d.arc([*p(0.36, 0.22), *p(0.64, 0.52)], 180, 360, fill=WHITE, width=int(0.055 * s))
    d.rectangle([*p(0.3585, 0.37), *p(0.3585 + 0.055, 0.47)], fill=WHITE)
    d.rectangle([*p(0.5865, 0.37), *p(0.5865 + 0.055, 0.47)], fill=WHITE)
    # Padlock body
    d.rounded_rectangle([*p(0.32, 0.44), *p(0.68, 0.72)], radius=int(0.05 * s), fill=WHITE)
    # Keyhole in emerald
    d.ellipse([*p(0.465, 0.514), *p(0.535, 0.584)], fill=EMERALD)
    d.polygon([p(0.485, 0.57), p(0.515, 0.57), p(0.527, 0.66), p(0.473, 0.66)], fill=EMERALD)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "assets"
    (out / "icons").mkdir(parents=True, exist_ok=True)
    logo = draw_logo(512)
    logo.save(out / "logo.png")
    logo.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                       (128, 128), (256, 256)])
    print("wrote", out / "logo.png", "and", out / "icon.ico")


if __name__ == "__main__":
    main()
