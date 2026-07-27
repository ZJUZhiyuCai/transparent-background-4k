from __future__ import annotations

import os
import subprocess
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

from make_transparent_4k import (
    apply_edge_matte_alpha,
    build_alpha_mask,
    build_candidate_background_mask,
    default_output_path,
    estimate_background,
    estimate_background_rgb,
    keep_edge_connected_background,
    load_image,
    main,
    neutralize_edge_matte_rgb,
    process_image,
    resize_rgba,
    resize_rgba_premultiplied,
)


def alpha_for(image: Image.Image, feather: float = 0) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    bg = estimate_background_rgb(rgba)
    candidate = build_candidate_background_mask(
        rgba[:, :, :3],
        bg_rgb=bg,
        bg_distance=32,
        brightness_threshold=180,
        saturation_threshold=45,
    )
    edge = keep_edge_connected_background(candidate)
    return build_alpha_mask(rgba[:, :, :3], edge, bg, feather=feather, original_alpha=rgba[:, :, 3])


class TransparentBackgroundTests(unittest.TestCase):
    def create_symlink_or_skip(self, target: Path, link: Path) -> None:
        try:
            os.symlink(target, link)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"Symbolic links are unavailable in this environment: {exc}")

    def test_white_background_and_colored_rectangle(self) -> None:
        image = Image.new("RGBA", (32, 32), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 23, 23), fill=(255, 0, 0, 255))

        alpha = alpha_for(image)

        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertEqual(int(alpha[16, 16]), 255)

    def test_near_white_background_is_removed(self) -> None:
        image = Image.new("RGBA", (32, 32), (247, 247, 247, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((9, 9, 22, 22), fill=(0, 70, 200, 255))

        alpha = alpha_for(image)

        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertEqual(int(alpha[16, 16]), 255)

    def test_light_gray_background_is_removed_without_losing_dark_content(self) -> None:
        image = Image.new("RGBA", (32, 32), (205, 205, 205, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 23, 23), fill=(25, 25, 25, 255))

        alpha = alpha_for(image)

        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertEqual(int(alpha[16, 16]), 255)

    def test_multitone_light_border_remains_a_reliable_auto_background(self) -> None:
        values = np.array([220, 228, 236, 244, 252], dtype=np.uint8)
        indices = np.indices((40, 40)).sum(axis=0) % len(values)
        rgba = np.empty((40, 40, 4), dtype=np.uint8)
        rgba[:, :, :3] = values[indices][:, :, None]
        rgba[:, :, 3] = 255

        estimate = estimate_background(rgba)

        self.assertTrue(estimate.reliable)

    def test_foreground_heavy_border_is_not_a_reliable_auto_background(self) -> None:
        rgba = np.zeros((40, 40, 4), dtype=np.uint8)
        rgba[:, :, :3] = (30, 100, 200)
        rgba[:8, :, :3] = 255
        rgba[:, :, 3] = 255

        estimate = estimate_background(rgba)

        self.assertFalse(estimate.reliable)

    def test_internal_white_region_is_preserved(self) -> None:
        image = Image.new("RGBA", (36, 36), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 27, 27), outline=(0, 0, 0, 255), width=3)

        alpha = alpha_for(image)

        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertEqual(int(alpha[18, 18]), 255)

    def test_thin_black_line_is_opaque(self) -> None:
        image = Image.new("RGBA", (32, 32), "white")
        draw = ImageDraw.Draw(image)
        draw.line((2, 16, 29, 16), fill=(0, 0, 0, 255), width=1)

        alpha = alpha_for(image, feather=1.2)

        self.assertTrue(np.all(alpha[16, 2:30] == 255))

    def test_edge_matte_reduces_gray_antialias_halo(self) -> None:
        image = Image.new("RGBA", (9, 5), "white")
        pixels = image.load()
        for y in range(1, 4):
            pixels[3, y] = (210, 210, 210, 255)
            pixels[4, y] = (0, 0, 0, 255)
            pixels[5, y] = (210, 210, 210, 255)

        rgba = np.asarray(image, dtype=np.uint8)
        bg = estimate_background_rgb(rgba)
        candidate = build_candidate_background_mask(
            rgba[:, :, :3],
            bg_rgb=bg,
            bg_distance=32,
            brightness_threshold=215,
            saturation_threshold=45,
        )
        edge = keep_edge_connected_background(candidate)
        alpha = build_alpha_mask(rgba[:, :, :3], edge, bg, feather=0, original_alpha=rgba[:, :, 3])
        cleaned = apply_edge_matte_alpha(
            rgba[:, :, :3],
            alpha,
            edge,
            bg,
            strength=1.0,
            radius=1,
            saturation_threshold=30,
            full_opacity_luma=80,
        )

        self.assertEqual(int(alpha[2, 3]), 255)
        self.assertLess(int(cleaned[2, 3]), 80)
        self.assertEqual(int(cleaned[2, 4]), 255)

    def test_edge_matte_neutralizes_subpixel_color_fringe(self) -> None:
        image = Image.new("RGBA", (9, 5), "white")
        pixels = image.load()
        for y in range(1, 4):
            pixels[3, y] = (230, 210, 255, 255)
            pixels[4, y] = (0, 0, 0, 255)

        rgba = np.asarray(image, dtype=np.uint8)
        bg = estimate_background_rgb(rgba)
        candidate = build_candidate_background_mask(
            rgba[:, :, :3],
            bg_rgb=bg,
            bg_distance=32,
            brightness_threshold=215,
            saturation_threshold=45,
        )
        edge = keep_edge_connected_background(candidate)
        alpha = build_alpha_mask(rgba[:, :, :3], edge, bg, feather=0, original_alpha=rgba[:, :, 3])
        alpha = apply_edge_matte_alpha(
            rgba[:, :, :3],
            alpha,
            edge,
            bg,
            strength=1.0,
            radius=1,
            saturation_threshold=255,
            full_opacity_luma=80,
        )
        neutralized = neutralize_edge_matte_rgb(
            rgba[:, :, :3],
            alpha,
            edge,
            bg,
            radius=1,
            saturation_threshold=255,
            full_opacity_luma=80,
        )

        self.assertLess(int(alpha[2, 3]), 80)
        self.assertEqual(tuple(int(v) for v in neutralized[2, 3]), (0, 0, 0))

    def test_existing_transparency_is_preserved(self) -> None:
        image = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 23, 23), fill=(0, 120, 0, 255))

        alpha = alpha_for(image)

        self.assertEqual(int(alpha[0, 0]), 0)
        self.assertEqual(int(alpha[16, 16]), 255)

    def test_existing_semitransparent_rgb_is_not_decontaminated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "source.png"
            out = tmp_path / "out.png"
            image = Image.new("RGBA", (16, 16), (255, 255, 255, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((4, 4, 11, 11), fill=(100, 100, 100, 128))
            image.save(src)

            process_image(
                src,
                output=out,
                target_width=None,
                no_upscale=True,
                feather=0,
            )

            saved = np.asarray(load_image(out), dtype=np.uint8)
            self.assertEqual(tuple(int(v) for v in saved[8, 8, :3]), (100, 100, 100))
            self.assertEqual(int(saved[8, 8, 3]), 128)

    def test_auto_mode_preserves_opaque_white_content_on_transparent_border(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "transparent_logo.png"
            out = tmp_path / "out.png"
            image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((0, 4, 14, 27), fill=(255, 255, 255, 255))
            image.save(src)

            result = process_image(
                src,
                output=out,
                target_width=None,
                no_upscale=True,
                feather=0,
            )

            saved = np.asarray(load_image(out), dtype=np.uint8)
            self.assertEqual(int(saved[10, 4, 3]), 255)
            self.assertTrue(any("Auto background detection was skipped" in warning for warning in result.warnings))

    def test_explicit_background_can_remove_transparent_canvas_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "transparent_logo.png"
            out = tmp_path / "out.png"
            image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((0, 4, 14, 27), fill=(255, 255, 255, 255))
            image.save(src)

            process_image(
                src,
                output=out,
                target_width=None,
                no_upscale=True,
                feather=0,
                bg="white",
            )

            saved = np.asarray(load_image(out), dtype=np.uint8)
            self.assertEqual(int(saved[10, 4, 3]), 0)

    def test_background_scope_all_removes_enclosed_matching_regions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "ring.png"
            edge_out = tmp_path / "edge.png"
            all_out = tmp_path / "all.png"
            image = Image.new("RGBA", (36, 36), "white")
            ImageDraw.Draw(image).rectangle((8, 8, 27, 27), outline=(0, 0, 0, 255), width=3)
            image.save(src)

            process_image(
                src,
                output=edge_out,
                target_width=None,
                no_upscale=True,
                feather=0,
                background_scope="edge",
            )
            process_image(
                src,
                output=all_out,
                target_width=None,
                no_upscale=True,
                feather=0,
                background_scope="all",
            )

            edge_alpha = np.asarray(load_image(edge_out).getchannel("A"), dtype=np.uint8)
            all_alpha = np.asarray(load_image(all_out).getchannel("A"), dtype=np.uint8)
            self.assertEqual(int(edge_alpha[18, 18]), 255)
            self.assertEqual(int(all_alpha[18, 18]), 0)

    def test_resize_to_4k_width_and_no_upscale(self) -> None:
        image = Image.new("RGBA", (12, 6), (255, 0, 0, 255))

        resized = resize_rgba(
            image,
            target_width=3840,
            target_long_edge=None,
            no_upscale=False,
            force_resize=False,
        )
        kept = resize_rgba(
            image,
            target_width=3840,
            target_long_edge=None,
            no_upscale=True,
            force_resize=False,
        )

        self.assertEqual(resized.size, (3840, 1920))
        self.assertEqual(kept.size, (12, 6))

    def test_premultiplied_resize_avoids_transparent_white_bleed(self) -> None:
        image = Image.new("RGBA", (3, 1), (255, 255, 255, 0))
        pixels = image.load()
        pixels[1, 0] = (0, 0, 0, 255)

        resized = resize_rgba_premultiplied(image, (9, 3))
        arr = np.asarray(resized, dtype=np.uint8)
        semi = (arr[:, :, 3] > 0) & (arr[:, :, 3] < 255)

        self.assertTrue(semi.any())
        self.assertEqual(int(arr[:, :, :3][semi].max()), 0)

    def test_output_pixel_limit_rejects_unbounded_resize_before_allocation(self) -> None:
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 255))

        with self.assertRaisesRegex(ValueError, "max-output-pixels"):
            resize_rgba(
                image,
                target_width=10_000,
                target_long_edge=None,
                no_upscale=False,
                force_resize=False,
                max_output_pixels=1_000,
            )

    def test_output_pixel_limit_also_applies_when_resize_is_skipped(self) -> None:
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 255))

        with self.assertRaisesRegex(ValueError, "Output would retain"):
            resize_rgba(
                image,
                target_width=100,
                target_long_edge=None,
                no_upscale=True,
                force_resize=False,
                max_output_pixels=99,
            )

    def test_force_resize_requires_a_target_size(self) -> None:
        image = Image.new("RGBA", (10, 10), (0, 0, 0, 255))

        with self.assertRaisesRegex(ValueError, "requires"):
            resize_rgba(
                image,
                target_width=None,
                target_long_edge=None,
                no_upscale=False,
                force_resize=True,
            )

    def test_process_image_outputs_png_preview_and_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "figure.jpg"
            out = tmp_path / "figure_transparent.png"
            image = Image.new("RGB", (40, 20), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 5, 29, 14), fill=(0, 0, 255))
            image.save(src)

            result = process_image(src, output=out, target_width=80, preview=True)

            self.assertTrue(result.output_path.exists())
            self.assertTrue(result.preview_path and result.preview_path.exists())
            saved = load_image(result.output_path)
            self.assertEqual(saved.mode, "RGBA")
            self.assertEqual(saved.size[0], 80)
            self.assertLess(saved.getchannel("A").getextrema()[0], 10)

    def test_process_image_defaults_to_original_size_and_plain_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "figure.png"
            image = Image.new("RGB", (40, 20), "white")
            ImageDraw.Draw(image).rectangle((10, 5, 29, 14), fill=(0, 90, 220))
            image.save(src)

            result = process_image(src, feather=0)

            self.assertEqual(result.output_path.name, "figure_transparent.png")
            self.assertEqual(result.size, (40, 20))
            self.assertEqual(result.removal_status, "removed")
            self.assertGreater(result.removed_fraction, 0.4)

    def test_unchanged_auto_result_has_explicit_status_and_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "blue.png"
            out = tmp_path / "blue_transparent.png"
            Image.new("RGB", (20, 20), (30, 100, 200)).save(src)

            result = process_image(src, output=out, feather=0)

            self.assertEqual(result.background_status, "auto-skipped")
            self.assertEqual(result.removal_status, "unchanged")
            self.assertEqual(result.removed_fraction, 0.0)
            self.assertTrue(any("No opaque pixels" in warning for warning in result.warnings))

    def test_process_image_outputs_dark_preview_and_quality_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "figure.png"
            out = tmp_path / "figure_transparent.png"
            image = Image.new("RGB", (40, 20), "white")
            ImageDraw.Draw(image).rectangle((10, 5, 29, 14), fill=(0, 90, 220))
            image.save(src)

            result = process_image(
                src,
                output=out,
                target_width=None,
                no_upscale=True,
                preview_dark=True,
            )

            self.assertTrue(result.dark_preview_path and result.dark_preview_path.exists())
            self.assertGreater(result.transparent_fraction, 0.4)
            self.assertGreater(result.opaque_fraction, 0.1)

    def test_non_png_output_extension_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "figure.png"
            Image.new("RGB", (8, 8), "white").save(src)

            with self.assertRaisesRegex(ValueError, "\\.png"):
                process_image(src, output=tmp_path / "wrong.jpg", no_upscale=True)

    def test_non_finite_parameters_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "figure.png"
            Image.new("RGB", (8, 8), "white").save(src)

            with self.assertRaisesRegex(ValueError, "finite"):
                process_image(src, output=tmp_path / "nan.png", no_upscale=True, bg_distance=float("nan"))
            with self.assertRaisesRegex(ValueError, "finite"):
                process_image(src, output=tmp_path / "infinite.png", no_upscale=True, feather=float("inf"))

    def test_input_pixel_limit_is_enforced_before_decoding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "figure.png"
            Image.new("RGB", (8, 8), "white").save(src)

            with self.assertRaisesRegex(ValueError, "max-input-pixels"):
                load_image(src, max_input_pixels=63)

    def test_output_symlink_is_rejected_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "source.png"
            target = tmp_path / "target.png"
            output_link = tmp_path / "output.png"
            Image.new("RGB", (8, 8), "white").save(src)
            target.write_bytes(b"sentinel")
            self.create_symlink_or_skip(target, output_link)

            with self.assertRaisesRegex(ValueError, "symbolic-link"):
                process_image(
                    src,
                    output=output_link,
                    target_width=None,
                    no_upscale=True,
                    overwrite=True,
                )

            self.assertEqual(target.read_bytes(), b"sentinel")

    def test_custom_target_uses_an_honest_default_filename(self) -> None:
        path = default_output_path("figure.png", target_width=800, target_long_edge=None, no_upscale=False)

        self.assertEqual(path.name, "figure_transparent_800px.png")

    def test_invalid_input_path_has_readable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.png"
            with self.assertRaises(FileNotFoundError):
                load_image(missing)

    def test_cli_subprocess_handles_spaces_and_unicode_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "path with spaces \u517c\u5bb9"
            root.mkdir()
            src = root / "input image \u56fe.png"
            out = root / "transparent output \u56fe.png"
            image = Image.new("RGB", (20, 10), "white")
            ImageDraw.Draw(image).rectangle((5, 2, 14, 7), fill=(0, 90, 220))
            image.save(src)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "make_transparent_4k.py"),
                    str(src),
                    "--output",
                    str(out),
                    "--preview",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode(errors="replace"),
            )
            self.assertTrue(out.exists())
            with Image.open(out) as saved:
                self.assertEqual(saved.size, (20, 10))

    def test_cli_target_long_edge_overrides_default_width(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "tall.png"
            out = tmp_path / "out.png"
            Image.new("RGBA", (20, 40), "white").save(src)

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = main([str(src), "--output", str(out), "--target-long-edge", "80"])

            self.assertEqual(exit_code, 0)
            with Image.open(out) as saved:
                self.assertEqual(saved.size, (40, 80))

    def test_cli_defaults_to_original_size_and_reports_removal_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "figure.png"
            out = tmp_path / "out.png"
            image = Image.new("RGB", (20, 10), "white")
            ImageDraw.Draw(image).rectangle((5, 2, 14, 7), fill=(0, 90, 220))
            image.save(src)

            stdout = StringIO()
            with redirect_stdout(stdout), redirect_stderr(StringIO()):
                exit_code = main([str(src), "--output", str(out), "--preview"])

            self.assertEqual(exit_code, 0)
            with Image.open(out) as saved:
                self.assertEqual(saved.size, (20, 10))
            self.assertIn("removal_status=removed", stdout.getvalue())
            self.assertIn("removed_fraction=", stdout.getvalue())

    def test_cli_force_resize_requires_target_size(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["input.png", "--force-resize"])

        self.assertEqual(raised.exception.code, 2)

    def test_cli_rejects_conflicting_size_targets(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["input.png", "--target-width", "80", "--target-long-edge", "80"])

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
