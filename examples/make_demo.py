#!/usr/bin/env python3
"""Generate the copyright-safe demo image used by the README."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1200
HEIGHT = 720
SCALE = 2
OUTPUT = Path(__file__).with_name("demo_source.png")


def scaled_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(value * SCALE for value in box)


def scaled_points(
    points: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    return [(x * SCALE, y * SCALE) for x, y in points]


def main() -> None:
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "white")
    draw = ImageDraw.Draw(image)

    # A synthetic logo mark with colored fills, dark outlines, and thin details.
    draw.ellipse(
        scaled_box((90, 105, 385, 400)),
        fill="#20B8CD",
        outline="#111827",
        width=4 * SCALE,
    )
    draw.rounded_rectangle(
        scaled_box((175, 175, 470, 470)),
        radius=42 * SCALE,
        fill="#F6C344",
        outline="#111827",
        width=4 * SCALE,
    )
    draw.polygon(
        scaled_points([(330, 90), (520, 260), (330, 430), (140, 260)]),
        fill="#EC5B76",
        outline="#111827",
        width=4 * SCALE,
    )
    draw.ellipse(
        scaled_box((254, 184, 406, 336)),
        fill="white",
        outline="#111827",
        width=3 * SCALE,
    )
    draw.line(
        scaled_points([(210, 260), (450, 260)]),
        fill="#111827",
        width=2 * SCALE,
    )
    draw.line(
        scaled_points([(330, 140), (330, 380)]),
        fill="#111827",
        width=2 * SCALE,
    )

    title_font = ImageFont.load_default(size=62 * SCALE)
    label_font = ImageFont.load_default(size=25 * SCALE)
    small_font = ImageFont.load_default(size=20 * SCALE)

    draw.text(
        (560 * SCALE, 170 * SCALE),
        "CLEAN EDGES",
        font=title_font,
        fill="#111827",
    )
    draw.text(
        (565 * SCALE, 265 * SCALE),
        "DETERMINISTIC BACKGROUND REMOVAL",
        font=label_font,
        fill="#111827",
    )
    draw.line(
        scaled_points([(565, 330), (1080, 330)]),
        fill="#111827",
        width=SCALE,
    )
    draw.line(
        scaled_points([(565, 360), (940, 360)]),
        fill="#111827",
        width=SCALE,
    )
    draw.line(
        scaled_points([(565, 390), (1020, 390)]),
        fill="#111827",
        width=SCALE,
    )
    draw.text(
        (565 * SCALE, 438 * SCALE),
        "TEXT  /  LINES  /  COLOR  /  ALPHA",
        font=small_font,
        fill="#111827",
    )

    draw.line(
        scaled_points([(90, 565), (1110, 565)]),
        fill="#111827",
        width=SCALE,
    )
    draw.text(
        (90 * SCALE, 595 * SCALE),
        "A SYNTHETIC, COPYRIGHT-SAFE DEMO ASSET",
        font=small_font,
        fill="#111827",
    )

    image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    image.save(OUTPUT, format="PNG", optimize=True)
    print(f"generated={OUTPUT}")
    print(f"size={image.size}")


if __name__ == "__main__":
    main()
