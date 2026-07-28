#!/usr/bin/env python3
"""Generate the text-free promotional artwork and its transparent previews.

The artwork is a deterministic flat-style mountain scene drawn with Pillow on a
pure white background. The transparent version is produced by the repository's
own CLI so the poster always shows a genuine processing result. A checkerboard
composite is also written for README previews, while the RGBA file remains the
actual output.
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
ART_SOURCE = Path(__file__).with_name("promo_art_source.png")
ART_TRANSPARENT = Path(__file__).with_name("promo_art_source_transparent.png")
ART_PREVIEW = Path(__file__).with_name(
    "promo_art_source_transparent_preview_checker.png"
)

# Final canvas and supersampling factor for smooth antialiased edges.
SIZE = (1440, 1080)
SS = 3

NAVY = (17, 24, 39, 255)
CORAL = (236, 91, 118, 255)
TEAL = (32, 184, 205, 255)
AMBER = (246, 195, 68, 255)
EMERALD = (18, 166, 125, 255)
VIOLET = (108, 92, 231, 255)


def draw_mark() -> Image.Image:
    width, height = SIZE[0] * SS, SIZE[1] * SS
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    def px(fx: float, fy: float) -> tuple[int, int]:
        return int(width * fx), int(height * fy)

    baseline = int(height * 0.86)

    # Amber sun, drawn first so the peaks overlap it.
    sun_r = int(height * 0.11)
    sun_cx, sun_cy = px(0.76, 0.20)
    draw.ellipse(
        (sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r),
        fill=AMBER,
    )

    # Back range: tall violet peak with a shoulder.
    draw.polygon(
        [px(0.10, 0.86), px(0.30, 0.30), px(0.40, 0.44),
         px(0.50, 0.14), px(0.74, 0.86)],
        fill=VIOLET,
    )
    # Middle range: teal peaks on the right.
    draw.polygon(
        [px(0.42, 0.86), px(0.62, 0.34), px(0.72, 0.50),
         px(0.82, 0.38), px(0.96, 0.86)],
        fill=TEAL,
    )
    # Front range: coral peak on the left.
    draw.polygon(
        [px(0.04, 0.86), px(0.22, 0.46), px(0.32, 0.58),
         px(0.42, 0.48), px(0.58, 0.86)],
        fill=CORAL,
    )
    # Foreground: small emerald hill anchoring the right corner.
    hill_r = int(width * 0.16)
    draw.pieslice(
        (int(width * 0.62) - hill_r, baseline - hill_r,
         int(width * 0.62) + hill_r, baseline + hill_r),
        start=180, end=360, fill=EMERALD,
    )
    # Navy ground line keeps the composition grounded.
    draw.rounded_rectangle(
        (int(width * 0.04), baseline - int(height * 0.008),
         int(width * 0.96), baseline + int(height * 0.012)),
        radius=int(height * 0.01),
        fill=NAVY,
    )

    # Thin navy birds: prove fine lines survive the pipeline.
    line_w = max(SS, int(height * 0.006))
    for fx, fy, s in ((0.12, 0.16, 1.0), (0.20, 0.10, 0.75), (0.27, 0.19, 0.6)):
        bx, by = px(fx, fy)
        wing = int(width * 0.030 * s)
        drop = int(height * 0.028 * s)
        draw.line((bx - wing, by, bx, by + drop), fill=NAVY, width=line_w)
        draw.line((bx, by + drop, bx + wing, by), fill=NAVY, width=line_w)

    return canvas.resize(SIZE, Image.Resampling.LANCZOS)


def make_checker_preview(image: Image.Image) -> Image.Image:
    """Composite the transparent result on a deterministic checkerboard."""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    draw = ImageDraw.Draw(background)
    tile = 48
    for row, y in enumerate(range(0, rgba.height, tile)):
        for col, x in enumerate(range(0, rgba.width, tile)):
            if (row + col) % 2:
                draw.rectangle(
                    (x, y, min(x + tile, rgba.width), min(y + tile, rgba.height)),
                    fill=(226, 230, 235, 255),
                )
    return Image.alpha_composite(background, rgba).convert("RGB")


def main() -> int:
    art = draw_mark().convert("RGB")
    art.save(ART_SOURCE, format="PNG")
    print(f"art source: {ART_SOURCE} {art.size}")

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "make_transparent_4k.py"),
            str(ART_SOURCE),
            "--background-scope",
            "all",
            "--bg",
            "white",
            "--edge-matte-strength",
            "1.0",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return result.returncode
    if not ART_TRANSPARENT.exists():
        print("expected transparent output missing", file=sys.stderr)
        return 1
    with Image.open(ART_TRANSPARENT) as transparent:
        preview = make_checker_preview(transparent)
    preview.save(ART_PREVIEW, format="PNG", optimize=True)
    print(f"transparent: {ART_TRANSPARENT}")
    print(f"checker preview: {ART_PREVIEW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
