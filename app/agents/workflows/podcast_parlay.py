"""Podcast Parlay — Agentic Planning layer.

Takes an interview transcript (Riverside-style, ideally with timestamps + speaker
labels) and produces a structured ``video_plan`` that can drive downstream video
assembly. See docs/parlays/podcast-parlay.md (the Parlay) and
docs/parlays/video-plan-schema.md (the output contract).

Two LLM stages, mirroring app/agents/workflows/meeting_strategy.py:

  1. Blake (Intelligence) — analyze the transcript into timestamped segments with
     topic, summary, notable quote, a suggested camera layout, lower-third text, and
     b-roll ideas; plus the people on the episode (for name cards).
  2. Alex (Visuals) — assemble the segments into a ``video_plan`` (scenes, graphics,
     b-roll) targeting the schema.

The plan is always normalized to the schema (defaults filled, enums coerced). If the
planner fails to return usable JSON, a deterministic fallback builds a basic plan
straight from Blake's segments, so the workflow always returns something usable for
human review.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

logger = logging.getLogger("parlayvu.podcast_parlay")

# ---------------------------------------------------------------------------
# Schema constants (see docs/parlays/video-plan-schema.md)
# ---------------------------------------------------------------------------
LAYOUTS = {
    "intro", "show_image", "1cam", "2cam", "2cam_broll", "3cam", "3cam_broll", "outro",
}
GRAPHIC_TYPES = {"name_card", "broll_card", "callout", "topic_card"}

SCENE_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "scene_id": "",
    "start": "00:00:00.000",
    "end": "00:00:00.000",
    "duration": "",
    "layout": "2cam",
    "source_start": "",
    "primary_camera": "",
    "host_source": "host.mp4",
    "guest_01_source": "guest_01.mp4",
    "guest_02_source": "",
    "broll_id": "",
    "broll_file": "",
    "broll_source_start": "",
    "top_row_text": "",
    "bottom_row_text": "",
    "notes": "",
}
GRAPHIC_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "graphic_id": "",
    "type": "topic_card",
    "start": "00:00:00.000",
    "end": "00:00:00.000",
    "text_line_1": "",
    "text_line_2": "",
    "position": "",
    "style": "",
    "linked_scene_id": "",
    "notes": "",
}
BROLL_DEFAULTS: dict[str, Any] = {
    "broll_id": "",
    "file_name": "",
    "description": "",
    "default_source_start": "",
    "notes": "",
}

DEFAULT_SETTINGS = [
    {"setting": "template_name", "value": "ramair_interview", "notes": ""},
    {"setting": "timeline_mode", "value": "full_rendered", "notes": ""},
]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
BLAKE_SEGMENT_PROMPT = """You are Blake Quinn, Intelligence & Insights specialist at ParlayVU.ai.

You are analyzing a recorded interview transcript for the Podcast Parlay. Break the
interview into natural content segments and return ONLY valid JSON matching this schema
exactly — no markdown, no extra text:

{
  "episode_summary": "2-3 sentence summary of the episode",
  "people": [
    {"name": "Full Name", "title": "Role, Company", "speaker": "host|guest_01|guest_02"}
  ],
  "segments": [
    {
      "segment_id": "SEG01",
      "start": "HH:MM:SS.000",
      "end": "HH:MM:SS.000",
      "speaker": "host|guest_01|guest_02|both",
      "topic": "short topic label",
      "summary": "1-2 sentence summary of this segment",
      "notable_quote": "a strong verbatim quote from this segment, or empty",
      "suggested_layout": "1cam|2cam|2cam_broll|3cam|3cam_broll",
      "lower_third_top": "speaker name or identity for the lower third",
      "lower_third_bottom": "topic line for the lower third",
      "broll_ideas": ["short b-roll idea", "..."]
    }
  ]
}

Rules:
- Use the transcript's real timestamps when present. If timestamps are missing, estimate
  reasonable monotonically-increasing times.
- Prefer 4-12 substantive segments. Merge trivial back-and-forth into coherent topics.
- suggested_layout: use 2cam_broll or 3cam_broll only when there is a clear b-roll idea.
- Only include people you can identify from the transcript.
- Be evidence-based; do not invent facts not supported by the transcript."""

ALEX_PLAN_PROMPT = """You are Alex Rivera, Visuals & Design specialist at ParlayVU.ai.

Using the segment analysis, compose a video_plan for the Podcast Parlay. Return ONLY
valid JSON matching this schema exactly — no markdown, no extra text:

{
  "scenes": [
    {
      "scene_id": "S001",
      "enabled": true,
      "start": "HH:MM:SS.000",
      "end": "HH:MM:SS.000",
      "layout": "intro|show_image|1cam|2cam|2cam_broll|3cam|3cam_broll|outro",
      "primary_camera": "host|guest_01|guest_02|",
      "broll_id": "",
      "top_row_text": "lower third top row",
      "bottom_row_text": "lower third bottom row",
      "notes": ""
    }
  ],
  "graphics": [
    {
      "graphic_id": "G001",
      "enabled": true,
      "type": "name_card|topic_card|broll_card|callout",
      "start": "HH:MM:SS.000",
      "end": "HH:MM:SS.000",
      "text_line_1": "main text",
      "text_line_2": "secondary text",
      "linked_scene_id": "S001"
    }
  ],
  "broll": [
    {"broll_id": "broll_01", "file_name": "broll_01.mp4", "description": "what it shows"}
  ]
}

Rules:
- Open with an `intro` scene and a `show_image` scene, and close with an `outro` scene.
- Create one interview scene per segment, in order, using the segment's suggested_layout
  and timestamps; carry the lower-third text into top_row_text / bottom_row_text.
- For each identified person, add a `name_card` graphic on their first interview scene
  (text_line_1 = name, text_line_2 = title), shown for ~5 seconds.
- Add a `topic_card` graphic when a segment introduces a clearly new topic.
- When a segment's layout includes b-roll, add a `broll[]` entry and set the scene's
  broll_id to match.
- Keep scene_ids and graphic_ids stable and sequential (S001.., G001.., broll_01..)."""


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class PodcastPlanState(BaseModel):
    transcript: str
    episode_title: str = "Episode"
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    brand_voice: Optional[str] = None
    project_context: Optional[dict] = None
    segment_analysis: Optional[dict] = None
    video_plan: Optional[dict] = None
    error: Optional[str] = None


def _agent_llm(name: str):
    """Indirection over the registry so tests can patch a single seam."""
    from app.agents.registry import get_agent_llm

    return get_agent_llm(name)


def _strip_json_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _load_json(raw: str) -> Any:
    return json.loads(_strip_json_fence(raw))


# ---------------------------------------------------------------------------
# Normalization (keeps the plan schema-valid regardless of LLM output)
# ---------------------------------------------------------------------------
def _normalize_row(row: dict, defaults: dict) -> dict:
    out = dict(defaults)
    if isinstance(row, dict):
        for key, value in row.items():
            if key in defaults:
                out[key] = value
    out["enabled"] = bool(out.get("enabled", True)) if "enabled" in defaults else out.get("enabled")
    return out


def normalize_video_plan(plan: dict, *, project: str) -> dict:
    """Coerce an LLM-produced plan into the documented schema with all fields present."""
    plan = plan if isinstance(plan, dict) else {}

    scenes = []
    for i, scene in enumerate(plan.get("scenes") or [], start=1):
        norm = _normalize_row(scene, SCENE_DEFAULTS)
        if not norm["scene_id"]:
            norm["scene_id"] = f"S{i:03d}"
        if norm["layout"] not in LAYOUTS:
            norm["layout"] = SCENE_DEFAULTS["layout"]
        scenes.append(norm)

    graphics = []
    for i, graphic in enumerate(plan.get("graphics") or [], start=1):
        norm = _normalize_row(graphic, GRAPHIC_DEFAULTS)
        if not norm["graphic_id"]:
            norm["graphic_id"] = f"G{i:03d}"
        if norm["type"] not in GRAPHIC_TYPES:
            norm["type"] = GRAPHIC_DEFAULTS["type"]
        graphics.append(norm)

    broll = []
    for i, item in enumerate(plan.get("broll") or [], start=1):
        norm = _normalize_row(item, BROLL_DEFAULTS)
        if not norm["broll_id"]:
            norm["broll_id"] = f"broll_{i:02d}"
        if not norm["file_name"]:
            norm["file_name"] = f"{norm['broll_id']}.mp4"
        broll.append(norm)

    assets = plan.get("assets") if isinstance(plan.get("assets"), list) else []
    settings = plan.get("settings") if isinstance(plan.get("settings"), list) else list(DEFAULT_SETTINGS)

    return {
        "project": project,
        "scenes": scenes,
        "graphics": graphics,
        "broll": broll,
        "assets": assets,
        "settings": settings,
    }


def _fallback_plan_from_segments(analysis: dict, *, project: str) -> dict:
    """Deterministic plan built straight from Blake's segments (used if the planner fails)."""
    segments = (analysis or {}).get("segments") or []
    scenes: list[dict] = [
        {"scene_id": "S001", "layout": "intro", "host_source": "intro.mp4",
         "start": "00:00:00.000", "end": "00:00:06.000", "notes": "Opening clip"},
        {"scene_id": "S002", "layout": "show_image", "host_source": "show_image.png",
         "start": "00:00:06.000", "end": "00:00:10.000", "notes": "Show image"},
    ]
    for i, seg in enumerate(segments, start=1):
        seg = seg if isinstance(seg, dict) else {}
        scenes.append({
            "scene_id": f"S{i + 2:03d}",
            "layout": seg.get("suggested_layout") or "2cam",
            "start": seg.get("start") or "00:00:00.000",
            "end": seg.get("end") or "00:00:00.000",
            "top_row_text": seg.get("lower_third_top") or "",
            "bottom_row_text": seg.get("lower_third_bottom") or seg.get("topic") or "",
            "notes": seg.get("summary") or "",
        })
    scenes.append({"scene_id": f"S{len(segments) + 3:03d}", "layout": "outro",
                   "host_source": "outro.mp4", "notes": "Closing"})

    graphics = []
    for i, person in enumerate((analysis or {}).get("people") or [], start=1):
        person = person if isinstance(person, dict) else {}
        graphics.append({
            "graphic_id": f"G{i:03d}",
            "type": "name_card",
            "text_line_1": person.get("name") or "",
            "text_line_2": person.get("title") or "",
        })

    return normalize_video_plan(
        {"scenes": scenes, "graphics": graphics, "broll": []}, project=project
    )


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------
def blake_node(state: PodcastPlanState) -> dict:
    llm = _agent_llm("blake")

    context_block = ""
    if state.project_context:
        context_block = f"\nProject context:\n{json.dumps(state.project_context, default=str)[:2000]}\n"

    try:
        response = llm.invoke([
            SystemMessage(content=BLAKE_SEGMENT_PROMPT),
            HumanMessage(content=f"Episode: {state.episode_title}{context_block}\nTranscript:\n{state.transcript}"),
        ])
        analysis = _load_json(response.content)
        if not isinstance(analysis, dict):
            raise ValueError("Blake returned non-object JSON")
    except Exception as exc:
        logger.exception("Blake segment analysis failed")
        return {"error": f"Blake segment analysis failed: {exc}"}

    analysis.setdefault("segments", [])
    analysis.setdefault("people", [])
    logger.info(
        "Blake segment analysis complete | segments=%d people=%d",
        len(analysis.get("segments", [])), len(analysis.get("people", [])),
    )
    return {"segment_analysis": analysis}


def alex_node(state: PodcastPlanState) -> dict:
    if state.error:
        return {}

    project = state.project_id or "podcast-episode"
    analysis = state.segment_analysis or {}

    llm = _agent_llm("alex")
    brand_block = f"\nBrand voice: {state.brand_voice}\n" if state.brand_voice else ""
    user = (
        f"Episode: {state.episode_title}{brand_block}\n"
        f"Segment analysis:\n{json.dumps(analysis, default=str)[:8000]}"
    )

    try:
        response = llm.invoke([
            SystemMessage(content=ALEX_PLAN_PROMPT),
            HumanMessage(content=user),
        ])
        raw_plan = _load_json(response.content)
        plan = normalize_video_plan(raw_plan, project=project)
        if not plan["scenes"]:
            raise ValueError("planner produced no scenes")
    except Exception as exc:
        logger.warning("Alex planner output unusable (%s) — using deterministic fallback", exc)
        plan = _fallback_plan_from_segments(analysis, project=project)

    logger.info(
        "Video plan composed | scenes=%d graphics=%d broll=%d",
        len(plan["scenes"]), len(plan["graphics"]), len(plan["broll"]),
    )
    return {"video_plan": plan}


_graph = None


def get_podcast_plan_graph():
    global _graph
    if _graph is None:
        workflow = StateGraph(PodcastPlanState)
        workflow.add_node("blake", blake_node)
        workflow.add_node("alex", alex_node)
        workflow.set_entry_point("blake")
        workflow.add_edge("blake", "alex")
        workflow.add_edge("alex", END)
        _graph = workflow.compile()
    return _graph


async def run_podcast_parlay_planning(
    *,
    transcript: str,
    episode_title: str = "Episode",
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    brand_voice: Optional[str] = None,
    project_context: Optional[dict] = None,
) -> dict:
    """Run the Podcast Parlay planning workflow and return its final state dict."""
    graph = get_podcast_plan_graph()
    initial = PodcastPlanState(
        transcript=transcript,
        episode_title=episode_title,
        project_id=project_id,
        client_id=client_id,
        brand_voice=brand_voice,
        project_context=project_context,
    )
    result = await graph.ainvoke(initial)
    return result if isinstance(result, dict) else result.model_dump()
