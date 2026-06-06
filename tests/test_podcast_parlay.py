"""Tests for the Podcast Parlay agentic planning workflow.

LLM calls are mocked at the `_agent_llm` seam, so these run with no API keys.
"""

import asyncio
import json
import unittest
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
    "scenes": [
        {"scene_id": "S001", "layout": "intro", "start": "00:00:00.000", "end": "00:00:06.000"},
        {"scene_id": "S002", "layout": "show_image", "start": "00:00:06.000", "end": "00:00:10.000"},
        {"scene_id": "S003", "layout": "2cam", "start": "00:00:10.000", "end": "00:02:30.000",
         "top_row_text": "David Hart", "bottom_row_text": "Origin story"},
        {"scene_id": "S004", "layout": "2cam_broll", "start": "00:02:30.000", "end": "00:05:00.000",
         "top_row_text": "David Hart", "bottom_row_text": "Duct cleaning myths", "broll_id": "broll_01"},
        {"scene_id": "S005", "layout": "outro"},
    ],
    "graphics": [
        {"graphic_id": "G001", "type": "name_card", "text_line_1": "David Hart",
         "text_line_2": "Founder & CEO, RamAir", "linked_scene_id": "S003"},
    ],
    "broll": [
        {"broll_id": "broll_01", "file_name": "broll_01.mp4", "description": "Duct footage"},
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


class AlexNodeTests(unittest.TestCase):
    def test_builds_normalized_plan(self):
        state = pp.PodcastPlanState(
            transcript="hi", project_id="ramair-sfth",
            segment_analysis=json.loads(BLAKE_JSON),
        )
        with patch.object(pp, "_agent_llm", _dispatch()):
            out = pp.alex_node(state)
        plan = out["video_plan"]
        self.assertEqual(plan["project"], "ramair-sfth")
        self.assertEqual(plan["scenes"][0]["layout"], "intro")
        self.assertEqual(plan["scenes"][-1]["layout"], "outro")
        self.assertEqual(plan["graphics"][0]["type"], "name_card")
        self.assertEqual(plan["broll"][0]["broll_id"], "broll_01")

    def test_falls_back_when_planner_unusable(self):
        state = pp.PodcastPlanState(
            transcript="hi", project_id="ep",
            segment_analysis=json.loads(BLAKE_JSON),
        )
        with patch.object(pp, "_agent_llm", _dispatch(alex="garbage not json")):
            out = pp.alex_node(state)
        plan = out["video_plan"]
        # fallback builds intro + show_image + one scene per segment + outro
        self.assertEqual(plan["scenes"][0]["layout"], "intro")
        self.assertEqual(plan["scenes"][-1]["layout"], "outro")
        self.assertTrue(any(s["bottom_row_text"] == "Origin story" for s in plan["scenes"]))
        self.assertEqual(plan["graphics"][0]["text_line_1"], "David Hart")  # name card from people

    def test_short_circuits_on_upstream_error(self):
        state = pp.PodcastPlanState(transcript="hi", error="boom")
        with patch.object(pp, "_agent_llm", _dispatch()):
            out = pp.alex_node(state)
        self.assertEqual(out, {})


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
        # 2 framing scenes + 2 segment scenes + outro = 5
        self.assertEqual(len(plan["scenes"]), 5)
        self.assertEqual(result["segment_analysis"]["episode_summary"][:5], "David")

    def test_blake_error_propagates_without_plan(self):
        with patch.object(pp, "_agent_llm", lambda name: _fake_llm("nope")):
            result = asyncio.run(pp.run_podcast_parlay_planning(transcript="x"))
        self.assertIn("Blake segment analysis failed", result["error"])
        self.assertIsNone(result.get("video_plan"))


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
        self.assertEqual(body["status"], "generated")
        self.assertEqual(len(body["video_plan"]["scenes"]), 5)
        self.assertEqual(body["video_plan"]["graphics"][0]["type"], "name_card")

    def test_plan_endpoint_rejects_empty_transcript(self):
        client = self._client()
        resp = client.post("/parlays/podcast/plan", json={"transcript": "   "})
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
