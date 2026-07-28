#!/usr/bin/env python3
"""Generate the Chinese promotional poster for Transparent Background 4K."""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


WIDTH = 1080
HEIGHT = 5000
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).with_name("promo_cn.png")
FONT_PATH = Path(
    os.environ.get(
        "PROMO_FONT_PATH",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    )
)

INK = "#111827"
DEEP = "#0B1220"
PAPER = "#F4F6F8"
WHITE = "#FFFFFF"
MUTED = "#5B6472"
LINE = "#D7DCE2"
CYAN = "#20B8CD"
CORAL = "#EC5B76"
YELLOW = "#F6C344"
GREEN = "#12A67D"
VIOLET = "#6C5CE7"


def load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size=size)
    except OSError as exc:
        raise RuntimeError(
            f"Required Chinese font could not be loaded: {FONT_PATH}"
        ) from exc


def fit_image(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        return ImageOps.fit(
            source.convert("RGB"),
            size,
            method=Image.Resampling.LANCZOS,
        )


def contain_rgba(path: Path, box: tuple[int, int]) -> Image.Image:
    """Load an image with alpha and shrink it to fit inside the box."""
    with Image.open(path) as source:
        image = source.convert("RGBA")
    image.thumbnail(box, Image.Resampling.LANCZOS)
    return image


def draw_checkerboard(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    tile: int = 22,
) -> None:
    """Fill a rectangle with the classic transparency checkerboard."""
    left, top, right, bottom = box
    draw.rectangle(box, fill="#FFFFFF")
    for row, y in enumerate(range(top, bottom, tile)):
        for col, x in enumerate(range(left, right, tile)):
            if (row + col) % 2 == 0:
                continue
            draw.rectangle(
                (x, y, min(x + tile, right), min(y + tile, bottom)),
                fill="#E2E6EB",
            )


def wrapped_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for char in paragraph:
            candidate = current + char
            width = draw.textbbox((0, 0), candidate, font=font)[2]
            if current and width > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    max_width: int,
    spacing: int,
) -> int:
    x, y = xy
    line_height = font.size + spacing
    for line in wrapped_lines(draw, text, font, max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def draw_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: str,
    font: ImageFont.FreeTypeFont,
) -> None:
    x, y = xy
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    draw.rounded_rectangle(
        (x, y, x + width + 44, y + 54),
        radius=8,
        outline=color,
        width=2,
    )
    draw.text((x + 22, y + 10), text, font=font, fill=color)


def draw_capability(
    draw: ImageDraw.ImageDraw,
    y: int,
    number: str,
    title: str,
    body: str,
    color: str,
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> None:
    draw.rounded_rectangle((80, y, 154, y + 74), radius=8, fill=color)
    number_box = draw.textbbox((0, 0), number, font=fonts["number"])
    number_width = number_box[2] - number_box[0]
    draw.text(
        (117 - number_width / 2, y + 11),
        number,
        font=fonts["number"],
        fill=INK,
    )
    draw.text((190, y - 3), title, font=fonts["cap_title"], fill=INK)
    draw_wrapped(
        draw,
        (190, y + 58),
        body,
        fonts["body"],
        MUTED,
        800,
        9,
    )
    draw.line((190, y + 185, 1000, y + 185), fill=LINE, width=2)


def main() -> None:
    fonts = {
        "eyebrow": load_font(28),
        "hero": load_font(82),
        "tagline": load_font(42),
        "body": load_font(28),
        "label": load_font(22),
        "section": load_font(56),
        "caption": load_font(24),
        "number": load_font(36),
        "cap_title": load_font(40),
        "code": load_font(21),
        "footer": load_font(48),
        "url": load_font(27),
    }

    source_path = Path(__file__).with_name("promo_art_source.png")
    transparent_path = Path(__file__).with_name(
        "promo_art_source_transparent.png"
    )
    for required in (source_path, transparent_path):
        if not required.is_file():
            raise FileNotFoundError(f"Required demo asset is missing: {required}")

    canvas = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(canvas)

    # Hero
    draw.rectangle((0, 0, WIDTH, 900), fill=INK)
    draw.rectangle((0, 0, 18, 900), fill=CYAN)
    draw.text(
        (80, 82),
        "OPEN-SOURCE CODEX SKILL",
        font=fonts["eyebrow"],
        fill=CYAN,
    )
    draw.text(
        (80, 154),
        "Transparent\nBackground 4K",
        font=fonts["hero"],
        fill=WHITE,
        spacing=8,
    )
    draw.text(
        (80, 405),
        "把白底图片变成干净、可复用的透明资产",
        font=fonts["tagline"],
        fill=WHITE,
    )
    draw_wrapped(
        draw,
        (80, 495),
        "不重画 Logo，不改写文字；保留细线、颜色与抗锯齿边缘，可选安全放大到 4K。",
        fonts["body"],
        "#CBD5E1",
        900,
        14,
    )
    draw_label(draw, (80, 650), "确定性抠图", CYAN, fonts["label"])
    draw_label(draw, (300, 650), "透明度安全", CORAL, fonts["label"])
    draw_label(draw, (520, 650), "Python 3.10+", YELLOW, fonts["label"])
    draw.line((80, 790, 1000, 790), fill="#344054", width=2)
    draw.rectangle((80, 826, 430, 842), fill=CYAN)
    draw.rectangle((430, 826, 740, 842), fill=CORAL)
    draw.rectangle((740, 826, 1000, 842), fill=YELLOW)

    # Transparency proof: same PNG on checkerboard and colored boards
    draw.rectangle((0, 900, WIDTH, 2420), fill=WHITE)
    draw.text(
        (80, 1010),
        "放上彩色底，透明一眼可见",
        font=fonts["section"],
        fill=INK,
    )
    draw.text(
        (80, 1095),
        "同一张自制图形，由仓库 CLI 真实处理，非贴图示意。",
        font=fonts["body"],
        fill=MUTED,
    )

    art_before = contain_rgba(source_path, (420, 315))
    art_alpha = contain_rgba(transparent_path, (420, 315))

    draw.rounded_rectangle(
        (80, 1180, 525, 1530), radius=10, fill=PAPER, outline=LINE, width=2
    )
    canvas.paste(
        art_before,
        (80 + (445 - art_before.width) // 2, 1180 + (350 - art_before.height) // 2),
        art_before,
    )
    draw_checkerboard(draw, (555, 1180, 1000, 1530))
    draw.rounded_rectangle(
        (555, 1180, 1000, 1530), radius=10, outline=LINE, width=2
    )
    canvas.paste(
        art_alpha,
        (555 + (445 - art_alpha.width) // 2, 1180 + (350 - art_alpha.height) // 2),
        art_alpha,
    )
    draw.text((80, 1560), "处理前 · 白底 PNG", font=fonts["caption"], fill=MUTED)
    draw.text(
        (555, 1560),
        "处理后 · 透明 PNG（棋盘格示透明）",
        font=fonts["caption"],
        fill=MUTED,
    )

    draw.text(
        (80, 1680),
        "同一张透明 PNG，横跨三种底色",
        font=fonts["cap_title"],
        fill=INK,
    )
    strip = (80, 1770, 1000, 2210)
    panel_width = (strip[2] - strip[0]) // 3
    # Panel hues deliberately avoid the artwork palette so every peak stays visible.
    for index, color in enumerate(("#38BDF8", "#F97316", INK)):
        draw.rectangle(
            (
                strip[0] + index * panel_width,
                strip[1],
                strip[0] + (index + 1) * panel_width if index < 2 else strip[2],
                strip[3],
            ),
            fill=color,
        )
    art_strip = contain_rgba(transparent_path, (860, 400))
    canvas.paste(
        art_strip,
        (
            strip[0] + (strip[2] - strip[0] - art_strip.width) // 2,
            strip[1] + (strip[3] - strip[1] - art_strip.height) // 2,
        ),
        art_strip,
    )
    draw.text(
        (80, 2250),
        "没有白边、没有底色残留：PPT、海报、深色页面直接贴。",
        font=fonts["body"],
        fill=MUTED,
    )

    # Capabilities
    draw.rectangle((0, 2420, WIDTH, 3570), fill=PAPER)
    draw.text(
        (80, 2520),
        "四件事，解决素材复用难题",
        font=fonts["section"],
        fill=INK,
    )
    draw_capability(
        draw,
        2670,
        "01",
        "确定性抠图",
        "像素级移除浅色背景，不生成、不重绘，科研插图与品牌文字更可控。",
        CYAN,
        fonts,
    )
    draw_capability(
        draw,
        2890,
        "02",
        "透明度正确",
        "保留已有 alpha；放大采用 premultiplied alpha，减少透明边缘渗色。",
        CORAL,
        fonts,
    )
    draw_capability(
        draw,
        3110,
        "03",
        "保守画质增强",
        "1.5× 以上可自动锐化；超过 4× 明确警告，绝不宣称恢复真实细节。",
        YELLOW,
        fonts,
    )
    draw_capability(
        draw,
        3330,
        "04",
        "多格式与批处理",
        "透明 PNG、无损 WebP、LZW TIFF；JPEG 必须指定 matte，批量结果可汇总。",
        GREEN,
        fonts,
    )

    # Installation
    draw.rectangle((0, 3570, WIDTH, 4470), fill=INK)
    draw.text(
        (80, 3675),
        "三行开始使用",
        font=fonts["section"],
        fill=WHITE,
    )
    draw.text(
        (80, 3755),
        "Python 3.10+ · macOS / Linux / Windows / WSL",
        font=fonts["body"],
        fill="#CBD5E1",
    )
    draw.rounded_rectangle(
        (80, 3855, 1000, 4295),
        radius=8,
        fill=DEEP,
        outline="#344054",
        width=2,
    )
    commands = [
        "git clone https://github.com/ZJUZhiyuCai/transparent-background-4k.git",
        "cd transparent-background-4k",
        "python3 -m pip install -r requirements.txt",
    ]
    command_colors = [CYAN, CORAL, YELLOW]
    for index, (command, color) in enumerate(zip(commands, command_colors), 1):
        y = 3925 + (index - 1) * 112
        draw.rounded_rectangle((115, y - 4, 165, y + 46), radius=6, fill=color)
        draw.text(
            (130, y + 5),
            str(index),
            font=fonts["label"],
            fill=INK,
        )
        draw.text(
            (195, y),
            command,
            font=fonts["code"],
            fill=WHITE,
        )
        if index < 3:
            draw.line((195, y + 70, 950, y + 70), fill="#283548", width=2)
    draw.text(
        (80, 4350),
        "也可以直接在 Codex 里说：把这张图的白色背景变透明。",
        font=fonts["body"],
        fill="#CBD5E1",
    )

    # Footer
    draw.rectangle((0, 4470, WIDTH, HEIGHT), fill=WHITE)
    draw.rectangle((0, 4470, WIDTH, 4490), fill=YELLOW)
    draw.text(
        (80, 4590),
        "开源、可复现、即装即用",
        font=fonts["footer"],
        fill=INK,
    )
    draw.text(
        (80, 4700),
        "github.com/ZJUZhiyuCai/transparent-background-4k",
        font=fonts["url"],
        fill=CORAL,
    )
    draw_wrapped(
        draw,
        (80, 4790),
        "适合 PPT 素材、科研插图、Logo、图标与纯底截图。",
        fonts["body"],
        MUTED,
        900,
        12,
    )
    draw.rectangle((80, 4920, 410, 4936), fill=CYAN)
    draw.rectangle((410, 4920, 705, 4936), fill=CORAL)
    draw.rectangle((705, 4920, 1000, 4936), fill=YELLOW)

    canvas.save(OUTPUT, format="PNG", optimize=True)
    print(f"font={FONT_PATH}")
    print(f"generated={OUTPUT}")
    print(f"size={canvas.size}")


if __name__ == "__main__":
    main()
