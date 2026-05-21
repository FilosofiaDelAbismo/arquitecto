#!/usr/bin/env python3
"""Genera favicon.ico (32x32) y apple-touch-icon.png (180x180).

Ejecutar UNA vez desde la raíz del sitio:
    cd /home/ubuntu/web-arquitectodigital && python3 assets/_gen_favicons.py

Requiere Pillow:
    pip install --user Pillow      # si no esta instalado

Diseño: circulo negro #0a0a0a, "A" naranja #FF6B35 + "D" blanca #F5F5F5.
Misma identidad que favicon.svg.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent

BG = (10, 10, 10, 255)
A_COLOR = (255, 107, 53, 255)
D_COLOR = (245, 245, 245, 255)


def _font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/Arial-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _render(size: int) -> Image.Image:
    """Devuelve una PIL.Image RGBA con el favicon AD del tamaño pedido."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Círculo de fondo (anti-alias decente con supersample x4).
    ss = 4
    big = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(big)
    d2.ellipse((0, 0, size * ss - 1, size * ss - 1), fill=BG)
    img = big.resize((size, size), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    font_size = int(size * 0.62)
    font = _font(font_size)

    # Medir "AD" para centrarlo.
    text = "AD"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1] - int(size * 0.04)

    # Letras por separado para colorear A y D distinto.
    a_bbox = draw.textbbox((0, 0), "A", font=font)
    a_w = a_bbox[2] - a_bbox[0]
    draw.text((tx, ty), "A", fill=A_COLOR, font=font)
    draw.text((tx + a_w, ty), "D", fill=D_COLOR, font=font)
    return img


def main() -> None:
    # favicon.ico — embebe 16, 32, 48 (multi-size standard).
    ico_path = ROOT / "favicon.ico"
    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    base = _render(48)
    base.save(ico_path, format="ICO", sizes=ico_sizes)
    print(f"OK  {ico_path}  ({', '.join(f'{w}x{h}' for w, h in ico_sizes)})")

    # apple-touch-icon.png — 180x180 sin transparencia.
    apple_path = ROOT / "apple-touch-icon.png"
    apple = _render(180).convert("RGB")
    apple.save(apple_path, format="PNG", optimize=True)
    print(f"OK  {apple_path}  (180x180)")


if __name__ == "__main__":
    main()
