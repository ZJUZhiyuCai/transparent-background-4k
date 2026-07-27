from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILL_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import batch_make_transparent_4k as batch
import make_transparent_4k as single


def transparent_logo(path: Path, size: tuple[int, int] = (24, 16)) -> None:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((3, 3, size[0] - 4, size[1] - 4), fill=(20, 80, 180, 255))
    draw.line((5, size[1] // 2, size[0] - 6, size[1] // 2), fill=(0, 0, 0, 255), width=1)
    image.save(path)


def white_background_logo(path: Path, size: tuple[int, int] = (24, 16)) -> None:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((3, 3, size[0] - 4, size[1] - 4), fill=(20, 80, 180))
    draw.line((5, size[1] // 2, size[0] - 6, size[1] // 2), fill=(0, 0, 0), width=1)
    image.save(path)


def rgba_array(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"), dtype=np.uint8)


def sharpness_score(rgba: np.ndarray) -> float:
    rgb = rgba[:, :, :3].astype(np.float32)
    luma = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    alpha = rgba[:, :, 3] >= 250
    dx = np.abs(np.diff(luma, axis=1))
    dy = np.abs(np.diff(luma, axis=0))
    valid_x = alpha[:, 1:] & alpha[:, :-1]
    valid_y = alpha[1:, :] & alpha[:-1, :]
    values = np.concatenate([dx[valid_x], dy[valid_y]])
    return float(values.mean()) if values.size else 0.0


class EnhancementAndFormatTests(unittest.TestCase):
    def test_default_output_remains_png_with_enhancement_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source.png"
            transparent_logo(src)

            result = single.process_image(src, feather=0)

            self.assertEqual(result.output_path.suffix, ".png")
            self.assertEqual(result.output_format, "png")
            self.assertEqual(result.enhancement_status, "off")
            self.assertEqual(result.scale_factor, 1.0)

    def test_auto_enhancement_skips_below_one_point_five_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            transparent_logo(src, (20, 12))

            result = single.process_image(
                src,
                output=root / "out.png",
                target_width=29,
                enhance="auto",
                feather=0,
            )

            self.assertEqual(result.enhancement_status, "skipped")
            self.assertAlmostEqual(result.scale_factor, 29 / 20, places=6)

    def test_auto_enhancement_applies_at_one_point_five_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            transparent_logo(src, (20, 12))

            result = single.process_image(
                src,
                output=root / "out.png",
                target_width=30,
                enhance="auto",
                feather=0,
            )

            self.assertEqual(result.enhancement_status, "applied")
            self.assertAlmostEqual(result.scale_factor, 1.5, places=6)

    def test_light_enhancement_forces_without_resize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            transparent_logo(src)

            result = single.process_image(
                src,
                output=root / "out.png",
                enhance="light",
                feather=0,
            )

            self.assertEqual(result.enhancement_status, "applied")
            self.assertEqual(result.scale_factor, 1.0)

    def test_enhancement_preserves_alpha_byte_for_byte(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            off = root / "off.png"
            enhanced = root / "enhanced.png"
            transparent_logo(src)

            single.process_image(src, output=off, target_width=96, enhance="off", feather=0)
            single.process_image(src, output=enhanced, target_width=96, enhance="auto", feather=0)

            self.assertTrue(np.array_equal(rgba_array(off)[:, :, 3], rgba_array(enhanced)[:, :, 3]))

    def test_enhancement_does_not_pollute_fully_transparent_rgb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            out = root / "out.png"
            transparent_logo(src)

            single.process_image(src, output=out, target_width=96, enhance="auto", feather=0)

            rgba = rgba_array(out)
            self.assertTrue(np.all(rgba[:, :, :3][rgba[:, :, 3] == 0] == 0))

    def test_scale_above_four_warns_about_unrecoverable_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            transparent_logo(src, (20, 12))

            result = single.process_image(
                src,
                output=root / "out.png",
                target_width=101,
                enhance="auto",
                feather=0,
            )

            self.assertTrue(any("cannot recover true detail" in warning.lower() for warning in result.warnings))

    def test_auto_enhancement_improves_sharpness_by_five_percent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            off = root / "off.png"
            enhanced = root / "enhanced.png"
            transparent_logo(src, (32, 20))

            single.process_image(src, output=off, target_width=128, enhance="off", feather=0)
            single.process_image(src, output=enhanced, target_width=128, enhance="auto", feather=0)

            off_score = sharpness_score(rgba_array(off))
            enhanced_score = sharpness_score(rgba_array(enhanced))
            self.assertGreaterEqual(enhanced_score, off_score * 1.05)

    def test_webp_lossless_roundtrip_matches_png_rgba(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            png = root / "out.png"
            webp = root / "out.webp"
            transparent_logo(src)

            single.process_image(src, output=png, feather=0)
            result = single.process_image(src, output=webp, feather=0)

            self.assertEqual(result.output_format, "webp")
            self.assertTrue(np.array_equal(rgba_array(png), rgba_array(webp)))

    def test_tiff_lzw_roundtrip_matches_png_rgba(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            png = root / "out.png"
            tiff = root / "out.tiff"
            transparent_logo(src)

            single.process_image(src, output=png, feather=0)
            result = single.process_image(src, output=tiff, feather=0)

            self.assertEqual(result.output_format, "tiff")
            self.assertTrue(np.array_equal(rgba_array(png), rgba_array(tiff)))

    def test_jpeg_without_matte_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            transparent_logo(src)

            with self.assertRaisesRegex(ValueError, "matte"):
                single.process_image(src, output=root / "out.jpg", feather=0)

    def test_jpeg_with_matte_outputs_rgb(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            out = root / "out.jpg"
            transparent_logo(src)

            result = single.process_image(src, output=out, matte="10,20,30", feather=0)

            self.assertEqual(result.output_format, "jpeg")
            with Image.open(out) as image:
                self.assertEqual(image.mode, "RGB")
                corner = image.getpixel((0, 0))
            self.assertTrue(all(abs(actual - expected) <= 3 for actual, expected in zip(corner, (10, 20, 30))))

    def test_explicit_format_controls_automatic_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source.png"
            transparent_logo(src)

            result = single.process_image(src, output_format="webp", feather=0)

            self.assertEqual(result.output_path.suffix, ".webp")
            self.assertEqual(result.output_format, "webp")

    def test_format_and_output_suffix_conflict_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            transparent_logo(src)

            with self.assertRaisesRegex(ValueError, "conflict"):
                single.process_image(src, output=root / "out.png", output_format="webp", feather=0)

    def test_unsupported_output_format_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "source.png"
            transparent_logo(src)

            with self.assertRaisesRegex(ValueError, "Unsupported output format"):
                single.process_image(src, output_format="avif", feather=0)

    def test_webp_previews_and_mask_stay_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            transparent_logo(src)

            result = single.process_image(
                src,
                output=root / "out.webp",
                preview=True,
                preview_dark=True,
                mask_debug=True,
                feather=0,
            )

            for path in (result.preview_path, result.dark_preview_path, result.mask_path):
                self.assertIsNotNone(path)
                self.assertEqual(path.suffix, ".png")
                with Image.open(path) as image:
                    self.assertEqual(image.format, "PNG")

    def test_cli_reports_format_enhancement_and_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "source.png"
            out = root / "out.webp"
            transparent_logo(src, (20, 12))
            stdout = StringIO()

            with redirect_stdout(stdout), redirect_stderr(StringIO()):
                exit_code = single.main(
                    [
                        str(src),
                        "--output",
                        str(out),
                        "--target-width",
                        "40",
                        "--enhance",
                        "auto",
                    ]
                )

            self.assertEqual(exit_code, 0)
            report = stdout.getvalue()
            self.assertIn("output_format=webp", report)
            self.assertIn("enhancement_status=applied", report)
            self.assertIn("scale_factor=2.000000", report)

    def test_batch_format_and_enhancement_reach_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "inputs"
            output_dir = root / "outputs"
            summary = root / "summary.json"
            input_dir.mkdir()
            white_background_logo(input_dir / "figure.png")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = batch.main(
                    [
                        str(input_dir),
                        "--output-dir",
                        str(output_dir),
                        "--format",
                        "webp",
                        "--enhance",
                        "light",
                        "--summary-json",
                        str(summary),
                    ]
                )

            rows = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "figure_transparent.webp").exists())
            self.assertEqual(rows[0]["output_format"], "webp")
            self.assertEqual(rows[0]["enhancement_status"], "applied")
            self.assertEqual(rows[0]["scale_factor"], "1.000000")

    def test_batch_same_stem_outputs_remain_distinct_in_webp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "inputs"
            output_dir = root / "outputs"
            input_dir.mkdir()
            white_background_logo(input_dir / "same.jpg")
            white_background_logo(input_dir / "same.png")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = batch.main(
                    [
                        str(input_dir),
                        "--output-dir",
                        str(output_dir),
                        "--format",
                        "webp",
                        "--overwrite",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["same_transparent.webp", "same_transparent_png.webp"],
            )


if __name__ == "__main__":
    unittest.main()
