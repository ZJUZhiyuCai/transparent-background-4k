#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import tempfile
from io import StringIO
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from make_transparent_4k import (
    BACKGROUND_SCOPES,
    DEFAULT_MAX_INPUT_PIXELS,
    DEFAULT_MAX_OUTPUT_PIXELS,
    ENHANCEMENT_MODES,
    OUTPUT_FORMATS,
    SUPPORTED_EXTS,
    default_output_path,
    process_image,
)


GENERATED_ARTIFACT_PATTERN = re.compile(
    r"(?:_transparent(?:_(?:4k|\d+px))?|_preview_checker|_preview_dark|_mask)$"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-remove plain backgrounds from image files.",
        epilog=(
            "Default: keep original dimensions. Use --target-width 3840 only when 4K output is "
            "explicitly wanted. The summary records whether each image was actually changed."
        ),
    )
    parser.add_argument("input_dir", help="Directory containing images.")
    parser.add_argument("--output-dir", help="Directory for outputs. Defaults to each image directory.")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=sorted(OUTPUT_FORMATS),
        default="png",
        help="Output format. Default: png.",
    )
    parser.add_argument(
        "--matte",
        help="JPEG background: white, black, or R,G,B. Required for JPEG.",
    )
    parser.add_argument(
        "--enhance",
        choices=sorted(ENHANCEMENT_MODES),
        default="off",
        help="Conservative alpha-safe sharpening. Default: off.",
    )
    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument("--target-width", type=int, help="Resize every output to this width.")
    size_group.add_argument("--target-long-edge", type=int, help="Resize every output to this long edge.")
    size_group.add_argument(
        "--keep-size",
        "--no-upscale",
        dest="no_upscale",
        action="store_true",
        help="Keep original dimensions. This is already the default.",
    )
    parser.add_argument(
        "--force-resize",
        action="store_true",
        help="Resize even when it shrinks an image. Requires a target size.",
    )
    parser.add_argument("--max-input-pixels", type=int, default=DEFAULT_MAX_INPUT_PIXELS)
    parser.add_argument("--max-output-pixels", type=int, default=DEFAULT_MAX_OUTPUT_PIXELS)
    parser.add_argument("--bg", default="auto")
    parser.add_argument("--bg-distance", type=float, default=32)
    parser.add_argument("--brightness-threshold", type=int, default=180)
    parser.add_argument("--saturation-threshold", type=int, default=45)
    parser.add_argument("--feather", type=float, default=1.2)
    parser.add_argument("--decontaminate", dest="decontaminate", action="store_true", default=True)
    parser.add_argument("--no-decontaminate", dest="decontaminate", action="store_false")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--preview-dark", action="store_true")
    parser.add_argument("--mask-debug", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--protect-dark", type=int, default=230)
    parser.add_argument("--protect-saturation", type=int, default=35)
    parser.add_argument("--protect-contrast", type=float, default=24)
    parser.add_argument("--content-distance", type=int, default=45)
    parser.add_argument("--background-scope", choices=sorted(BACKGROUND_SCOPES), default="edge")
    parser.add_argument("--edge-matte-strength", type=float, default=0.0)
    parser.add_argument("--edge-matte-radius", type=int, default=2)
    parser.add_argument("--edge-matte-saturation", type=int, default=30)
    parser.add_argument("--edge-matte-full-opacity-luma", type=int, default=80)
    parser.add_argument("--edge-matte-neutralize", action="store_true")
    parser.add_argument("--summary-json", help="Optional path for a JSON summary.")
    parser.add_argument("--summary-csv", help="Optional path for a CSV summary.")
    return parser


def image_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.iterdir()
        if (
            path.is_file()
            and path.suffix.lower() in SUPPORTED_EXTS
            and not path.name.startswith(".")
            and not is_generated_artifact(path)
        )
    )


def is_generated_artifact(path: Path) -> bool:
    stem = path.stem.lower()
    base, separator, suffix = stem.rpartition("_")
    if separator and suffix.isdigit():
        stem = base
    return GENERATED_ARTIFACT_PATTERN.search(stem) is not None


def disambiguate_batch_output(
    output_path: Path,
    source_path: Path,
    reserved_outputs: set[Path],
) -> Path:
    """Return a deterministic distinct destination for colliding input stems."""
    if output_path not in reserved_outputs:
        return output_path
    format_tag = source_path.suffix.lower().lstrip(".") or "image"
    candidate = output_path.with_name(f"{output_path.stem}_{format_tag}{output_path.suffix}")
    index = 2
    while candidate in reserved_outputs:
        candidate = output_path.with_name(
            f"{output_path.stem}_{format_tag}_{index}{output_path.suffix}"
        )
        index += 1
    return candidate


def write_text_atomic(path: str | Path, content: str) -> None:
    """Write a text summary without following a symbolic-link destination."""
    destination = Path(path)
    if destination.is_symlink():
        raise ValueError(f"Refusing to overwrite symbolic-link summary: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=destination.suffix or ".tmp",
        dir=destination.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        print(f"Error: input directory not found: {input_dir}", file=sys.stderr)
        return 1
    if args.no_upscale and args.force_resize:
        parser.error("--no-upscale and --force-resize cannot be used together.")
    if args.force_resize and args.target_width is None and args.target_long_edge is None:
        parser.error("--force-resize requires --target-width or --target-long-edge.")

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"Error: could not create output directory {output_dir}: {exc}", file=sys.stderr)
            return 1
    target_width = args.target_width

    rows: list[dict[str, str]] = []
    files = image_files(input_dir)
    if not files:
        print(f"No supported image files found in {input_dir}", file=sys.stderr)
        return 1

    reserved_outputs: set[Path] = set()
    for image_path in files:
        default_path = default_output_path(
            image_path,
            target_width=target_width,
            target_long_edge=args.target_long_edge,
            no_upscale=args.no_upscale,
            output_format=args.output_format,
        )
        output_path = output_dir / default_path.name if output_dir else default_path
        output_path = disambiguate_batch_output(output_path, image_path, reserved_outputs)
        reserved_outputs.add(output_path)
        try:
            result = process_image(
                input_path=image_path,
                output=output_path,
                target_width=target_width,
                target_long_edge=args.target_long_edge,
                no_upscale=args.no_upscale,
                force_resize=args.force_resize,
                max_input_pixels=args.max_input_pixels,
                max_output_pixels=args.max_output_pixels,
                bg=args.bg,
                bg_distance=args.bg_distance,
                brightness_threshold=args.brightness_threshold,
                saturation_threshold=args.saturation_threshold,
                feather=args.feather,
                decontaminate=args.decontaminate,
                preview=args.preview,
                preview_dark=args.preview_dark,
                mask_debug=args.mask_debug,
                overwrite=args.overwrite,
                protect_dark=args.protect_dark,
                protect_saturation=args.protect_saturation,
                protect_contrast=args.protect_contrast,
                content_distance=args.content_distance,
                background_scope=args.background_scope,
                edge_matte_strength=args.edge_matte_strength,
                edge_matte_radius=args.edge_matte_radius,
                edge_matte_saturation=args.edge_matte_saturation,
                edge_matte_full_opacity_luma=args.edge_matte_full_opacity_luma,
                edge_matte_neutralize=args.edge_matte_neutralize,
                output_format=args.output_format,
                matte=args.matte,
                enhance=args.enhance,
            )
            row = {
                "input": str(image_path),
                "status": "ok",
                "output": str(result.output_path),
                "preview": str(result.preview_path or ""),
                "dark_preview": str(result.dark_preview_path or ""),
                "mask": str(result.mask_path or ""),
                "size": f"{result.size[0]}x{result.size[1]}",
                "background_rgb": ",".join(str(channel) for channel in result.bg_rgb),
                "background_status": result.background_status,
                "removal_status": result.removal_status,
                "removed_fraction": f"{result.removed_fraction:.6f}",
                "transparent_fraction": f"{result.transparent_fraction:.6f}",
                "opaque_fraction": f"{result.opaque_fraction:.6f}",
                "output_format": result.output_format,
                "enhancement_status": result.enhancement_status,
                "scale_factor": f"{result.scale_factor:.6f}",
                "warnings": "; ".join(result.warnings),
                "error": "",
            }
            print(
                f"ok {image_path} -> {result.output_path} "
                f"({result.removal_status}; {result.output_format}; "
                f"enhancement={result.enhancement_status}; removed={result.removed_fraction:.1%})"
            )
        except Exception as exc:
            row = {
                "input": str(image_path),
                "status": "failed",
                "output": "",
                "preview": "",
                "dark_preview": "",
                "mask": "",
                "size": "",
                "background_rgb": "",
                "background_status": "",
                "removal_status": "",
                "removed_fraction": "",
                "transparent_fraction": "",
                "opaque_fraction": "",
                "output_format": args.output_format,
                "enhancement_status": "",
                "scale_factor": "",
                "warnings": "",
                "error": str(exc),
            }
            print(f"failed {image_path}: {exc}", file=sys.stderr)
        rows.append(row)

    try:
        if args.summary_json:
            write_text_atomic(args.summary_json, json.dumps(rows, indent=2))
        if args.summary_csv:
            buffer = StringIO()
            writer = csv.DictWriter(
                buffer,
                fieldnames=[
                    "input",
                    "status",
                    "output",
                    "preview",
                    "dark_preview",
                    "mask",
                    "size",
                    "background_rgb",
                    "background_status",
                    "removal_status",
                    "removed_fraction",
                    "transparent_fraction",
                    "opaque_fraction",
                    "output_format",
                    "enhancement_status",
                    "scale_factor",
                    "warnings",
                    "error",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
            write_text_atomic(args.summary_csv, buffer.getvalue())
    except (OSError, ValueError) as exc:
        print(f"Error: could not write batch summary: {exc}", file=sys.stderr)
        return 1

    failed = sum(row["status"] == "failed" for row in rows)
    if failed == 0:
        return 0
    if failed == len(rows):
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
