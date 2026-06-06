"""Tests for the Podcast Parlay Execute adapter (app/services/podcast_render.py).

Guard tests run everywhere. The full smoke render needs the render toolchain
(ffmpeg + Pillow + the Show Kit template + the Windows fonts render_video.py uses),
so it skips where those aren't available.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.services import podcast_render as pr
from app.services.podcast_render import DEFAULT_TEMPLATE, render_project


def _render_deps_available() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    if not DEFAULT_TEMPLATE.is_file():
        return False
    if not Path(r"C:\Windows\Fonts\arialbd.ttf").is_file():  # render_video.py hard-codes this
        return False
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def _mk_video(path: Path, seconds: int = 1) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", str(path)],
        check=True, capture_output=True,
    )


def _mk_png(path: Path, color, size=(1920, 1080)) -> None:
    from PIL import Image
    Image.new("RGB", size, color).save(path)


SMOKE_PLAN = {
    "project": "smoke",
    "scenes": [
        {"enabled": True, "scene_id": "S001", "layout": "intro",
         "start": "00:00:00.000", "end": "00:00:01.000", "host_source": "intro.mp4"},
        {"enabled": True, "scene_id": "S002", "layout": "show_image",
         "start": "00:00:01.000", "end": "00:00:02.000", "host_source": "show_image.png"},
        {"enabled": True, "scene_id": "S003", "layout": "2cam",
         "start": "00:00:02.000", "end": "00:00:03.000",
         "host_source": "host.mp4", "guest_01_source": "guest_01.mp4",
         "top_row_text": "David Hart", "bottom_row_text": "Origin story"},
        {"enabled": True, "scene_id": "S004", "layout": "outro",
         "start": "00:00:03.000", "end": "00:00:04.000", "host_source": "show_image.png"},
    ],
    "graphics": [],
    "broll": [],
    "assets": [
        {"asset_key": "show_image_lower_third", "file_name": "lower_third.png"},
        {"asset_key": "logo_square", "file_name": "logo.png"},
        {"asset_key": "show_image", "file_name": "show_image.png"},
    ],
    "settings": [
        {"setting": "template_name", "value": "parlayvu_interview"},
        {"setting": "timeline_mode", "value": "full_rendered"},
    ],
}


class GuardTests(unittest.TestCase):
    """Run everywhere — no render toolchain needed."""

    def test_missing_plan_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "planning").mkdir()
            with self.assertRaises(FileNotFoundError):
                render_project(project_dir=tmp)

    def test_missing_template_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            planning = Path(tmp) / "planning"
            planning.mkdir()
            (planning / "video_plan.json").write_text("{}")
            with self.assertRaises(FileNotFoundError):
                render_project(project_dir=tmp, template=Path(tmp) / "nope.json")

    def test_render_episode_rejects_path_escape(self):
        with self.assertRaises(ValueError):
            pr.render_episode(client_id="../evil", slug="x")


@unittest.skipUnless(_render_deps_available(), "render toolchain (ffmpeg/Pillow/fonts/template) not available")
class SmokeRenderTests(unittest.TestCase):
    def test_video_plan_renders_to_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "ep"
            assets = proj / "assets"
            planning = proj / "planning"
            assets.mkdir(parents=True)
            planning.mkdir(parents=True)
            for v in ("intro.mp4", "host.mp4", "guest_01.mp4"):
                _mk_video(assets / v)
            _mk_png(assets / "show_image.png", (20, 30, 60))
            _mk_png(assets / "lower_third.png", (12, 12, 12), (1920, 320))
            _mk_png(assets / "logo.png", (200, 200, 200), (400, 400))
            (planning / "video_plan.json").write_text(json.dumps(SMOKE_PLAN))

            result = render_project(project_dir=proj)

            out = Path(result["no_subtitles"])
            self.assertEqual(result["status"], "rendered")
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 10_000)  # a real, non-empty mp4


if __name__ == "__main__":
    unittest.main()
