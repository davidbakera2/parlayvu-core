"""Tests for the Podcast Parlay agentic planning workflow.

LLM calls are mocked at the `_agent_llm` seam, so these run with no API keys.
"""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.agents.workflows import podcast_parlay as pp


def _fake_llm(content: str) -> MagicMock:
    """An LLM whose .invoke() returns a message with the given .content string."""
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content=content))
    return llm


BLAKE_JSON = json.dumps({
    "episode_summary": "David explains air-duct cleaning myths.",
    "people": [
        {"name": "David Hart", "title": "Founder & CEO, RamAir", "speaker": "guest_01"},
    ],
    "segments": [
        {
            "segment_id": "SEG01", "start": "00:00:10.000", "end": "00:02:30.000",
            "speaker": "guest_01", "topic": "Origin story",
            "summary": "How RamAir started.", "notable_quote": "We started in a garage.",
            "suggested_layout": "2cam", "lower_third_top": "David Hart",
            "lower_third_bottom": "Origin story", "broll_ideas": [],
        },
        {
            "segment_id": "SEG02", "start": "00:02:30.000", "end": "00:05:00.000",
            "speaker": "both", "topic": "Duct cleaning myths",
            "summary": "Common misconceptions.", "notable_quote": "",
            "suggested_layout": "2cam_broll", "lower_third_top": "David Hart",
            "lower_third_bottom": "Duct cleaning myths", "broll_ideas": ["duct footage"],
        },
    ],
})

ALEX_JSON = json.dumps({
    "program_scenes": [
        {"layout": "3cam", "cameras": ["host", "guest_01", "guest_02"],
         "source_start": "00:00:00.000", "duration": "00:02:20.000",
         "top_row_text": "David Hart", "bottom_row_text": "Origin story"},
        {"layout": "2cam", "cameras": ["host", "guest_02"],
         "source_start": "00:02:30.000", "duration": "00:02:30.000",
         "top_row_text": "John Miles", "bottom_row_text": "Duct cleaning myths"},
    ],
})


def _dispatch(blake=BLAKE_JSON, alex=ALEX_JSON):
    def _inner(name: str):
        return _fake_llm(blake if name == "blake" else alex)
    return _inner


class NormalizeTests(unittest.TestCase):
    def test_fills_defaults_and_assigns_ids(self):
        plan = pp.normalize_video_plan({"scenes": [{"layout": "2cam"}]}, project="ep")
        scene = plan["scenes"][0]
        self.assertEqual(scene["scene_id"], "S001")          # auto-assigned
        self.assertEqual(scene["host_source"], "host.mp4")    # default filled
        self.assertIn("top_row_text", scene)                  # all keys present
        self.assertEqual(plan["project"], "ep")
        self.assertTrue(plan["settings"])                     # default settings applied

    def test_coerces_invalid_enums(self):
        plan = pp.normalize_video_plan(
            {"scenes": [{"layout": "bogus"}], "graphics": [{"type": "bogus"}]},
            project="ep",
        )
        self.assertEqual(plan["scenes"][0]["layout"], "2cam")      # invalid -> default
        self.assertEqual(plan["graphics"][0]["type"], "topic_card")

    def test_broll_filename_defaulted_from_id(self):
        plan = pp.normalize_video_plan({"broll": [{}]}, project="ep")
        self.assertEqual(plan["broll"][0]["broll_id"], "broll_01")
        self.assertEqual(plan["broll"][0]["file_name"], "broll_01.mp4")


class FenceStripTests(unittest.TestCase):
    def test_strips_json_code_fence(self):
        self.assertEqual(pp._load_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_plain_json(self):
        self.assertEqual(pp._load_json('{"a": 1}'), {"a": 1})


class BlakeNodeTests(unittest.TestCase):
    def test_parses_segments_and_people(self):
        with patch.object(pp, "_agent_llm", _dispatch()):
            out = pp.blake_node(pp.PodcastPlanState(transcript="hi", episode_title="Ep04"))
        self.assertIsNone(out.get("error"))
        self.assertEqual(len(out["segment_analysis"]["segments"]), 2)
        self.assertEqual(out["segment_analysis"]["people"][0]["name"], "David Hart")

    def test_returns_error_on_bad_json(self):
        with patch.object(pp, "_agent_llm", lambda name: _fake_llm("not json at all")):
            out = pp.blake_node(pp.PodcastPlanState(transcript="hi"))
        self.assertIn("Blake segment analysis failed", out["error"])


def _settings_map(plan):
    return {s["setting"]: s["value"] for s in plan["settings"]}


class AlexNodeTests(unittest.TestCase):
    def test_merges_program_scenes_onto_show_kit(self):
        state = pp.PodcastPlanState(
            transcript="hi", project_id="ramair-sfth",
            segment_analysis=json.loads(BLAKE_JSON),
        )
        with patch.object(pp, "_agent_llm", _dispatch()):
            out = pp.alex_node(state)
        plan = out["video_plan"]
        self.assertEqual(plan["project"], "ramair-sfth")
        # Show Kit bookends wrap Alex's program scenes.
        self.assertEqual(plan["scenes"][0]["layout"], "intro")
        self.assertEqual(plan["scenes"][1]["layout"], "show_image")
        self.assertEqual(plan["scenes"][-1]["layout"], "outro")
        self.assertEqual([s["layout"] for s in plan["scenes"][2:-1]], ["3cam", "2cam"])
        # Per-scene cameras honored: the 2cam scene shows host + guest_02 (not guest_01).
        two_cam = plan["scenes"][3]
        self.assertEqual(two_cam["host_source"], "host.mp4")
        self.assertEqual(two_cam["guest_02_source"], "guest_02.mp4")
        self.assertNotIn("guest_01_source", two_cam)
        # Show Kit format applied.
        settings = _settings_map(plan)
        self.assertEqual(settings["background_video"], "background.mov")
        self.assertEqual(settings["intro_lower_third_scene_id"], plan["scenes"][2]["scene_id"])
        self.assertEqual([a["audio_id"] for a in plan["audio"]], ["intro_music", "outro_music"])

    def test_falls_back_to_segments_when_planner_unusable(self):
        state = pp.PodcastPlanState(
            transcript="hi", project_id="ep",
            segment_analysis=json.loads(BLAKE_JSON),
        )
        with patch.object(pp, "_agent_llm", _dispatch(alex="garbage not json")):
            out = pp.alex_node(state)
        plan = out["video_plan"]
        self.assertEqual(plan["scenes"][0]["layout"], "intro")
        self.assertEqual(plan["scenes"][-1]["layout"], "outro")
        # program scenes built from Blake's segments
        self.assertTrue(any(s.get("bottom_row_text") == "Origin story" for s in plan["scenes"]))

    def test_short_circuits_on_upstream_error(self):
        state = pp.PodcastPlanState(transcript="hi", error="boom")
        with patch.object(pp, "_agent_llm", _dispatch()):
            out = pp.alex_node(state)
        self.assertEqual(out, {})


class ShowNotesContextTests(unittest.TestCase):
    """show_notes must reach both planners as LOOSE context, and be absent when unset."""

    def _capture_prompt(self, node, state):
        captured = {}

        def _capturing(name: str):
            llm = MagicMock()

            def _invoke(messages):
                captured["text"] = "\n".join(getattr(m, "content", "") for m in messages)
                return MagicMock(content=BLAKE_JSON if name == "blake" else ALEX_JSON)

            llm.invoke = MagicMock(side_effect=_invoke)
            return llm

        with patch.object(pp, "_agent_llm", _capturing):
            node(state)
        return captured["text"]

    def test_show_notes_injected_as_loose_into_blake(self):
        state = pp.PodcastPlanState(transcript="hi", show_notes="Topic: SaniJet rollout")
        text = self._capture_prompt(pp.blake_node, state)
        self.assertIn("SaniJet rollout", text)
        self.assertIn("LOOSE", text)        # framed as loose, not a structure
        self.assertIn("DO NOT force", text)

    def test_show_notes_injected_into_alex(self):
        state = pp.PodcastPlanState(
            transcript="hi", show_notes="Topic: SaniJet rollout",
            segment_analysis=json.loads(BLAKE_JSON),
        )
        text = self._capture_prompt(pp.alex_node, state)
        self.assertIn("SaniJet rollout", text)
        self.assertIn("LOOSE", text)

    def test_absent_when_unset(self):
        state = pp.PodcastPlanState(transcript="hi")
        text = self._capture_prompt(pp.blake_node, state)
        self.assertNotIn("Show notes", text)


class RunWorkflowTests(unittest.TestCase):
    def test_end_to_end_returns_video_plan(self):
        with patch.object(pp, "_agent_llm", _dispatch()):
            result = asyncio.run(pp.run_podcast_parlay_planning(
                transcript="full transcript text",
                episode_title="Straight From The Hart Ep04",
                project_id="ramair-sfth",
            ))
        self.assertIsNone(result.get("error"))
        plan = result["video_plan"]
        self.assertEqual(plan["project"], "ramair-sfth")
        # intro + show_image + 2 program scenes + outro = 5
        self.assertEqual([s["layout"] for s in plan["scenes"]],
                         ["intro", "show_image", "3cam", "2cam", "outro"])
        self.assertEqual(result["segment_analysis"]["episode_summary"][:5], "David")

    def test_blake_error_propagates_without_plan(self):
        with patch.object(pp, "_agent_llm", lambda name: _fake_llm("nope")):
            result = asyncio.run(pp.run_podcast_parlay_planning(transcript="x"))
        self.assertIn("Blake segment analysis failed", result["error"])
        self.assertIsNone(result.get("video_plan"))


class PersistenceTests(unittest.TestCase):
    def test_writes_plan_and_segment_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pp, "CLIENT_ARTIFACTS_ROOT", Path(tmp)):
                written = pp.persist_video_plan(
                    client_id="ramair",
                    episode_title="Straight From The Hart Ep04",
                    video_plan={"project": "ep", "scenes": [{"scene_id": "S001"}]},
                    segment_analysis={"segments": []},
                )
            base = Path(tmp) / "ramair" / "02_Planning" / "podcast_plans" / "straight-from-the-hart-ep04"
            self.assertTrue((base / "video_plan.json").is_file())
            self.assertTrue((base / "segment_analysis.json").is_file())
            self.assertEqual(written["slug"], "straight-from-the-hart-ep04")
            saved = json.loads((base / "video_plan.json").read_text())
            self.assertEqual(saved["scenes"][0]["scene_id"], "S001")

    def test_rejects_path_escaping_client_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pp, "CLIENT_ARTIFACTS_ROOT", Path(tmp)):
                for bad in ("../evil", "a/b", ""):
                    with self.assertRaises(ValueError):
                        pp.persist_video_plan(
                            client_id=bad, episode_title="x", video_plan={},
                        )


class EndpointTests(unittest.TestCase):
    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_plan_endpoint_returns_video_plan(self):
        client = self._client()
        with patch.dict("os.environ", {"PROJECT_MEMORY_ENABLED": "false"}):
            with patch.object(pp, "_agent_llm", _dispatch()):
                resp = client.post("/parlays/podcast/plan", json={
                    "transcript": "full transcript",
                    "episode_title": "Straight From The Hart Ep04",
                })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "generated")  # no client_id -> no approval
        # Show Kit-merged plan: intro + show_image + 2 program + outro
        self.assertEqual([s["layout"] for s in body["video_plan"]["scenes"]],
                         ["intro", "show_image", "3cam", "2cam", "outro"])
        self.assertIsNone(body["plan_files"])           # not persisted without client_id

    def test_plan_endpoint_persists_and_requests_approval(self):
        client = self._client()
        fake_approval = {"id": "appr-1", "status": "pending"}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"PROJECT_MEMORY_ENABLED": "false"}), \
                 patch.object(pp, "CLIENT_ARTIFACTS_ROOT", Path(tmp)), \
                 patch.object(pp, "_agent_llm", _dispatch()), \
                 patch("app.main.request_approval", return_value=fake_approval) as mock_appr:
                resp = client.post("/parlays/podcast/plan", json={
                    "transcript": "full transcript",
                    "episode_title": "Ep04",
                    "client_id": "ramair",
                    "project_id": "ramair-sfth",
                })
            self.assertTrue((Path(tmp) / "ramair" / "02_Planning" / "podcast_plans" / "ep04" / "video_plan.json").is_file())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "pending_approval")
        self.assertEqual(body["approval"], fake_approval)
        self.assertIsNotNone(body["plan_files"])
        self.assertEqual(mock_appr.call_args.kwargs["action_type"], "video_plan")
        self.assertEqual(mock_appr.call_args.kwargs["requested_by_agent"], "alex")

    def test_approval_can_be_disabled(self):
        client = self._client()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"PROJECT_MEMORY_ENABLED": "false"}), \
                 patch.object(pp, "CLIENT_ARTIFACTS_ROOT", Path(tmp)), \
                 patch.object(pp, "_agent_llm", _dispatch()), \
                 patch("app.main.request_approval") as mock_appr:
                resp = client.post("/parlays/podcast/plan", json={
                    "transcript": "t", "episode_title": "Ep04",
                    "client_id": "ramair", "project_id": "ramair-sfth",
                    "request_approval": False,
                })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "generated")
        mock_appr.assert_not_called()

    def test_plan_endpoint_rejects_empty_transcript(self):
        client = self._client()
        resp = client.post("/parlays/podcast/plan", json={"transcript": "   "})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
