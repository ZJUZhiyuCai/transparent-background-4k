from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image, ImageDraw

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILL_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from batch_make_transparent_4k import image_files, main


class BatchTransparentBackgroundTests(unittest.TestCase):
    def create_symlink_or_skip(self, target: Path, link: Path) -> None:
        try:
            os.symlink(target, link)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"Symbolic links are unavailable in this environment: {exc}")

    def test_generated_artifacts_are_not_reprocessed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (
                "source.png",
                "source_transparent.png",
                "source_transparent_4k.png",
                "source_transparent_4k_1.png",
                "source_transparent_800px.png",
                "source_transparent_4k_preview_checker.png",
                "source_transparent_4k_preview_dark.png",
                "source_transparent_4k_mask.png",
                ".interrupted_write.png",
            ):
                Image.new("RGB", (8, 8), "white").save(root / name)

            found = image_files(root)

            self.assertEqual(found, [root / "source.png"])

    def test_partial_failure_returns_two_and_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            summary_path = root / "summaries" / "result.json"
            valid = Image.new("RGB", (20, 20), "white")
            ImageDraw.Draw(valid).rectangle((5, 5, 14, 14), fill=(0, 90, 220))
            valid.save(root / "valid.png")
            (root / "broken.png").write_bytes(b"not a png")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = main(
                    [
                        str(root),
                        "--output-dir",
                        str(output_dir),
                        "--no-upscale",
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            rows = json.loads(summary_path.read_text(encoding="utf-8"))
            statuses = {Path(row["input"]).name: row["status"] for row in rows}
            self.assertEqual(exit_code, 2)
            self.assertEqual(statuses, {"broken.png": "failed", "valid.png": "ok"})

    def test_duplicate_stems_receive_distinct_outputs_even_with_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            Image.new("RGB", (20, 20), "white").save(root / "same.jpg")
            Image.new("RGB", (20, 20), "white").save(root / "same.png")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = main(
                    [
                        str(root),
                        "--output-dir",
                        str(output_dir),
                        "--no-upscale",
                        "--overwrite",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["same_transparent.png", "same_transparent_png.png"],
            )

    def test_batch_defaults_to_original_size_and_records_removal_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "outputs"
            summary_path = root / "summary.json"
            source = root / "figure.png"
            image = Image.new("RGB", (20, 10), "white")
            ImageDraw.Draw(image).rectangle((5, 2, 14, 7), fill=(0, 90, 220))
            image.save(source)

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = main(
                    [
                        str(root),
                        "--output-dir",
                        str(output_dir),
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            rows = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            with Image.open(output_dir / "figure_transparent.png") as saved:
                self.assertEqual(saved.size, (20, 10))
            self.assertEqual(rows[0]["removal_status"], "removed")
            self.assertGreater(float(rows[0]["removed_fraction"]), 0.4)

    def test_summary_symlink_is_rejected_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            sentinel = root / "sentinel.json"
            summary_link = root / "summary.json"
            Image.new("RGB", (16, 16), "white").save(source)
            sentinel.write_bytes(b"sentinel")
            self.create_symlink_or_skip(sentinel, summary_link)

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = main([str(root), "--no-upscale", "--summary-json", str(summary_link)])

            self.assertEqual(exit_code, 1)
            self.assertEqual(sentinel.read_bytes(), b"sentinel")

    def test_batch_handles_spaces_and_unicode_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "input folder \u517c\u5bb9"
            output_dir = Path(tmp) / "output folder \u8f93\u51fa"
            summary_path = Path(tmp) / "summary folder \u6c47\u603b" / "result.json"
            root.mkdir()
            source = root / "source image \u56fe.png"
            image = Image.new("RGB", (20, 10), "white")
            ImageDraw.Draw(image).rectangle((5, 2, 14, 7), fill=(0, 90, 220))
            image.save(source)

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                exit_code = main(
                    [
                        str(root),
                        "--output-dir",
                        str(output_dir),
                        "--summary-json",
                        str(summary_path),
                    ]
                )

            rows = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(rows), 1)
            self.assertTrue((output_dir / "source image \u56fe_transparent.png").exists())


if __name__ == "__main__":
    unittest.main()
