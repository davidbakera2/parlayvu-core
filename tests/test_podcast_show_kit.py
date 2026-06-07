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


class BrollManifestTests(unittest.TestCase):
    def test_scans_real_broll_files(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for n in ("broll_01.png", "broll_02.jpg", "host.mp4", "broll_03.mp4", "notes.txt"):
                (d / n).write_text("x")
            manifest = sk.build_broll_manifest(d)
        names = [m["file_name"] for m in manifest]
        self.assertEqual(names, ["broll_01.png", "broll_02.jpg", "broll_03.mp4"])  # only b-roll, sorted
        self.assertEqual(manifest[0]["broll_id"], "broll_01")

    def test_empty_when_no_dir(self):
        self.assertEqual(sk.build_broll_manifest(None), [])
        self.assertEqual(sk.build_broll_manifest("/no/such/dir"), [])

    def test_excludes_clips_marked_usage_exclude(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for n in ("broll_01.png", "broll_02.jpg", "broll_03.mp4"):
                (d / n).write_text("x")
            (d / "broll.json").write_text(json.dumps([
                {"file": "broll_02.jpg", "description": "bad take", "tags": [], "usage": "exclude"},
            ]), encoding="utf-8")
            manifest = sk.build_broll_manifest(d)
        names = [m["file_name"] for m in manifest]
        self.assertEqual(names, ["broll_01.png", "broll_03.mp4"])  # broll_02 filtered out


class CameraRosterTests(unittest.TestCase):
    def test_formats_names_and_titles(self):
        roster = sk.format_camera_roster({
            "host": {"name": "David Baker", "title": "Host"},
            "guest_01": {"name": "David Hart", "title": "Founder & CEO, RAM AIR"},
            "guest_02": "John Miles",
        })
        self.assertIn("host = David Baker (Host)", roster)
        self.assertIn("guest_01 = David Hart (Founder & CEO, RAM AIR)", roster)
        self.assertIn("guest_02 = John Miles", roster)

    def test_empty(self):
        self.assertEqual(sk.format_camera_roster(None), "")


class CameraSelectionTests(unittest.TestCase):
    def setUp(self):
        self.kit = sk.load_show_kit("parlayvu_interview")

    def test_explicit_cameras_set_only_those_sources(self):
        plan = sk.merge_with_show_kit(
            program_scenes=[
                {"layout": "2cam", "cameras": ["host", "guest_02"],
                 "source_start": "00:00:00.000", "duration": "00:00:10.000"},
            ],
            show_kit=self.kit, project="ep",
        )
        scene = next(s for s in plan["scenes"] if s["scene_id"].startswith("S"))
        self.assertEqual(scene["host_source"], "host.mp4")
        self.assertEqual(scene["guest_02_source"], "guest_02.mp4")
        self.assertNotIn("guest_01_source", scene)  # guest_01 not shown

    def test_layout_inferred_cameras_when_unspecified(self):
        plan = sk.merge_with_show_kit(
            program_scenes=[{"layout": "3cam", "source_start": "0", "duration": "10"}],
            show_kit=self.kit, project="ep",
        )
        scene = next(s for s in plan["scenes"] if s["scene_id"].startswith("S"))
        self.assertEqual(scene["host_source"], "host.mp4")
        self.assertEqual(scene["guest_01_source"], "guest_01.mp4")
        self.assertEqual(scene["guest_02_source"], "guest_02.mp4")  # 3cam -> all three

    def test_4cam_infers_four_cameras_including_guest_03(self):
        plan = sk.merge_with_show_kit(
            program_scenes=[{"layout": "4cam", "source_start": "0", "duration": "10"}],
            show_kit=self.kit, project="ep",
        )
        scene = next(s for s in plan["scenes"] if s["scene_id"].startswith("S"))
        self.assertEqual(scene["host_source"], "host.mp4")
        self.assertEqual(scene["guest_01_source"], "guest_01.mp4")
        self.assertEqual(scene["guest_02_source"], "guest_02.mp4")
        self.assertEqual(scene["guest_03_source"], "guest_03.mp4")  # 4cam -> all four

    def test_new_portrait_broll_layouts_are_program_layouts(self):
        for layout in ("1cam_broll", "1cam_brollp", "2cam_brollp", "3cam_brollp", "4cam_brollp", "4cam", "4cam_broll"):
            self.assertIn(layout, sk.PROGRAM_LAYOUTS)
            plan = sk.merge_with_show_kit(
                program_scenes=[{"layout": layout, "source_start": "0", "duration": "10",
                                 "broll_file": "broll_01.png"}],
                show_kit=self.kit, project="ep",
            )
            # the scene survives the merge (not skipped as a non-program layout)
            self.assertTrue(any(s.get("layout") == layout for s in plan["scenes"]))


if __name__ == "__main__":
    unittest.main()
