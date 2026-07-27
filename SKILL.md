---
name: transparent-background-4k
description: Convert white, near-white, light gray, or scanned-background images into transparent PNG, lossless WebP, or LZW TIFF, with matte-backed JPEG when requested. Preserve existing alpha, clean halos, safely enhance low-resolution enlargements, and optionally resize to 4K. Use for background removal, transparent assets, low-resolution logo or figure enhancement, PPT-ready exports, scientific figures that must not be redrawn, or transparent holes in logos and text.
---

# Transparent Background 4K

Remove plain light backgrounds deterministically. Preserve labels, lines, colors, antialiasing, and existing transparency; do not redraw or stylize the source.

## Workflow

1. Locate a JPG, JPEG, PNG, WEBP, TIF, or TIFF input.
2. Choose the background scope:
   - Use `edge` by default for scientific figures and diagrams. It preserves enclosed white regions.
   - Use `all` only for logos or text when every background-colored region, including letter holes, should become transparent. It can erase intentional white foreground.
   - Let `--bg auto` operate only when the image border is mostly opaque and mostly light. If the input already has a transparent border, preserve it and use `--bg white` or `--bg R,G,B` only when forced removal is intentional.
3. The default preserves the original pixel dimensions and does not sharpen. Add `--target-width 3840 --enhance auto` for a requested low-resolution 4K enlargement. Auto enhancement starts only at an actual 1.5x scale; use `light` only when sharpening is explicitly wanted without enlargement.
4. Choose the delivery format deliberately: PNG by default, lossless WebP for smaller transparent web assets, LZW TIFF for compatible production workflows, or JPEG only with an explicit matte color.
5. Run with `--preview`; add `--preview-dark` for slide assets or whenever halo quality matters. Previews and debug masks are always PNG.
6. Inspect both the alpha result and previews. Treat printed quality warnings as a reason to retune or inspect, not as proof of failure.
7. Tune conservatively. Preserve content when the correct interpretation is ambiguous.
8. Deliver the selected output file. Never substitute a preview for the real output.

## Commands

Require Python 3.10 or newer. Quote every input and output path so spaces and non-ASCII filenames remain intact.

On macOS, Linux, or WSL:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/transparent-background-4k"
python3 "$SKILL_DIR/scripts/make_transparent_4k.py" "INPUT_IMAGE" --preview --preview-dark
```

On native Windows PowerShell:

```powershell
$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }
$SkillDir = Join-Path $CodexRoot "skills\transparent-background-4k"
$SingleScript = Join-Path $SkillDir "scripts\make_transparent_4k.py"
$BatchScript = Join-Path $SkillDir "scripts\batch_make_transparent_4k.py"
py -3 $SingleScript "C:\Images\input.png" --preview --preview-dark
```

Use `python` instead of `py -3` when Python is installed without the Windows launcher. Under WSL, use the macOS/Linux commands and WSL paths rather than PowerShell paths.

Add `--target-width 3840 --enhance auto` when the user asks to enlarge a low-resolution source for a 4K-wide export. The same flags work on every platform:

```bash
python3 "$SKILL_DIR/scripts/make_transparent_4k.py" "INPUT_IMAGE" --target-width 3840 --enhance auto --preview --preview-dark
```

For a white-background logo or text asset whose enclosed holes should also be transparent:

```bash
python3 "$SKILL_DIR/scripts/make_transparent_4k.py" "INPUT_IMAGE" --background-scope all --bg white --edge-matte-strength 1.0 --preview --preview-dark
```

For batch conversion on macOS, Linux, or WSL:

```bash
python3 "$SKILL_DIR/scripts/batch_make_transparent_4k.py" "INPUT_DIR" --output-dir "OUTPUT_DIR" --target-width 3840 --enhance auto --format webp --preview --summary-json "OUTPUT_DIR/summary.json"
```

For batch conversion on Windows PowerShell:

```powershell
py -3 $BatchScript "C:\Images\Input Folder" --output-dir "C:\Images\Output Folder" --target-width 3840 --enhance auto --format webp --preview --summary-json "C:\Images\Output Folder\summary.json"
```

Batch processing continues after individual failures. Exit status is `0` when all files succeed, `2` for partial success, and `1` when none succeed or setup fails. Generated transparent, preview, and mask files are skipped on later runs. Same-stem inputs such as `figure.jpg` and `figure.png` receive distinct outputs.

Select another format with `--format`, or let an explicit output extension select it:

```bash
python3 "$SKILL_DIR/scripts/make_transparent_4k.py" "INPUT_IMAGE" --format webp
python3 "$SKILL_DIR/scripts/make_transparent_4k.py" "INPUT_IMAGE" --format tiff
python3 "$SKILL_DIR/scripts/make_transparent_4k.py" "INPUT_IMAGE" --format jpeg --matte white
```

## Outputs

```text
<stem>_transparent.png
<stem>_transparent.webp
<stem>_transparent.tiff
<stem>_transparent.jpg
<stem>_transparent_4k.png
<stem>_transparent_<size>px.png
<stem>_transparent_4k_preview_checker.png
<stem>_transparent_4k_preview_dark.png
<stem>_transparent_4k_mask.png
```

Create the mask only with `--mask-debug`. Transparent outputs support `.png`, `.webp`, `.tif`, and `.tiff`; `.jpg` and `.jpeg` require `--matte white|black|R,G,B` and produce RGB without transparency. If `--format` and the output extension conflict, the command fails instead of guessing. Existing files receive a numeric suffix unless `--overwrite` is set. The CLI reports `removal_status`, `background_status`, `output_format`, `enhancement_status`, and `scale_factor`; batch JSON and CSV summaries include the same enhancement and format fields.

## Tuning

- `--bg auto|white|R,G,B`: Estimate a reliable opaque border color, force white, or provide an exact RGB background. Auto mode deliberately skips removal on a mostly transparent or inconsistent border.
- `--background-scope edge|all`: Preserve enclosed background-colored regions or remove every match. Keep `edge` unless the user explicitly wants transparent logo/text holes.
- `--bg-distance`: Increase when light background remains; decrease when pale content is removed.
- `--brightness-threshold`: Lower for darker scans. Default `180` supports light gray backgrounds.
- `--saturation-threshold`: Increase for slightly tinted paper; decrease to protect pale colors.
- `--protect-contrast`: Increase if gray background is being preserved as content; decrease only when genuinely low-contrast details disappear.
- `--feather`: Reduce if thin lines look soft.
- `--edge-matte-strength 0.8-1.0`: Reduce neutral white/gray edge halos on dark slides.
- `--edge-matte-saturation 255 --edge-matte-neutralize`: Suppress screenshot LCD red/blue fringes. Use only after inspecting a dark preview.
- `--target-width 3840`: Request a 3840 px wide export. Without a target, the skill keeps the original dimensions. Add `--force-resize` to shrink larger inputs too; it requires a target size.
- `--target-long-edge 3840`: Size by the long edge instead of width.
- `--keep-size` / `--no-upscale`: Keep the original dimensions; this is already the default.
- `--enhance off|auto|light`: Keep sharpening off, apply it automatically at 1.5x enlargement or above, or force a light pass. Enhancement sharpens only fully opaque foreground interiors and preserves alpha byte-for-byte.
- `--format png|webp|tiff|jpeg`: Choose the output encoding. PNG remains the default; WebP and TIFF retain alpha losslessly.
- `--matte white|black|R,G,B`: Required for JPEG because JPEG cannot store transparency.
- `--max-input-pixels`: Reject suspiciously large inputs before decoding. Default: `24,000,000` pixels.
- `--max-output-pixels`: Reject oversized resize requests before allocation. Default: `32,000,000` pixels.

Resizing uses premultiplied alpha to prevent transparent-pixel color bleed. Edge decontamination skips pixels that were already semi-transparent in the input. Enhancement is deterministic sharpening, not generative super-resolution: it can improve edge clarity but cannot recover true detail. Any enlargement above 4x emits this warning explicitly.

## Guardrails

- Prefer this skill for figures, diagrams, icons, labels, arrows, mechanism drawings, logos, and plain-background screenshots.
- Do not use it as the default for people, hair, glass, natural photos, or complex scenes.
- Do not crop, recolor, relayout, remove labels, or alter foreground shadows without an explicit request.
- Do not describe enhancement as restored or reconstructed detail. For tiny or heavily compressed sources, report the limitation and prefer the smallest useful enlargement.
- Keep `--background-scope edge` when intentional white fills may exist.
- Do not raise pixel limits casually. Larger images allocate several working buffers during masking and resizing.
- Treat symbolic-link output and summary paths as invalid. Final images, masks, previews, and batch summaries are written atomically to avoid partial files.
- Return the checker preview when quality is uncertain and the dark preview when the asset will be placed on a dark slide.

## Dependencies

Install the accelerated dependency set on macOS, Linux, or WSL:

```bash
python3 -m pip install -r "$SKILL_DIR/requirements.txt"
```

Install it on native Windows PowerShell:

```powershell
py -3 -m pip install -r (Join-Path $SkillDir "requirements.txt")
```

Use Pillow and numpy. Use OpenCV for faster connected-component and blur operations. If OpenCV cannot be installed on a platform, install the core dependencies directly with `python -m pip install "Pillow>=10.0.0" "numpy>=1.24.0"`; the script retains a slower Pillow/Python fallback. Normal processing does not require symbolic-link privileges.
