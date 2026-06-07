"""Tests for b-roll auto-description + the correctable manifest (vision mocked)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.workflows import podcast_broll as br
from app.agents.workflows.podcast_show_kit import build_broll_manifest


def _mk_png(path: Path, color=(10, 20, 30)):
    from PIL import Image
    Image.new("RGB", (64, 64), color).save(path)


FAKE_DESC = {"description": "A duct-cleaning shot", "tags": ["duct", "hvac"], "usage": "specific"}


class DescribeTests(unittest.TestCase):
    def test_describe_file_returns_auto_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "broll_01.png"
            _mk_png(f)
            with patch.object(br, "_vision_describe", return_value=FAKE_DESC):
                entry = br.describe_broll_file(f)
        self.assertEqual(entry["file"], "broll_01.png")
        self.assertEqual(entry["description"], "A duct-cleaning shot")
        self.assertEqual(entry["tags"], ["duct", "hvac"])
        self.assertEqual(entry["usage"], "specific")
        self.assertEqual(entry["source"], "auto")


class ManifestTests(unittest.TestCase):
    def _make_assets(self, tmp):
        d = Path(tmp)
        _mk_png(d / "broll_01.png")
        _mk_png(d / "broll_02.jpg")
        (d / "host.mp4").write_bytes(b"not-a-real-video")  # non-broll file, should be ignored
        return d

    def test_generate_writes_manifest_for_broll_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._make_assets(tmp)
            with patch.object(br, "_vision_describe", return_value=FAKE_DESC):
                entries = br.generate_broll_manifest(d)
            self.assertEqual([e["file"] for e in entries], ["broll_01.png", "broll_02.jpg"])
            self.assertTrue((d / "broll.json").is_file())

    def test_correction_is_preserved_across_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._make_assets(tmp)
            with patch.object(br, "_vision_describe", return_value=FAKE_DESC):
                br.generate_broll_manifest(d)
                # producer corrects one entry by chat
                br.correct_broll_entry(d, "broll_01.png", description="John Miles LinkedIn", usage="specific")
                # regenerate with a DIFFERENT vision result; corrected entry must not change
                with patch.object(br, "_vision_describe", return_value={"description": "WRONG", "tags": [], "usage": "generic"}):
                    entries = br.generate_broll_manifest(d, redescribe_auto=True)
            by_file = {e["file"]: e for e in entries}
            self.assertEqual(by_file["broll_01.png"]["description"], "John Miles LinkedIn")
            self.assertEqual(by_file["broll_01.png"]["source"], "corrected")
            self.assertEqual(by_file["broll_02.png" if False else "broll_02.jpg"]["description"], "WRONG")  # auto got redescribed

    def test_build_manifest_merges_descriptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self._make_assets(tmp)
            with patch.object(br, "_vision_describe", return_value=FAKE_DESC):
                br.generate_broll_manifest(d)
            manifest = build_broll_manifest(d)
        first = next(m for m in manifest if m["file_name"] == "broll_01.png")
        self.assertEqual(first["description"], "A duct-cleaning shot")
        self.assertEqual(first["usage"], "specific")
        # broll.json itself is not treated as a b-roll asset
        self.assertNotIn("broll.json", [m["file_name"] for m in manifest])


if __name__ == "__main__":
    unittest.main()
