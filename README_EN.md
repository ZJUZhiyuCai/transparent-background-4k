# Transparent Background 4K

[![CI](https://github.com/ZJUZhiyuCai/transparent-background-4k/actions/workflows/ci.yml/badge.svg)](https://github.com/ZJUZhiyuCai/transparent-background-4k/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)

[简体中文](README.md) | English

A Codex image cutout Skill that turns white, near-white, light gray, or scanned
paper backgrounds transparent while preserving text, logos, thin lines, colors,
and antialiased edges. It can also perform a conservative optional enlargement
to 4K. Use it for presentation assets, scientific figures, transparent logos,
and web graphics.

It uses deterministic image processing rather than generative cutout methods:
it does not redraw brand marks, rewrite text, or invent detail.

## Preview

The artwork below is synthesized by the Pillow script in this repository and
uses no downloaded media. The left image is the white-background input; the
right image previews the same output PNG on a checkerboard so the removed
background is immediately visible.

| White-background mountain artwork | Transparent output (checkerboard preview) |
| --- | --- |
| ![White-background mountain artwork](assets/promo/promo_art_source.png) | ![Mountain artwork transparent checkerboard preview](assets/promo/promo_art_source_transparent_preview_checker.png) |

Chinese promotional poster:
[view or download `promo_cn.png`](assets/promo/promo_cn.png).

## Contents

- [Preview](#preview)
- [Why use it](#why-use-it)
- [Core capabilities](#core-capabilities)
- [Behavior and design principles](#behavior-and-design-principles)
- [Quick installation](#quick-installation)
- [Use it in Codex](#use-it-in-codex)
- [Common CLI examples](#common-cli-examples)
- [Output format comparison](#output-format-comparison)
- [Enhancement modes](#enhancement-modes)
- [Background scope](#background-scope)
- [Batch processing](#batch-processing)
- [Usage boundaries](#usage-boundaries)
- [Testing and validation](#testing-and-validation)
- [Project structure](#project-structure)

## Why use it

- **Content preservation**: text and thin lines in scientific figures,
  mechanism diagrams, and logos must not be redrawn. This tool performs
  pixel-level background removal and deterministic sharpening while keeping
  foreground content intact.
- **Correct transparency**: existing alpha is preserved byte-for-byte.
  Enlargements use premultiplied alpha to avoid white fringes and color bleed
  around transparent edges.
- **Explainable results**: every run reports the removal state, output format,
  enhancement state, and scale factor. Suspicious results produce quality
  warnings instead of being silently accepted.

## Core capabilities

- Remove white, near-white, light gray, or scanned paper backgrounds
- Preserve text, logos, thin lines, colors, antialiasing, and existing alpha
- Output transparent PNG by default, with lossless transparent WebP and LZW
  TIFF also supported
- Export JPEG only with an explicit `--matte` color because JPEG has no alpha
- Choose `--enhance off|auto|light` for alpha-safe deterministic sharpening
- Optionally enlarge to 4K with `--target-width 3840`, using premultiplied alpha
  to prevent edge color bleed
- Generate checkerboard previews, dark-background previews, and alpha masks
- Process one image or a directory, with JSON/CSV batch summaries
- Run on Python 3.10+ across macOS, Linux, Windows, and WSL

## Behavior and design principles

- **Remove only the background**: do not crop, rearrange, delete text, or trace
  the image into vectors.
- **Enhancement is sharpening, not super-resolution**: `--enhance` applies
  deterministic alpha-safe sharpening only to fully opaque foreground RGB.
  Alpha remains byte-for-byte unchanged. It can improve edge clarity, but it
  cannot recover real detail that is absent from the source. Enlargements above
  4x emit an explicit warning.
- **Stay conservative when uncertain**: `--bg auto` identifies a background
  only when the border is sufficiently opaque and bright. It skips removal
  when the border is already transparent or inconsistent instead of guessing.
- **Run locally**: the tool uses no generative model and downloads no model
  weights.

## Quick installation

Python 3.10 or newer is required. Install the repository in the Codex Skill
directory:

```text
${CODEX_HOME:-$HOME/.codex}/skills/transparent-background-4k
```

### macOS, Linux, and WSL

```bash
git clone https://github.com/ZJUZhiyuCai/transparent-background-4k.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/transparent-background-4k"

python3 -m pip install -r \
  "${CODEX_HOME:-$HOME/.codex}/skills/transparent-background-4k/requirements.txt"
```

### Windows PowerShell

```powershell
$CodexRoot = if ($env:CODEX_HOME) {
    $env:CODEX_HOME
} else {
    Join-Path $env:USERPROFILE ".codex"
}

$SkillDir = Join-Path $CodexRoot "skills\transparent-background-4k"
git clone https://github.com/ZJUZhiyuCai/transparent-background-4k.git $SkillDir
py -3 -m pip install -r (Join-Path $SkillDir "requirements.txt")
```

Replace `py -3` with `python` when Python is installed without the Windows
launcher. Under WSL, use the macOS/Linux commands and WSL paths rather than
PowerShell paths.

The dependencies are Pillow and numpy. OpenCV
(`opencv-python-headless`) accelerates connected-component and blur operations;
if it cannot be installed, the script automatically uses a slower
Pillow/Python fallback.

After installation, reopen Codex or start a new task so Codex discovers the
Skill.

## Use it in Codex

Describe the request in natural language; no command memorization is required:

```text
Make the white background of this image transparent and keep the original size.
```

```text
Enlarge this low-resolution logo to 3840 pixels wide, apply safe enhancement,
and export a lossless WebP.
```

```text
Process every image in this folder, export TIFF, and generate dark-background
previews.
```

Codex follows [SKILL.md](SKILL.md) to choose the background scope, enhancement
mode, output format, and previews.

## Common CLI examples

Run these commands from the repository root. If the repository is installed as
a Skill, replace `scripts/...` with the full path inside the Skill directory.
Quote paths that contain spaces or non-ASCII characters.

The simplest command removes a light background, keeps the original dimensions,
and writes `<stem>_transparent.png`:

```bash
python3 scripts/make_transparent_4k.py "input.jpg"
```

Enlarge a low-resolution image to 4K width, enable automatic enhancement, and
generate checkerboard and dark-background previews:

```bash
python3 scripts/make_transparent_4k.py "input.png" \
  --target-width 3840 \
  --enhance auto \
  --preview \
  --preview-dark
```

For a white-background logo or text image where enclosed letter holes should
also become transparent:

```bash
python3 scripts/make_transparent_4k.py "logo.png" \
  --background-scope all \
  --bg white \
  --edge-matte-strength 1.0 \
  --preview \
  --preview-dark
```

Other useful options include `--target-long-edge` to size by the long edge,
`--force-resize` to allow shrinking when a target is present, `--mask-debug`
to write an alpha mask, and `--overwrite` to replace existing files. Without
`--overwrite`, outputs receive a numeric suffix. See `--help` for every option.

## Output format comparison

| Format | Transparency | Good for |
| --- | --- | --- |
| PNG | Yes | Default choice, presentation assets, general transparent images |
| WebP | Yes, lossless | Web assets and smaller files |
| TIFF | Yes, LZW compression | Publishing and TIFF-compatible production |
| JPEG | No | Requires `--matte` to choose the composited background |

```bash
# PNG is the default
python3 scripts/make_transparent_4k.py "input.jpg"

# Lossless transparent WebP
python3 scripts/make_transparent_4k.py "input.jpg" --format webp

# LZW TIFF
python3 scripts/make_transparent_4k.py "input.jpg" --format tiff

# JPEG requires an explicit matte: white, black, or R,G,B
python3 scripts/make_transparent_4k.py "input.png" \
  --format jpeg \
  --matte white
```

`--matte` accepts `white`, `black`, or `R,G,B`, such as
`--matte 10,20,30`. An explicit output suffix can also select the format, for
example `-o output.webp`. If `--format` conflicts with the output suffix, the
program reports an error instead of guessing. Previews and masks are always PNG
and do not replace the final output.

## Enhancement modes

Use `--enhance` to control low-resolution enhancement:

| Mode | Behavior |
| --- | --- |
| `off` | Default; do not sharpen |
| `auto` | Enable only when the actual enlargement is at least 1.5x |
| `light` | Apply one light sharpening pass even without enlargement |

Enhancement blends RGB only within fully opaque foreground regions. Alpha
remains byte-for-byte unchanged, and fully transparent RGB is not polluted.
Enlargements above 4x warn that sharpening cannot recover real detail.

## Background scope

- `--background-scope edge` (default) removes only background connected to the
  canvas edge. It preserves enclosed white regions and is suitable for
  scientific figures, flowcharts, and images with intentional white fills.
- `--background-scope all` removes every region matching the background color.
  It is useful when letter holes in a logo or text must be transparent, but it
  can erase intentional white foreground.
- `--bg auto` (default) estimates a background only when the image border is
  sufficiently opaque and bright.
- `--bg white` or `--bg R,G,B` explicitly selects the color to remove.

Increase `--bg-distance` when a light background remains; decrease it when
light foreground is removed. See the Tuning section in [SKILL.md](SKILL.md) for
additional controls such as `--brightness-threshold`, `--protect-contrast`,
`--feather`, and `--edge-matte-*`.

## Batch processing

```bash
python3 scripts/batch_make_transparent_4k.py "INPUT_DIR" \
  --output-dir "OUTPUT_DIR" \
  --format webp \
  --enhance auto \
  --summary-json "OUTPUT_DIR/summary.json" \
  --summary-csv "OUTPUT_DIR/summary.csv"
```

Batch behavior:

- An individual failure does not interrupt the remaining files
- Exit status `0` means all files succeeded, `2` means partial success, and `1`
  means no files succeeded or setup failed
- Generated transparent images, previews, and masks are skipped on later runs
- Same-stem inputs with different suffixes, such as `figure.jpg` and
  `figure.png`, receive distinct output names
- JSON/CSV summaries record each image's processing status, format, and
  enhancement state

## Usage boundaries

- Designed for plain or nearly plain light backgrounds: illustrations, charts,
  icons, logos, text labels, mechanism diagrams, and plain-background
  screenshots.
- Not recommended for hair, glass, smoke, portraits, or complex natural
  photographs. Those edges require a generative cutout method beyond this
  deterministic tool.
- Does not connect to the network, download models, or perform generative
  super-resolution.
- The default input limit is 24,000,000 pixels and the default output limit is
  32,000,000 pixels. They can be changed with `--max-input-pixels` and
  `--max-output-pixels`, but should not be raised casually.
- Symbolic-link output paths are rejected. Final images, masks, previews, and
  summaries are written atomically to avoid partial files.

## Testing and validation

GitHub Actions runs an Ubuntu/Windows × Python 3.10/3.12 matrix on every push
and pull request.

```bash
python3 -B -m unittest discover -s tests
```

The current version contains 59 passing tests covering:

- White, near-white, and light gray background removal and dark-content
  protection
- Byte-for-byte preservation of existing alpha and unchanged RGB for existing
  semitransparent pixels
- The 1.5x automatic enhancement threshold and the warning above 4x
- Protection against RGB contamination in fully transparent pixels
- Lossless RGBA round trips for PNG, WebP, and TIFF
- Rejection of JPEG output without `--matte`
- Format inference and `--format`/suffix conflict detection
- Batch same-stem collision avoidance, partial-failure exit status, and summary
  fields
- Cross-platform handling of paths containing spaces and non-ASCII characters
- Rejection of symbolic-link output paths and input/output pixel limits

## Project structure

```text
transparent-background-4k/
├── .github/workflows/
│   └── ci.yml            # Ubuntu/Windows × Python 3.10/3.12
├── assets/promo/          # Chinese poster and reproducible generator
├── examples/             # Reproducible source, transparent output, previews
├── LICENSE
├── README.md
├── README_EN.md
├── SKILL.md              # Codex workflow, options, and guardrails
├── requirements.txt
├── agents/
│   └── openai.yaml       # Skill interface metadata
├── scripts/
│   ├── make_transparent_4k.py        # Single-image CLI
│   └── batch_make_transparent_4k.py  # Batch CLI
└── tests/                # Unit tests
```
