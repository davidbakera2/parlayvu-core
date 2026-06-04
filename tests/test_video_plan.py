"""Tests for generate_video_plan — the transcript -> video_plan.json planner.

The LLM call is mocked; these lock in the deterministic assembly (role->source
mapping, layout/role reconciliation, b-roll fallback) and the end-to-end write +
state advance, none of which should depend on a live model.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import parlay_state as ps
from app.database import initialize_database
from app.tools import video_parlay_tools as v


def build_fake_scope(Session):
    def fake_scope():
        class Scope:
            def __enter__(self):
                self.session = Session()
                return self.session

            def __exit__(self, exc_type, exc, tb):
                if exc_type:
                    self.session.rollback()
                else:
                    self.session.commit()
                self.session.close()

        return Scope()

    return fake_scope


class CoerceRolesTests(unittest.TestCase):
    def test_1cam_keeps_only_primary(self):
        primary, active = v._coerce_roles("1cam", "host", ["host", "guest_01"])
        self.assertEqual(active, ["host"])
        self.assertEqual(primary, "host")

    def test_2cam_fills_to_two(self):
        primary, active = v._coerce_roles("2cam", "host", ["host"])
        self.assertEqual(len(active), 2)
        self.assertIn("host", active)

    def test_3cam_trims_to_three_keeping_primary(self):
        primary, active = v._coerce_roles("3cam", "guest_01", ["host", "guest_01", "guest_02"])
        self.assertEqual(len(active), 3)
        self.assertIn("guest_01", active)

    def test_primary_forced_into_active(self):
        primary, active = v._coerce_roles("2cam", "guest_02", ["host", "guest_01"])
        self.assertIn(primary, active)


class AssembleVideoPlanTests(unittest.TestCase):
    def setUp(self):
        self.assets = {
            "present": ["host.mp4", "guest_01.mp4", "guest_02.mp4", "intro.mp4",
                        "show_image.png", "logo_square.png", "music.wav", "ciri1.JPG"],
            "cameras": ["host.mp4", "guest_01.mp4", "guest_02.mp4"],
            "branding": {"intro.mp4": "intro", "show_image.png": "show_image",
                         "logo_square.png": "logo_square", "music.wav": "music"},
            "broll": ["ciri1.JPG"],
        }
        self.llm_out = {
            "speaker_map": {"David Baker": "host", "David Hart": "guest_01"},
            "scenes": [
                {"scene_id": "S001", "layout": "1cam", "start": "00:00:30.000", "end": "00:00:57.000",
                 "primary_camera": "host", "active_roles": ["host"], "top_row_text": "DAVID BAKER | HOST", "broll_id": ""},
                {"scene_id": "S002", "layout": "2cam", "start": "00:00:57.000", "end": "00:02:15.000",
                 "primary_camera": "guest_01", "active_roles": ["host", "guest_01"], "top_row_text": "DAVID HART | CEO", "broll_id": ""},
                {"scene_id": "S003", "layout": "2cam_broll", "start": "00:02:15.000", "end": "00:03:00.000",
                 "primary_camera": "guest_01", "active_roles": ["host", "guest_01"], "top_row_text": "DAVID HART | CEO", "broll_id": "ciri1"},
                {"scene_id": "S004", "layout": "3cam_broll", "start": "00:03:00.000", "end": "00:04:00.000",
                 "primary_camera": "host", "active_roles": ["host", "guest_01", "guest_02"], "top_row_text": "PANEL", "broll_id": "doesnotexist"},
            ],
        }
        self.plan = v._assemble_video_plan("Ep06", "EP06: TEST", self.llm_out, self.assets)

    def _scene(self, sid):
        return next(s for s in self.plan["scenes"] if s["scene_id"] == sid)

    def test_scene_count_and_caption(self):
        self.assertEqual(len(self.plan["scenes"]), 4)
        self.assertTrue(all(s["bottom_row_text"] == "EP06: TEST" for s in self.plan["scenes"]))

    def test_1cam_only_primary_source(self):
        s = self._scene("S001")
        self.assertEqual(s["host_source"], "host.mp4")
        self.assertEqual(s["guest_01_source"], "")
        self.assertEqual(s["guest_02_source"], "")

    def test_2cam_two_sources(self):
        s = self._scene("S002")
        self.assertEqual(s["host_source"], "host.mp4")
        self.assertEqual(s["guest_01_source"], "guest_01.mp4")
        self.assertEqual(s["guest_02_source"], "")

    def test_broll_resolves_file(self):
        s = self._scene("S003")
        self.assertEqual(s["broll_id"], "ciri1")
        self.assertEqual(s["broll_file"], "ciri1.JPG")

    def test_unknown_broll_falls_back_to_plain_layout(self):
        s = self._scene("S004")
        self.assertEqual(s["layout"], "3cam")  # _broll stripped
        self.assertEqual(s["broll_id"], "")
        self.assertEqual(s["broll_file"], "")

    def test_sections_present(self):
        self.assertEqual([b["broll_id"] for b in self.plan["broll"]], ["ciri1"])
        keys = {a["asset_key"] for a in self.plan["assets"]}
        self.assertIn("intro", keys)
        self.assertIn("music", keys)


class ClassifyAssetsTests(unittest.TestCase):
    """B-roll must be visual only — audio + background + branding excluded."""

    def test_excludes_audio_and_branding_from_broll(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "Ep"
            (proj / "assets").mkdir(parents=True)
            for name in ("host.mp4", "guest_01.mp4", "intro.mp4", "show_image.png",
                         "music.mp3", "music.wav", "background.mp4",
                         "ciri1.JPG", "duct1.jpg", "clip.mp4", "notes.txt"):
                (proj / "assets" / name).write_bytes(b"x")
            a = v._classify_assets(proj)
        self.assertEqual(a["cameras"], ["guest_01.mp4", "host.mp4"])
        # audio, background, branding, and non-visual files are NOT b-roll
        self.assertEqual(sorted(a["broll"]), ["ciri1.JPG", "clip.mp4", "duct1.jpg"])
        for bad in ("music.mp3", "music.wav", "background.mp4", "intro.mp4", "notes.txt"):
            self.assertNotIn(bad, a["broll"])


class GenerateVideoPlanTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        initialize_database(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        self.fake = build_fake_scope(self.Session)
        self._tmp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self._tmp.name) / "Ep06"
        (self.project_dir / "planning").mkdir(parents=True)
        (self.project_dir / "assets").mkdir(parents=True)
        (self.project_dir / "planning" / "transcript.txt").write_text(
            "David Baker (00:01)\nWelcome.\n\nDavid Hart (00:16)\nThanks.\n", encoding="utf-8")
        for name in ("host.mp4", "guest_01.mp4", "intro.mp4", "show_image.png", "music.wav"):
            (self.project_dir / "assets" / name).write_bytes(b"x")

    def tearDown(self):
        self._tmp.cleanup()

    def test_drafts_and_writes_plan(self):
        llm_out = {
            "speaker_map": {"David Baker": "host", "David Hart": "guest_01"},
            "scenes": [
                {"scene_id": "S001", "layout": "1cam", "start": "00:00:00.000", "end": "00:00:20.000",
                 "primary_camera": "host", "active_roles": ["host"], "top_row_text": "DAVID BAKER | HOST", "broll_id": ""},
                {"scene_id": "S002", "layout": "2cam", "start": "00:00:20.000", "end": "00:01:00.000",
                 "primary_camera": "guest_01", "active_roles": ["host", "guest_01"], "top_row_text": "DAVID HART | CEO", "broll_id": ""},
            ],
        }
        with patch("app.database.session_scope", self.fake), \
             patch.object(v, "_get_project_dir", return_value=self.project_dir), \
             patch.object(v, "_draft_scenes_with_llm", new=AsyncMock(return_value=llm_out)), \
             patch.object(v, "_refresh_state_mirror", return_value=None), \
             patch.object(v, "_safe_event", return_value=None):
            result = asyncio.run(v.generate_video_plan(
                client_id="ramair", episode_slug="Ep06", episode_caption="EP06: TEST"))

        self.assertEqual(result["status"], "planned")
        self.assertEqual(result["scene_count"], 2)
        plan_file = self.project_dir / "planning" / "video_plan.json"
        self.assertTrue(plan_file.is_file())
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        self.assertEqual(len(plan["scenes"]), 2)
        self.assertEqual(plan["scenes"][0]["host_source"], "host.mp4")
        # state advanced to planning
        with patch("app.database.session_scope", self.fake):
            state = ps.get_state(ps.parlay_project_id("ramair", "Ep06"))
        self.assertEqual(state["stage"], ps.PLANNING)

    def test_missing_transcript_errors(self):
        (self.project_dir / "planning" / "transcript.txt").unlink()
        with patch("app.database.session_scope", self.fake), \
             patch.object(v, "_get_project_dir", return_value=self.project_dir), \
             patch.object(v, "_draft_scenes_with_llm", new=AsyncMock()) as llm:
            result = asyncio.run(v.generate_video_plan(client_id="ramair", episode_slug="Ep06"))
        self.assertEqual(result["status"], "error")
        llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
