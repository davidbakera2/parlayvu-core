"""Unit tests for the Show Kit merge (app/agents/workflows/podcast_show_kit.py)."""

import unittest

from app.agents.workflows import podcast_show_kit as sk


class TimeHelperTests(unittest.TestCase):
    def test_to_seconds_roundtrip_and_negative(self):
        self.assertAlmostEqual(sk.to_seconds("00:01:30.500"), 90.5)
        self.assertAlmostEqual(sk.to_seconds("-00:00:10.000"), -10.0)
        self.assertAlmostEqual(sk.to_seconds("12.5"), 12.5)
        self.assertEqual(sk.to_seconds("", 7.0), 7.0)

    def test_hhmmss_format(self):
        self.assertEqual(sk.hhmmss(90.5), "00:01:30.500")
        self.assertEqual(sk.hhmmss(0), "00:00:00.000")


class LoadShowKitTests(unittest.TestCase):
    def test_loads_parlayvu_interview(self):
        kit = sk.load_show_kit("parlayvu_interview")
        self.assertIn("bookends", kit)
        self.assertTrue(any(s["setting"] == "background_video" for s in kit["settings"]))
        self.assertEqual([a["audio_id"] for a in kit["audio"]], ["intro_music", "outro_music"])

    def test_unknown_visual_system_raises(self):
        with self.assertRaises(FileNotFoundError):
            sk.load_show_kit("does-not-exist")


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.kit = sk.load_show_kit("parlayvu_interview")
        self.program = [
            {"layout": "3cam", "source_start": "00:00:00.000", "duration": "00:00:20.000",
             "top_row_text": "DAVID BAKER", "bottom_row_text": "WELCOME"},
            {"layout": "2cam_broll", "source_start": "00:00:40.000", "duration": "00:00:10.000",
             "top_row_text": "DAVID HART", "bottom_row_text": "THE REPORT", "broll_id": "b1"},
        ]

    def test_wraps_program_in_bookends_with_contiguous_timeline(self):
        # No assets_dir -> intro uses default_duration (00:00:15).
        plan = sk.merge_with_show_kit(
            program_scenes=self.program, show_kit=self.kit, project="ep",
            broll=[{"broll_id": "b1", "file_name": "broll_01.png", "description": "x"}],
        )
        layouts = [s["layout"] for s in plan["scenes"]]
        self.assertEqual(layouts, ["intro", "show_image", "3cam", "2cam_broll", "outro"])
        # timeline is contiguous: each scene starts where the previous ends
        ends = [sk.to_seconds(s["end"]) for s in plan["scenes"]]
        starts = [sk.to_seconds(s["start"]) for s in plan["scenes"]]
        for i in range(1, len(plan["scenes"])):
            self.assertAlmostEqual(starts[i], ends[i - 1])
        # intro default 15s, show_image 5s -> first program starts at 20s
        self.assertAlmostEqual(starts[2], 20.0)

    def test_program_source_start_is_preserved(self):
        plan = sk.merge_with_show_kit(program_scenes=self.program, show_kit=self.kit, project="ep")
        program = [s for s in plan["scenes"] if s["scene_id"].startswith("S")]
        self.assertEqual(program[0]["source_start"], "00:00:00.000")
        self.assertEqual(program[1]["source_start"], "00:00:40.000")

    def test_intro_lower_third_points_at_first_program_scene(self):
        plan = sk.merge_with_show_kit(program_scenes=self.program, show_kit=self.kit, project="ep")
        settings = {s["setting"]: s["value"] for s in plan["settings"]}
        first_program = next(s["scene_id"] for s in plan["scenes"] if s["scene_id"].startswith("S"))
        self.assertEqual(settings["intro_lower_third_scene_id"], first_program)

    def test_show_kit_settings_audio_assets_attached(self):
        plan = sk.merge_with_show_kit(program_scenes=self.program, show_kit=self.kit, project="ep")
        settings = {s["setting"]: s["value"] for s in plan["settings"]}
        self.assertEqual(settings["background_video"], "background.mov")
        self.assertEqual([a["audio_id"] for a in plan["audio"]], ["intro_music", "outro_music"])
        self.assertTrue(any(a["asset_key"] == "background_video" for a in plan["assets"]))


if __name__ == "__main__":
    unittest.main()
