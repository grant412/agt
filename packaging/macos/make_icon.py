# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Draws AGT's macOS app icon, packaging/macos/AGT.icns: the tray's ring and dot (see
`rgba` in crates/app/src/tray.rs) on a macOS icon tile.

    uv run packaging/macos/make_icon.py [--style graphite|blue|light] [--png out.png]
"""

import argparse
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

N = 1024  # master size
SS = 4  # drawn this many times larger, then scaled down (antialiasing)
# Tile top, tile bottom, ring, dot.
STYLES = {
    "blue": ((59, 130, 246), (29, 78, 216), (255, 255, 255), (255, 255, 255)),
    "graphite": ((55, 65, 81), (17, 24, 39), (255, 255, 255), (59, 130, 246)),
    "light": ((255, 255, 255), (226, 232, 240), (37, 99, 235), (37, 99, 235)),
}


def tile_mask(size: int) -> Image.Image:
    """macOS's icon tile: 824/1024 of the canvas, a superellipse (the "continuous" corners)."""
    c, a, n = size / 2, size * 412 / 1024, 5.0
    points = []
    for i in range(1440):
        t = 2 * math.pi * i / 1440
        cos, sin = math.cos(t), math.sin(t)
        points.append(
            (
                c + a * math.copysign(abs(cos) ** (2 / n), cos),
                c + a * math.copysign(abs(sin) ** (2 / n), sin),
            )
        )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask


def gradient(size: int, top, bottom) -> Image.Image:
    column = Image.new("RGB", (1, size))
    for y in range(size):
        f = y / (size - 1)
        column.putpixel((0, y), tuple(round(t + (b - t) * f) for t, b in zip(top, bottom)))
    return column.resize((size, size))


def glyph_mask(size: int, ring: bool) -> Image.Image:
    """The tray glyph's proportions: ring 11..15, dot 6 (of 15), 48% of the canvas wide."""
    c, r = size / 2, size * 0.235
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    if ring:
        draw.ellipse((c - r, c - r, c + r, c + r), fill=255)
        inner = r * 11 / 15
        draw.ellipse((c - inner, c - inner, c + inner, c + inner), fill=0)
    else:
        dot = r * 6 / 15
        draw.ellipse((c - dot, c - dot, c + dot, c + dot), fill=255)
    return mask


def icon(style: str) -> Image.Image:
    top, bottom, ring, dot = STYLES[style]
    size = N * SS
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shape = tile_mask(size)

    # Drop shadow under the tile.
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = shape.transform(shape.size, Image.AFFINE, (1, 0, 0, 0, 1, -12 * SS))
    shadow.putalpha(offset.point(lambda v: v * 0.32).filter(ImageFilter.GaussianBlur(20 * SS)))
    out.alpha_composite(shadow)

    body = gradient(size, top, bottom).convert("RGBA")
    body.putalpha(shape)
    out.alpha_composite(body)

    # A soft shadow under the glyph, then the ring and the dot.
    marks = Image.new("L", (size, size), 0)
    marks.paste(255, mask=glyph_mask(size, True))
    marks.paste(255, mask=glyph_mask(size, False))
    depth = marks.transform(marks.size, Image.AFFINE, (1, 0, 0, 0, 1, -8 * SS))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow.putalpha(
        depth.point(lambda v: v * (0.10 if style == "light" else 0.22)).filter(
            ImageFilter.GaussianBlur(14 * SS)
        )
    )
    out.alpha_composite(glow)
    for color, is_ring in ((ring, True), (dot, False)):
        layer = Image.new("RGBA", (size, size), color + (0,))
        layer.putalpha(glyph_mask(size, is_ring))
        out.alpha_composite(layer)

    return out.resize((N, N), Image.LANCZOS)


def write_icns(master: Image.Image, path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AGT.iconset"
        iconset.mkdir()
        for points in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = points * scale
                name = f"icon_{points}x{points}{'@2x' if scale == 2 else ''}.png"
                master.resize((px, px), Image.LANCZOS).save(iconset / name)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--style", choices=STYLES, default="graphite")
    parser.add_argument("--png", type=Path, help="also save the 1024 px master here")
    parser.add_argument("--icns", type=Path, default=Path(__file__).with_name("AGT.icns"))
    args = parser.parse_args()
    master = icon(args.style)
    if args.png:
        master.save(args.png)
    if shutil.which("iconutil"):
        write_icns(master, args.icns)
        print(f"wrote {args.icns}")


if __name__ == "__main__":
    main()
