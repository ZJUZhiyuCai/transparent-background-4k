#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import sys
import tempfile
import warnings
from collections import deque
from dataclasses import dataclass
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only on missing dependency
    np = None

try:
    import cv2
except ImportError:  # pragma: no cover - optional acceleration
    cv2 = None

from PIL import Image, ImageChops, ImageFilter, ImageOps


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
BACKGROUND_SCOPES = {"edge", "all"}
OUTPUT_FORMATS = {"png", "webp", "tiff", "jpeg"}
OUTPUT_EXTENSIONS = {
    "png": ".png",
    "webp": ".webp",
    "tiff": ".tiff",
    "jpeg": ".jpg",
}
EXTENSION_FORMATS = {
    ".png": "png",
    ".webp": "webp",
    ".tif": "tiff",
    ".tiff": "tiff",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
}
ENHANCEMENT_MODES = {"off", "auto", "light"}
DEFAULT_MAX_INPUT_PIXELS = 24_000_000
DEFAULT_MAX_OUTPUT_PIXELS = 32_000_000
MIN_OPAQUE_BORDER_FRACTION = 0.75
MIN_LIGHT_BORDER_FRACTION = 0.60


@dataclass(frozen=True)
class ProcessResult:
    output_path: Path
    preview_path: Path | None
    dark_preview_path: Path | None
    mask_path: Path | None
    bg_rgb: tuple[int, int, int]
    background_status: str
    size: tuple[int, int]
    removal_status: str
    removed_fraction: float
    transparent_fraction: float
    opaque_fraction: float
    output_format: str
    enhancement_status: str
    scale_factor: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class BackgroundEstimate:
    rgb: tuple[int, int, int]
    opaque_border_fraction: float
    reliable: bool


def _require_numpy() -> None:
    if np is None:
        raise RuntimeError(
            "Missing dependency: numpy. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        )


def _positive_int(value: int, option_name: str) -> int:
    """Validate and return a positive integer option value."""
    if isinstance(value, bool):
        raise ValueError(f"{option_name} must be a positive integer.")
    try:
        integer = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{option_name} must be a positive integer.") from exc
    if integer <= 0 or integer != value:
        raise ValueError(f"{option_name} must be a positive integer.")
    return integer


def load_image(
    path: str | Path,
    max_input_pixels: int = DEFAULT_MAX_INPUT_PIXELS,
) -> Image.Image:
    """Load image, apply EXIF transpose, return RGBA PIL image."""
    pixel_limit = _positive_int(max_input_pixels, "--max-input-pixels")
    image_path = Path(path)
    if not image_path.exists():
        raise FileNotFoundError(f"Input image not found: {image_path}")
    if image_path.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError(f"Unsupported image type: {image_path.suffix}")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(image_path) as img:
                pixels = img.width * img.height
                if pixels > pixel_limit:
                    raise ValueError(
                        f"Input image has {pixels:,} pixels, exceeding --max-input-pixels "
                        f"({pixel_limit:,})."
                    )
                img = ImageOps.exif_transpose(img)
                return img.convert("RGBA")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Input image is rejected as a decompression bomb.") from exc


def _border_pixels(rgba: "np.ndarray") -> "np.ndarray":
    """Return RGBA pixels from a proportional border without a full-size mask."""
    _require_numpy()
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("Expected an RGBA array with shape HxWx4.")

    h, w = rgba.shape[:2]
    if h == 0 or w == 0:
        raise ValueError("Input image must not be empty.")
    border_width = int(round(min(h, w) * 0.02))
    border_width = max(8, border_width)
    border_width = min(80, border_width, h, w)

    strips = [
        rgba[:border_width, :, :].reshape(-1, 4),
        rgba[-border_width:, :, :].reshape(-1, 4),
    ]
    if h > border_width * 2:
        strips.extend(
            [
                rgba[border_width:-border_width, :border_width, :].reshape(-1, 4),
                rgba[border_width:-border_width, -border_width:, :].reshape(-1, 4),
            ]
        )
    return np.concatenate(strips, axis=0)


def estimate_background(rgba: "np.ndarray") -> BackgroundEstimate:
    """Estimate a light border background and report whether it is trustworthy."""
    _require_numpy()
    border_pixels = _border_pixels(rgba)
    opaque = border_pixels[:, 3] >= 250
    opaque_border_fraction = float(np.count_nonzero(opaque)) / max(1, len(border_pixels))
    if not opaque.any():
        return BackgroundEstimate((255, 255, 255), opaque_border_fraction, False)

    rgb = border_pixels[opaque, :3].astype(np.int16)
    high_light = rgb.min(axis=1) >= 160
    low_saturation = (rgb.max(axis=1) - rgb.min(axis=1)) <= 45
    candidates = rgb[high_light & low_saturation]
    if len(candidates) < 10:
        return BackgroundEstimate((255, 255, 255), opaque_border_fraction, False)
    light_border_fraction = float(len(candidates)) / max(1, len(rgb))

    quantized = (candidates // 8).astype(np.int16)
    bins, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant_bin = bins[int(np.argmax(counts))]
    dominant = candidates[np.all(quantized == dominant_bin, axis=1)]
    if len(dominant) >= max(10, int(round(len(candidates) * 0.08))):
        candidates = dominant

    median = np.median(candidates, axis=0)
    rgb_estimate = tuple(int(round(float(channel))) for channel in median)
    reliable = (
        opaque_border_fraction >= MIN_OPAQUE_BORDER_FRACTION
        and light_border_fraction >= MIN_LIGHT_BORDER_FRACTION
    )
    return BackgroundEstimate(rgb_estimate, opaque_border_fraction, reliable)


def estimate_background_rgb(rgba: "np.ndarray") -> tuple[int, int, int]:
    """Estimate only the background color for callers that do not need confidence."""
    return estimate_background(rgba).rgb


def build_candidate_background_mask(
    rgb: "np.ndarray",
    bg_rgb: tuple[int, int, int],
    bg_distance: float,
    brightness_threshold: int,
    saturation_threshold: int,
) -> "np.ndarray":
    """Return boolean candidate background mask."""
    _require_numpy()
    rgb_f = rgb.astype(np.float32)
    bg = np.array(bg_rgb, dtype=np.float32)
    color_distance = np.linalg.norm(rgb_f - bg, axis=2)
    max_channel = rgb.max(axis=2)
    saturation_proxy = max_channel - rgb.min(axis=2)
    return (
        (color_distance <= float(bg_distance))
        & (max_channel >= int(brightness_threshold))
        & (saturation_proxy <= int(saturation_threshold))
    )


def keep_edge_connected_background(candidate_mask: "np.ndarray") -> "np.ndarray":
    """Return candidate background connected to the image border."""
    _require_numpy()
    candidate = candidate_mask.astype(bool)
    if candidate.size == 0 or not candidate.any():
        return np.zeros_like(candidate, dtype=bool)

    if cv2 is not None:
        mask_u8 = candidate.astype(np.uint8)
        _, labels = cv2.connectedComponents(mask_u8, connectivity=8)
        border_labels = np.unique(
            np.concatenate(
                [
                    labels[0, :],
                    labels[-1, :],
                    labels[:, 0],
                    labels[:, -1],
                ]
            )
        )
        border_labels = border_labels[border_labels != 0]
        if border_labels.size == 0:
            return np.zeros_like(candidate, dtype=bool)
        return np.isin(labels, border_labels)

    return _edge_connected_background_fallback(candidate)


def _edge_connected_background_fallback(candidate: "np.ndarray") -> "np.ndarray":
    h, w = candidate.shape
    seen = np.zeros_like(candidate, dtype=bool)
    queue: deque[tuple[int, int]] = deque()

    def add(y: int, x: int) -> None:
        if candidate[y, x] and not seen[y, x]:
            seen[y, x] = True
            queue.append((y, x))

    for x in range(w):
        add(0, x)
        add(h - 1, x)
    for y in range(h):
        add(y, 0)
        add(y, w - 1)

    while queue:
        y, x = queue.popleft()
        for ny in (y - 1, y, y + 1):
            for nx in (x - 1, x, x + 1):
                if ny == y and nx == x:
                    continue
                if 0 <= ny < h and 0 <= nx < w and candidate[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    queue.append((ny, nx))
    return seen


def build_protect_mask(
    rgb: "np.ndarray",
    bg_rgb: tuple[int, int, int],
    text_dark_threshold: int = 230,
    color_content_threshold: int = 35,
    content_distance_threshold: int = 45,
    dark_content_distance_threshold: float = 24,
) -> "np.ndarray":
    """Return pixels that should remain fully opaque."""
    _require_numpy()
    rgb_i = rgb.astype(np.int16)
    max_channel = rgb_i.max(axis=2)
    saturation_proxy = max_channel - rgb_i.min(axis=2)
    bg = np.array(bg_rgb, dtype=np.float32)
    color_distance = np.linalg.norm(rgb.astype(np.float32) - bg, axis=2)
    return (
        (
            (max_channel <= int(text_dark_threshold))
            & (color_distance >= float(dark_content_distance_threshold))
        )
        | (saturation_proxy >= int(color_content_threshold))
        | (color_distance >= float(content_distance_threshold))
    )


def build_alpha_mask(
    rgb: "np.ndarray",
    edge_bg_mask: "np.ndarray",
    bg_rgb: tuple[int, int, int],
    feather: float,
    original_alpha: "np.ndarray | None" = None,
    text_dark_threshold: int = 230,
    color_content_threshold: int = 35,
    content_distance_threshold: int = 45,
    dark_content_distance_threshold: float = 24,
) -> "np.ndarray":
    """Return uint8 alpha mask."""
    _require_numpy()
    edge_bg = edge_bg_mask.astype(bool)
    foreground = (~edge_bg).astype(np.uint8) * 255

    if feather and feather > 0:
        if cv2 is not None:
            alpha = cv2.GaussianBlur(
                foreground,
                ksize=(0, 0),
                sigmaX=float(feather),
                sigmaY=float(feather),
                borderType=cv2.BORDER_REPLICATE,
            )
        else:
            alpha = np.asarray(
                Image.fromarray(foreground, mode="L").filter(
                    ImageFilter.GaussianBlur(radius=float(feather))
                )
            )
    else:
        alpha = foreground.copy()

    alpha = np.array(alpha, dtype=np.uint8, copy=True)
    protect_mask = build_protect_mask(
        rgb,
        bg_rgb,
        text_dark_threshold=text_dark_threshold,
        color_content_threshold=color_content_threshold,
        content_distance_threshold=content_distance_threshold,
        dark_content_distance_threshold=dark_content_distance_threshold,
    )
    alpha[protect_mask] = 255

    if original_alpha is not None:
        alpha = np.minimum(alpha, original_alpha.astype(np.uint8))
    return alpha


def expand_mask(mask: "np.ndarray", radius: int) -> "np.ndarray":
    """Return mask expanded by radius pixels."""
    _require_numpy()
    radius = int(radius)
    if radius <= 0:
        return mask.astype(bool)
    mask_u8 = mask.astype(np.uint8) * 255
    size = radius * 2 + 1
    if cv2 is not None:
        kernel = np.ones((size, size), dtype=np.uint8)
        expanded = cv2.dilate(mask_u8, kernel, iterations=1)
    else:
        expanded = np.asarray(
            Image.fromarray(mask_u8, mode="L").filter(ImageFilter.MaxFilter(size=size))
        )
    return expanded > 0


def apply_edge_matte_alpha(
    rgb: "np.ndarray",
    alpha: "np.ndarray",
    edge_bg_mask: "np.ndarray",
    bg_rgb: tuple[int, int, int],
    strength: float,
    radius: int = 2,
    saturation_threshold: int = 30,
    full_opacity_luma: int = 80,
    eligible_mask: "np.ndarray | None" = None,
) -> "np.ndarray":
    """Lower alpha for neutral anti-aliased edge pixels matted against a light background."""
    _require_numpy()
    strength = float(strength)
    if strength <= 0:
        return alpha
    strength = min(strength, 1.0)

    alpha_out = np.array(alpha, dtype=np.uint8, copy=True)
    edge_bg = edge_bg_mask.astype(bool)
    edge_band = expand_mask(edge_bg, radius=radius) & (~edge_bg) & (alpha_out > 0)
    if eligible_mask is not None:
        edge_band &= eligible_mask.astype(bool)
    if not edge_band.any():
        return alpha_out

    rgb_f = rgb.astype(np.float32)
    luma = 0.2126 * rgb_f[:, :, 0] + 0.7152 * rgb_f[:, :, 1] + 0.0722 * rgb_f[:, :, 2]
    bg_luma = float(0.2126 * bg_rgb[0] + 0.7152 * bg_rgb[1] + 0.0722 * bg_rgb[2])
    if bg_luma <= 1:
        return alpha_out

    rgb_i = rgb.astype(np.int16)
    saturation_proxy = rgb_i.max(axis=2) - rgb_i.min(axis=2)
    neutral_edge = saturation_proxy <= int(saturation_threshold)

    candidates = (
        edge_band
        & neutral_edge
        & (luma > float(full_opacity_luma))
        & (luma < bg_luma)
    )
    if not candidates.any():
        return alpha_out

    matte_alpha = np.clip((1.0 - (luma / bg_luma)) * 255.0, 0, 255)
    target_alpha = np.minimum(alpha_out.astype(np.float32), matte_alpha)
    blended = alpha_out.astype(np.float32) * (1.0 - strength) + target_alpha * strength
    alpha_out[candidates] = np.clip(np.rint(blended[candidates]), 0, 255).astype(np.uint8)
    return alpha_out


def edge_matte_candidates(
    rgb: "np.ndarray",
    alpha: "np.ndarray",
    edge_bg_mask: "np.ndarray",
    bg_rgb: tuple[int, int, int],
    radius: int,
    saturation_threshold: int,
    full_opacity_luma: int,
    eligible_mask: "np.ndarray | None" = None,
) -> "np.ndarray":
    """Return neutral or subpixel edge pixels likely matted against a light background."""
    _require_numpy()
    edge_bg = edge_bg_mask.astype(bool)
    edge_band = expand_mask(edge_bg, radius=radius) & (~edge_bg) & (alpha > 0) & (alpha < 255)
    if eligible_mask is not None:
        edge_band &= eligible_mask.astype(bool)
    if not edge_band.any():
        return edge_band

    rgb_f = rgb.astype(np.float32)
    luma = 0.2126 * rgb_f[:, :, 0] + 0.7152 * rgb_f[:, :, 1] + 0.0722 * rgb_f[:, :, 2]
    bg_luma = float(0.2126 * bg_rgb[0] + 0.7152 * bg_rgb[1] + 0.0722 * bg_rgb[2])
    rgb_i = rgb.astype(np.int16)
    saturation_proxy = rgb_i.max(axis=2) - rgb_i.min(axis=2)
    return (
        edge_band
        & (saturation_proxy <= int(saturation_threshold))
        & (luma > float(full_opacity_luma))
        & (luma < bg_luma)
    )


def neutralize_edge_matte_rgb(
    rgb: "np.ndarray",
    alpha: "np.ndarray",
    edge_bg_mask: "np.ndarray",
    bg_rgb: tuple[int, int, int],
    radius: int = 2,
    saturation_threshold: int = 255,
    full_opacity_luma: int = 80,
    eligible_mask: "np.ndarray | None" = None,
) -> "np.ndarray":
    """Desaturate edge-matte pixels to suppress LCD subpixel color fringes."""
    _require_numpy()
    candidates = edge_matte_candidates(
        rgb,
        alpha,
        edge_bg_mask,
        bg_rgb,
        radius=radius,
        saturation_threshold=saturation_threshold,
        full_opacity_luma=full_opacity_luma,
        eligible_mask=eligible_mask,
    )
    if not candidates.any():
        return rgb.copy()

    rgb_f = rgb.astype(np.float32)
    luma = 0.2126 * rgb_f[:, :, 0] + 0.7152 * rgb_f[:, :, 1] + 0.0722 * rgb_f[:, :, 2]
    bg_luma = float(0.2126 * bg_rgb[0] + 0.7152 * bg_rgb[1] + 0.0722 * bg_rgb[2])
    a = np.maximum(alpha.astype(np.float32) / 255.0, 1e-3)
    foreground_luma = (luma - (1.0 - a) * bg_luma) / a
    foreground_luma = np.clip(np.rint(foreground_luma), 0, 255).astype(np.uint8)

    out = rgb.copy()
    for channel in range(3):
        out[:, :, channel][candidates] = foreground_luma[candidates]
    return out


def decontaminate_edges(
    rgb: "np.ndarray",
    alpha: "np.ndarray",
    bg_rgb: tuple[int, int, int],
    eligible_mask: "np.ndarray | None" = None,
) -> "np.ndarray":
    """Remove background color contamination from semi-transparent edge pixels."""
    _require_numpy()
    edge = (alpha > 0) & (alpha < 255)
    if eligible_mask is not None:
        edge &= eligible_mask.astype(bool)
    if not edge.any():
        return rgb.copy()

    rgb_f = rgb.astype(np.float32)
    a = (alpha.astype(np.float32) / 255.0)[..., None]
    safe_a = np.maximum(a, 1e-3)
    bg = np.array(bg_rgb, dtype=np.float32)
    corrected = (rgb_f - (1.0 - safe_a) * bg) / safe_a

    out = rgb_f.copy()
    out[edge] = corrected[edge]
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def resize_rgba(
    rgba: Image.Image,
    target_width: int | None,
    target_long_edge: int | None,
    no_upscale: bool,
    force_resize: bool,
    max_output_pixels: int = DEFAULT_MAX_OUTPUT_PIXELS,
) -> Image.Image:
    """Resize RGBA while preserving aspect ratio."""
    output_limit = _positive_int(max_output_pixels, "--max-output-pixels")
    source_pixels = rgba.width * rgba.height
    if target_width is not None and target_long_edge is not None:
        raise ValueError("--target-width and --target-long-edge are mutually exclusive.")
    if no_upscale and force_resize:
        raise ValueError("--no-upscale and --force-resize cannot be used together.")
    if force_resize and target_width is None and target_long_edge is None:
        raise ValueError("--force-resize requires --target-width or --target-long-edge.")
    if target_width is None and target_long_edge is None:
        if source_pixels > output_limit:
            raise ValueError(
                f"Output would retain {source_pixels:,} pixels, exceeding --max-output-pixels "
                f"({output_limit:,})."
            )
        return rgba

    w, h = rgba.size
    if target_width is not None:
        target = _positive_int(target_width, "--target-width")
        source = w
    else:
        target = _positive_int(target_long_edge, "--target-long-edge")
        source = max(w, h)

    should_resize = force_resize or (target > source and not no_upscale)
    if not should_resize:
        if source_pixels > output_limit:
            raise ValueError(
                f"Output would retain {source_pixels:,} pixels, exceeding --max-output-pixels "
                f"({output_limit:,})."
            )
        return rgba

    scale = target / float(source)
    new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
    return resize_rgba_premultiplied(
        rgba,
        new_size,
        max_output_pixels=output_limit,
    )


def resize_rgba_premultiplied(
    rgba: Image.Image,
    new_size: tuple[int, int],
    max_output_pixels: int = DEFAULT_MAX_OUTPUT_PIXELS,
) -> Image.Image:
    """Resize RGBA using premultiplied alpha to avoid light color bleed."""
    _require_numpy()
    output_limit = _positive_int(max_output_pixels, "--max-output-pixels")
    if len(new_size) != 2:
        raise ValueError("New image size must contain width and height.")
    width = _positive_int(new_size[0], "Output width")
    height = _positive_int(new_size[1], "Output height")
    output_pixels = width * height
    if output_pixels > output_limit:
        raise ValueError(
            f"Requested output has {output_pixels:,} pixels, exceeding --max-output-pixels "
            f"({output_limit:,})."
        )
    rgba = rgba.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.float32)
    alpha = arr[:, :, 3:4] / 255.0
    premultiplied = arr.copy()
    premultiplied[:, :, :3] *= alpha

    premultiplied_img = Image.fromarray(
        np.clip(np.rint(premultiplied), 0, 255).astype(np.uint8),
        mode="RGBA",
    )
    resized = np.asarray(
        premultiplied_img.resize((width, height), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )

    resized_alpha = resized[:, :, 3:4] / 255.0
    out = resized.copy()
    nonzero = resized_alpha[:, :, 0] > 1e-6
    out[:, :, :3][nonzero] = resized[:, :, :3][nonzero] / resized_alpha[nonzero]
    out[:, :, :3][~nonzero] = 0
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), mode="RGBA")


def enhance_rgba(
    rgba: Image.Image,
    mode: str,
    scale_factor: float,
) -> tuple[Image.Image, str]:
    """Sharpen only fully opaque foreground interiors while preserving alpha."""
    _require_numpy()
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in ENHANCEMENT_MODES:
        choices = ", ".join(sorted(ENHANCEMENT_MODES))
        raise ValueError(f"--enhance must be one of: {choices}.")
    if normalized_mode == "off":
        return rgba, "off"
    if normalized_mode == "auto" and scale_factor < 1.5:
        return rgba, "skipped"

    source = rgba.convert("RGBA")
    source_array = np.asarray(source, dtype=np.uint8)
    alpha = source_array[:, :, 3].copy()

    opaque = Image.fromarray(
        np.where(alpha == 255, 255, 0).astype(np.uint8),
        mode="L",
    )
    interior = np.asarray(opaque.filter(ImageFilter.MinFilter(3)), dtype=np.uint8) == 255
    sharpened = source.convert("RGB").filter(
        ImageFilter.UnsharpMask(radius=1.1, percent=180, threshold=1)
    )
    sharpened_rgb = np.asarray(sharpened, dtype=np.uint8)

    output = source_array.copy()
    output[:, :, :3][interior] = sharpened_rgb[interior]
    output[:, :, :3][alpha == 0] = 0
    output[:, :, 3] = alpha
    return Image.fromarray(output, mode="RGBA"), "applied"


def save_image_atomic(
    image: Image.Image,
    output_path: str | Path,
    output_format: str,
    matte: tuple[int, int, int] | None = None,
) -> None:
    """Write a supported image format through an atomic same-directory replacement."""
    normalized_format = normalize_output_format(output_format)
    save_image = image
    save_options: dict[str, object]
    if normalized_format == "png":
        save_options = {"format": "PNG", "compress_level": 6}
    elif normalized_format == "webp":
        save_image = image.convert("RGBA")
        save_options = {
            "format": "WEBP",
            "lossless": True,
            "quality": 100,
            "method": 6,
            "exact": True,
        }
    elif normalized_format == "tiff":
        save_image = image.convert("RGBA")
        save_options = {"format": "TIFF", "compression": "tiff_lzw"}
    else:
        if matte is None:
            raise ValueError(
                "JPEG cannot preserve transparency; provide --matte or use .png "
                "for transparent output."
            )
        rgba = image.convert("RGBA")
        base = Image.new("RGBA", rgba.size, (*matte, 255))
        base.alpha_composite(rgba)
        composite = base.convert("RGB")
        alpha = rgba.getchannel("A")
        edge_band = ImageChops.difference(
            alpha.filter(ImageFilter.MaxFilter(5)),
            alpha.filter(ImageFilter.MinFilter(5)),
        )
        softened_edge = composite.filter(ImageFilter.GaussianBlur(0.5))
        save_image = Image.composite(softened_edge, composite, edge_band)
        save_options = {
            "format": "JPEG",
            "quality": 95,
            "subsampling": 0,
            "optimize": True,
        }

    destination = Path(output_path)
    if destination.is_symlink():
        raise ValueError(f"Refusing to overwrite symbolic-link output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=destination.suffix or ".png",
        dir=destination.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            save_image.save(handle, **save_options)
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def save_png_atomic(image: Image.Image, output_path: str | Path, compress_level: int = 6) -> None:
    """Write a PNG through a same-directory temporary file and atomic replacement."""
    if compress_level != 6:
        destination = Path(output_path)
        if destination.is_symlink():
            raise ValueError(f"Refusing to overwrite symbolic-link output: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}.",
            suffix=destination.suffix or ".png",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                image.save(handle, format="PNG", compress_level=compress_level)
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return
    save_image_atomic(image, output_path, "png")


def save_checker_preview(rgba: Image.Image, output_path: str | Path, square_size: int = 32) -> None:
    """Composite transparent PNG over a checkerboard and save preview."""
    _require_numpy()
    if square_size <= 0:
        raise ValueError("Checker square size must be positive.")
    w, h = rgba.size
    x_pattern = (np.arange(w, dtype=np.int32) // square_size) % 2
    y_pattern = (np.arange(h, dtype=np.int32) // square_size) % 2
    pattern = x_pattern[None, :] ^ y_pattern[:, None]
    checker = np.where(pattern == 0, 240, 190).astype(np.uint8)
    base = Image.fromarray(checker, mode="L").convert("RGBA")
    base.alpha_composite(rgba.convert("RGBA"))
    save_png_atomic(base.convert("RGB"), output_path)


def save_solid_preview(
    rgba: Image.Image,
    output_path: str | Path,
    color: tuple[int, int, int] = (31, 37, 48),
) -> None:
    """Composite transparent PNG over a solid RGB background and save preview."""
    base = Image.new("RGBA", rgba.size, (*color, 255))
    base.alpha_composite(rgba.convert("RGBA"))
    save_png_atomic(base.convert("RGB"), output_path)


def alpha_statistics(alpha: Image.Image | "np.ndarray") -> tuple[float, float]:
    """Return transparent and opaque pixel fractions."""
    _require_numpy()
    values = np.asarray(alpha, dtype=np.uint8)
    total = max(1, values.size)
    transparent = float(np.count_nonzero(values == 0)) / total
    opaque = float(np.count_nonzero(values == 255)) / total
    return transparent, opaque


def quality_warnings(transparent_fraction: float, opaque_fraction: float) -> tuple[str, ...]:
    """Return conservative warnings for likely ineffective or empty outputs."""
    warnings: list[str] = []
    if transparent_fraction < 0.001:
        warnings.append("Less than 0.1% of the output is transparent; background removal may have missed.")
    if opaque_fraction < 0.001:
        warnings.append("Less than 0.1% of the output is fully opaque; foreground may have been over-removed.")
    return tuple(warnings)


def parse_background(value: str, rgba_array: "np.ndarray") -> tuple[int, int, int]:
    value = value.strip().lower()
    if value == "auto":
        return estimate_background_rgb(rgba_array)
    if value == "white":
        return (255, 255, 255)

    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise ValueError("--bg must be auto, white, or R,G,B.")
    channels = tuple(int(part) for part in parts)
    if any(channel < 0 or channel > 255 for channel in channels):
        raise ValueError("--bg RGB channels must be between 0 and 255.")
    return channels


def normalize_output_format(value: str) -> str:
    """Return a canonical output format name."""
    normalized = str(value).strip().lower()
    aliases = {"jpg": "jpeg", "tif": "tiff"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in OUTPUT_FORMATS:
        choices = ", ".join(sorted(OUTPUT_FORMATS))
        raise ValueError(
            f"Unsupported output format: {value}. Supported formats: {choices}."
        )
    return normalized


def resolve_output_path(
    path: str | Path,
    output_format: str | None = None,
) -> tuple[Path, str]:
    """Resolve a destination extension and reject format/extension conflicts."""
    output_path = Path(path)
    explicit_format = (
        normalize_output_format(output_format) if output_format is not None else None
    )
    suffix_format = None
    if output_path.suffix:
        suffix_format = EXTENSION_FORMATS.get(output_path.suffix.lower())
        if suffix_format is None:
            raise ValueError(
                f"Unsupported output format for extension: {output_path.suffix}."
            )
    if (
        explicit_format is not None
        and suffix_format is not None
        and explicit_format != suffix_format
    ):
        raise ValueError(
            f"Output format conflict: --format {explicit_format} does not match "
            f"the {output_path.suffix} extension."
        )

    resolved_format = explicit_format or suffix_format or "png"
    if not output_path.suffix:
        output_path = output_path.with_suffix(OUTPUT_EXTENSIONS[resolved_format])
    return output_path, resolved_format


def parse_matte(value: str) -> tuple[int, int, int]:
    """Parse a JPEG matte as white, black, or R,G,B."""
    normalized = str(value).strip().lower()
    if normalized == "white":
        return (255, 255, 255)
    if normalized == "black":
        return (0, 0, 0)
    parts = [part.strip() for part in normalized.split(",")]
    if len(parts) != 3:
        raise ValueError("--matte must be white, black, or R,G,B.")
    try:
        channels = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("--matte must be white, black, or R,G,B.") from exc
    if any(channel < 0 or channel > 255 for channel in channels):
        raise ValueError("--matte RGB channels must be between 0 and 255.")
    return channels


def normalize_output_path(path: str | Path) -> Path:
    """Return an output path with an unambiguous PNG extension."""
    output_path = Path(path)
    if not output_path.suffix:
        return output_path.with_suffix(".png")
    if output_path.suffix.lower() != ".png":
        raise ValueError("Output path must use a .png extension.")
    return output_path


def validate_parameters(
    *,
    bg_distance: float,
    brightness_threshold: int,
    saturation_threshold: int,
    feather: float,
    protect_dark: int,
    protect_saturation: int,
    protect_contrast: float,
    content_distance: float,
    edge_matte_strength: float,
    edge_matte_radius: int,
    edge_matte_saturation: int,
    edge_matte_full_opacity_luma: int,
    background_scope: str,
    max_input_pixels: int,
    max_output_pixels: int,
) -> None:
    """Validate public processing parameters before allocating large arrays."""
    finite_values = (
        ("--bg-distance", bg_distance),
        ("--feather", feather),
        ("--protect-contrast", protect_contrast),
        ("--content-distance", content_distance),
        ("--edge-matte-strength", edge_matte_strength),
    )
    for name, value in finite_values:
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a finite number.") from exc
        if not math.isfinite(numeric):
            raise ValueError(f"{name} must be a finite number.")
    if bg_distance < 0:
        raise ValueError("--bg-distance must be non-negative.")
    if feather < 0:
        raise ValueError("--feather must be non-negative.")
    if content_distance < 0 or protect_contrast < 0:
        raise ValueError("Content and protection distances must be non-negative.")
    for name, value in (
        ("--brightness-threshold", brightness_threshold),
        ("--saturation-threshold", saturation_threshold),
        ("--protect-dark", protect_dark),
        ("--protect-saturation", protect_saturation),
        ("--edge-matte-saturation", edge_matte_saturation),
        ("--edge-matte-full-opacity-luma", edge_matte_full_opacity_luma),
    ):
        if not 0 <= int(value) <= 255:
            raise ValueError(f"{name} must be between 0 and 255.")
    if not 0 <= edge_matte_strength <= 1:
        raise ValueError("--edge-matte-strength must be between 0 and 1.")
    if not 0 <= edge_matte_radius <= 64:
        raise ValueError("--edge-matte-radius must be between 0 and 64.")
    if background_scope not in BACKGROUND_SCOPES:
        choices = ", ".join(sorted(BACKGROUND_SCOPES))
        raise ValueError(f"--background-scope must be one of: {choices}.")
    _positive_int(max_input_pixels, "--max-input-pixels")
    _positive_int(max_output_pixels, "--max-output-pixels")


def default_output_path(
    input_path: str | Path,
    target_width: int | None,
    target_long_edge: int | None,
    no_upscale: bool,
    output_format: str = "png",
) -> Path:
    input_path = Path(input_path)
    normalized_format = normalize_output_format(output_format)
    suffix = "_transparent"
    target = target_width if target_width is not None else target_long_edge
    if not no_upscale and target is not None:
        suffix += "_4k" if int(target) == 3840 else f"_{int(target)}px"
    return input_path.with_name(
        f"{input_path.stem}{suffix}{OUTPUT_EXTENSIONS[normalized_format]}"
    )


def unique_path(path: str | Path, overwrite: bool = False) -> Path:
    candidate = Path(path)
    if overwrite:
        if candidate.is_symlink():
            raise ValueError(f"Refusing to overwrite symbolic-link output: {candidate}")
        return candidate
    if not candidate.exists() and not candidate.is_symlink():
        return candidate
    for index in range(1, 1000):
        numbered = candidate.with_name(f"{candidate.stem}_{index}{candidate.suffix}")
        if not numbered.exists() and not numbered.is_symlink():
            return numbered
    raise FileExistsError(f"Could not find available output path for {candidate}")


def process_image(
    input_path: str | Path,
    output: str | Path | None = None,
    target_width: int | None = None,
    target_long_edge: int | None = None,
    no_upscale: bool = False,
    force_resize: bool = False,
    max_input_pixels: int = DEFAULT_MAX_INPUT_PIXELS,
    max_output_pixels: int = DEFAULT_MAX_OUTPUT_PIXELS,
    bg: str = "auto",
    bg_distance: float = 32,
    brightness_threshold: int = 180,
    saturation_threshold: int = 45,
    feather: float = 1.2,
    decontaminate: bool = True,
    preview: bool = False,
    preview_dark: bool = False,
    mask_debug: bool = False,
    overwrite: bool = False,
    protect_dark: int = 230,
    protect_saturation: int = 35,
    protect_contrast: float = 24,
    content_distance: int = 45,
    background_scope: str = "edge",
    edge_matte_strength: float = 0.0,
    edge_matte_radius: int = 2,
    edge_matte_saturation: int = 30,
    edge_matte_full_opacity_luma: int = 80,
    edge_matte_neutralize: bool = False,
    output_format: str | None = None,
    matte: str | None = None,
    enhance: str = "off",
) -> ProcessResult:
    """Remove a plain background, optionally enhance it, and save an image."""
    _require_numpy()
    validate_parameters(
        bg_distance=bg_distance,
        brightness_threshold=brightness_threshold,
        saturation_threshold=saturation_threshold,
        feather=feather,
        protect_dark=protect_dark,
        protect_saturation=protect_saturation,
        protect_contrast=protect_contrast,
        content_distance=content_distance,
        edge_matte_strength=edge_matte_strength,
        edge_matte_radius=edge_matte_radius,
        edge_matte_saturation=edge_matte_saturation,
        edge_matte_full_opacity_luma=edge_matte_full_opacity_luma,
        background_scope=background_scope,
        max_input_pixels=max_input_pixels,
        max_output_pixels=max_output_pixels,
    )
    enhancement_mode = str(enhance).strip().lower()
    if enhancement_mode not in ENHANCEMENT_MODES:
        choices = ", ".join(sorted(ENHANCEMENT_MODES))
        raise ValueError(f"--enhance must be one of: {choices}.")

    if output is not None:
        requested_output, resolved_format = resolve_output_path(output, output_format)
    else:
        requested_output = None
        resolved_format = (
            normalize_output_format(output_format) if output_format is not None else "png"
        )
    jpeg_matte = None
    if resolved_format == "jpeg":
        if matte is None:
            raise ValueError(
                "JPEG cannot preserve transparency; provide --matte or use .png "
                "for transparent output."
            )
        jpeg_matte = parse_matte(matte)
    elif matte is not None:
        raise ValueError("--matte is only valid when the output format is JPEG.")

    image = load_image(input_path, max_input_pixels=max_input_pixels)
    rgba = np.asarray(image, dtype=np.uint8)
    rgb = rgba[:, :, :3]
    original_alpha = rgba[:, :, 3]

    process_warnings: list[str] = []
    if bg.strip().lower() == "auto":
        background_estimate = estimate_background(rgba)
        bg_rgb = background_estimate.rgb
        if background_estimate.reliable:
            background_status = "auto"
            candidate_bg = build_candidate_background_mask(
                rgb,
                bg_rgb=bg_rgb,
                bg_distance=bg_distance,
                brightness_threshold=brightness_threshold,
                saturation_threshold=saturation_threshold,
            )
        else:
            background_status = "auto-skipped"
            candidate_bg = np.zeros(original_alpha.shape, dtype=bool)
            process_warnings.append(
                "Auto background detection was skipped because the border is not reliably opaque and light. "
                "Use --bg white or --bg R,G,B to force removal."
            )
    else:
        background_status = "explicit"
        bg_rgb = parse_background(bg, rgba)
        candidate_bg = build_candidate_background_mask(
            rgb,
            bg_rgb=bg_rgb,
            bg_distance=bg_distance,
            brightness_threshold=brightness_threshold,
            saturation_threshold=saturation_threshold,
        )
    # Do not use pre-existing transparency as a bridge to erase opaque foreground pixels.
    candidate_bg &= original_alpha == 255
    edge_bg = keep_edge_connected_background(candidate_bg)
    removal_bg = candidate_bg if background_scope == "all" else edge_bg
    alpha = build_alpha_mask(
        rgb,
        removal_bg,
        bg_rgb,
        feather=feather,
        original_alpha=original_alpha,
        text_dark_threshold=protect_dark,
        color_content_threshold=protect_saturation,
        content_distance_threshold=content_distance,
        dark_content_distance_threshold=protect_contrast,
    )
    opaque_input = original_alpha == 255
    alpha = apply_edge_matte_alpha(
        rgb,
        alpha,
        removal_bg,
        bg_rgb,
        strength=edge_matte_strength,
        radius=edge_matte_radius,
        saturation_threshold=edge_matte_saturation,
        full_opacity_luma=edge_matte_full_opacity_luma,
        eligible_mask=opaque_input,
    )
    removed_fraction = float(np.count_nonzero(alpha < original_alpha)) / max(1, alpha.size)
    removal_status = "removed" if removed_fraction > 0 else "unchanged"
    if removal_status == "unchanged" and np.any(opaque_input):
        process_warnings.append(
            "No opaque pixels were made transparent. The background may already be absent; "
            "otherwise retry with --bg white or --bg R,G,B."
        )
    matte_rgb = rgb
    if edge_matte_neutralize and edge_matte_strength > 0:
        matte_rgb = neutralize_edge_matte_rgb(
            rgb,
            alpha,
            removal_bg,
            bg_rgb,
            radius=edge_matte_radius,
            saturation_threshold=edge_matte_saturation,
            full_opacity_luma=edge_matte_full_opacity_luma,
            eligible_mask=opaque_input,
        )
    out_rgb = (
        decontaminate_edges(matte_rgb, alpha, bg_rgb, eligible_mask=opaque_input)
        if decontaminate
        else matte_rgb.copy()
    )
    out_arr = np.empty((*alpha.shape, 4), dtype=np.uint8)
    out_arr[:, :, :3] = out_rgb
    out_arr[:, :, 3] = alpha
    out_img = Image.fromarray(out_arr, mode="RGBA")
    source_width, source_height = out_img.size
    out_img = resize_rgba(
        out_img,
        target_width=target_width,
        target_long_edge=target_long_edge,
        no_upscale=no_upscale,
        force_resize=force_resize,
        max_output_pixels=max_output_pixels,
    )
    scale_factor = max(
        out_img.width / float(source_width),
        out_img.height / float(source_height),
    )
    if scale_factor > 4.0:
        process_warnings.append(
            f"Output is enlarged {scale_factor:.2f}x; enhancement cannot recover true detail."
        )
    out_img, enhancement_status = enhance_rgba(
        out_img,
        mode=enhancement_mode,
        scale_factor=scale_factor,
    )

    if requested_output is None:
        output_path = default_output_path(
            input_path,
            target_width,
            target_long_edge,
            no_upscale,
            output_format=resolved_format,
        )
    else:
        output_path = requested_output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path = unique_path(output_path, overwrite=overwrite)
    save_image_atomic(
        out_img,
        output_path,
        output_format=resolved_format,
        matte=jpeg_matte,
    )

    preview_path = None
    if preview:
        preview_path = unique_path(
            output_path.with_name(f"{output_path.stem}_preview_checker.png"),
            overwrite=overwrite,
        )
        save_checker_preview(out_img, preview_path)

    dark_preview_path = None
    if preview_dark:
        dark_preview_path = unique_path(
            output_path.with_name(f"{output_path.stem}_preview_dark.png"),
            overwrite=overwrite,
        )
        save_solid_preview(out_img, dark_preview_path)

    mask_path = None
    if mask_debug:
        resized_alpha = out_img.getchannel("A")
        mask_path = unique_path(
            output_path.with_name(f"{output_path.stem}_mask.png"),
            overwrite=overwrite,
        )
        save_png_atomic(resized_alpha, mask_path)

    transparent_fraction, opaque_fraction = alpha_statistics(out_img.getchannel("A"))
    warnings = tuple(process_warnings) + quality_warnings(transparent_fraction, opaque_fraction)

    return ProcessResult(
        output_path=output_path,
        preview_path=preview_path,
        dark_preview_path=dark_preview_path,
        mask_path=mask_path,
        bg_rgb=bg_rgb,
        background_status=background_status,
        size=out_img.size,
        removal_status=removal_status,
        removed_fraction=removed_fraction,
        transparent_fraction=transparent_fraction,
        opaque_fraction=opaque_fraction,
        output_format=resolved_format,
        enhancement_status=enhancement_status,
        scale_factor=scale_factor,
        warnings=warnings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove a plain light background and output a reusable image.",
        epilog=(
            "Default: keep the original pixel dimensions. Use --target-width 3840 only when a 4K "
            "output is explicitly wanted. PNG is the default; JPEG requires --matte."
        ),
    )
    parser.add_argument("input", help="Input image path.")
    parser.add_argument(
        "-o",
        "--output",
        help="Output path. Its extension can select PNG, WebP, TIFF, or JPEG.",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=sorted(OUTPUT_FORMATS),
        help="Output format. Defaults to the output extension, then PNG.",
    )
    parser.add_argument(
        "--matte",
        help="JPEG background: white, black, or R,G,B. Required for JPEG.",
    )
    parser.add_argument(
        "--enhance",
        choices=sorted(ENHANCEMENT_MODES),
        default="off",
        help="Conservative alpha-safe sharpening: off, auto, or light. Default: off.",
    )
    size_group = parser.add_mutually_exclusive_group()
    size_group.add_argument(
        "--target-width",
        type=int,
        help="Resize output to this width. Default: keep original dimensions.",
    )
    size_group.add_argument("--target-long-edge", type=int, help="Resize output to this long edge.")
    size_group.add_argument(
        "--keep-size",
        "--no-upscale",
        dest="no_upscale",
        action="store_true",
        help="Keep the original dimensions. This is already the default.",
    )
    parser.add_argument(
        "--force-resize",
        action="store_true",
        help="Resize even when it shrinks the image. Requires a target size.",
    )
    parser.add_argument(
        "--max-input-pixels",
        type=int,
        default=DEFAULT_MAX_INPUT_PIXELS,
        help=f"Reject inputs above this pixel count. Default: {DEFAULT_MAX_INPUT_PIXELS:,}.",
    )
    parser.add_argument(
        "--max-output-pixels",
        type=int,
        default=DEFAULT_MAX_OUTPUT_PIXELS,
        help=f"Reject requested output above this pixel count. Default: {DEFAULT_MAX_OUTPUT_PIXELS:,}.",
    )
    parser.add_argument("--bg", default="auto", help="Background: auto, white, or R,G,B. Default: auto.")
    parser.add_argument("--bg-distance", type=float, default=32, help="Background color distance threshold.")
    parser.add_argument("--brightness-threshold", type=int, default=180, help="Minimum brightness for background.")
    parser.add_argument("--saturation-threshold", type=int, default=45, help="Maximum saturation proxy for background.")
    parser.add_argument("--feather", type=float, default=1.2, help="Edge feather radius in pixels.")
    parser.add_argument(
        "--decontaminate",
        dest="decontaminate",
        action="store_true",
        default=True,
        help="Remove estimated background color from new semi-transparent edges. Default: enabled.",
    )
    parser.add_argument(
        "--no-decontaminate",
        dest="decontaminate",
        action="store_false",
        help="Keep original RGB values on new semi-transparent edges.",
    )
    parser.add_argument("--preview", action="store_true", help="Save a checkerboard preview.")
    parser.add_argument("--preview-dark", action="store_true", help="Save a dark-background halo preview.")
    parser.add_argument("--mask-debug", action="store_true", help="Save the alpha mask for debugging.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting output files.")
    parser.add_argument("--protect-dark", type=int, default=230, help="Protect pixels with max RGB at or below this value.")
    parser.add_argument("--protect-saturation", type=int, default=35, help="Protect pixels above this saturation proxy.")
    parser.add_argument(
        "--protect-contrast",
        type=float,
        default=24,
        help="Minimum RGB distance from the background before dark-pixel protection applies.",
    )
    parser.add_argument("--content-distance", type=int, default=45, help="Protect pixels this far from the background color.")
    parser.add_argument(
        "--background-scope",
        choices=sorted(BACKGROUND_SCOPES),
        default="edge",
        help="Remove only edge-connected background or all matching pixels. Default: edge.",
    )
    parser.add_argument(
        "--edge-matte-strength",
        type=float,
        default=0.0,
        help="Reduce light halos on neutral edge pixels. 0 disables; try 0.8-1.0 for dark slide backgrounds.",
    )
    parser.add_argument("--edge-matte-radius", type=int, default=2, help="Pixel radius around removed background for edge matte cleanup.")
    parser.add_argument("--edge-matte-saturation", type=int, default=30, help="Maximum saturation proxy for neutral edge matte cleanup.")
    parser.add_argument(
        "--edge-matte-full-opacity-luma",
        type=int,
        default=80,
        help="Neutral pixels at or below this luma remain fully opaque during edge matte cleanup.",
    )
    parser.add_argument(
        "--edge-matte-neutralize",
        action="store_true",
        help="Desaturate edge-matte pixels to suppress LCD subpixel red/blue fringes on dark backgrounds.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_upscale and args.force_resize:
        parser.error("--no-upscale and --force-resize cannot be used together.")
    if args.force_resize and args.target_width is None and args.target_long_edge is None:
        parser.error("--force-resize requires --target-width or --target-long-edge.")
    target_width = args.target_width
    try:
        result = process_image(
            input_path=args.input,
            output=args.output,
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
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"removal_status={result.removal_status}")
    print(f"removed_fraction={result.removed_fraction:.6f}")
    print(f"background_status={result.background_status}")
    print(f"output={result.output_path}")
    print(f"output_format={result.output_format}")
    print(f"enhancement_status={result.enhancement_status}")
    print(f"scale_factor={result.scale_factor:.6f}")
    print(f"size={result.size[0]}x{result.size[1]}")
    print(f"background_rgb={result.bg_rgb[0]},{result.bg_rgb[1]},{result.bg_rgb[2]}")
    print(f"transparent_fraction={result.transparent_fraction:.6f}")
    print(f"opaque_fraction={result.opaque_fraction:.6f}")
    if result.preview_path:
        print(f"preview={result.preview_path}")
    if result.dark_preview_path:
        print(f"dark_preview={result.dark_preview_path}")
    if result.mask_path:
        print(f"mask={result.mask_path}")
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
