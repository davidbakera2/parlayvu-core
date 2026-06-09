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
import re
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

from app.client_config import CLIENT_ARTIFACTS_ROOT
from app.agents.workflows.podcast_show_kit import (
    build_broll_manifest,
    format_camera_roster,
    load_show_kit,
    merge_with_show_kit,
    to_seconds,
)

logger = logging.getLogger("parlayvu.podcast_parlay")

# Persisted plans live under the client's planning folder (ARCHITECTURE.md §5).
PLANS_SUBPATH = Path("02_Planning") / "podcast_plans"

# ---------------------------------------------------------------------------
# Schema constants (see docs/parlays/video-plan-schema.md)
# ---------------------------------------------------------------------------
LAYOUTS = {
    "intro", "show_image", "1cam", "2cam", "2cam_broll", "3cam", "3cam_broll", "outro",
    # Data-driven layouts (render_video.py LAYOUT_BOXES). "*p" = tall/portrait b-roll panel;
    # 4cam layouts use a 4th camera (guest_03).
    "1cam_broll", "1cam_brollp", "2cam_brollp", "3cam_brollp", "4cam_brollp", "4cam", "4cam_broll",
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
      "speaker": "host|guest_01|guest_02|guest_03|both",
      "topic": "short topic label",
      "summary": "1-2 sentence summary of this segment",
      "notable_quote": "a strong verbatim quote from this segment, or empty",
      "suggested_layout": "1cam|2cam|3cam|4cam|*_broll (landscape b-roll) or *_brollp (portrait b-roll)",
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
- If a camera roster is provided, use its EXACT name spellings and map each segment's
  `speaker` to the correct roster slot (host / guest_01 / guest_02 / guest_03). The transcript
  may misspell names — always prefer the roster spelling. When the roster gives a title, use it
  verbatim.
- `title` is the person's role/affiliation only — e.g. "Host", "Founder & CEO, RAM AIR
  International". NEVER fold the show name into a title (the host is "Host", not
  "Host, <Show Name>").
- Be evidence-based; do not invent facts not supported by the transcript."""

ALEX_PLAN_PROMPT = """You are Alex Rivera, Visuals & Design specialist at ParlayVU.ai.

Using the segment analysis, compose the INTERVIEW SCENES for this episode. The opening intro,
show image, closing outro, music, background, and branding are added automatically from the
show's Show Kit — do NOT include them. Return ONLY valid JSON, no markdown, no extra text:

{
  "program_scenes": [
    {
      "layout": "1cam|2cam|3cam|4cam|1cam_broll|2cam_broll|3cam_broll|4cam_broll|1cam_brollp|2cam_brollp|3cam_brollp|4cam_brollp",
      "cameras": ["host", "guest_01"],
      "source_start": "HH:MM:SS.000",
      "duration": "HH:MM:SS.000",
      "primary_camera": "host|guest_01|guest_02|guest_03",
      "top_row_text": "NAME | TITLE of the person speaking",
      "bottom_row_text": "topic line",
      "broll_file": ""
    }
  ]
}

Rules:
- One scene per segment, in order. `source_start` is the segment's start and `duration` is
  (end - start) — positions IN THE TRIMMED INTERVIEW FOOTAGE (what the segment timestamps
  already represent).
- `cameras`: WHICH people to show (not their position). The renderer always places them in fixed
  role order — host far-left/top, then guest_01, guest_02, guest_03 — so you do NOT control
  left/right; just choose who is on screen. Match the count to the layout: `2cam`=2, `3cam`=3,
  `4cam`=4 (only when the roster has guest_03).
- Two-box layouts (`2cam`, `2cam_broll`, `2cam_brollp`) must be EITHER ["host","guest_01"] OR
  ["guest_01","guest_02"] — never ["host","guest_02"] (don't skip guest_01). If the host is in a
  two-person exchange with guest_02, use `3cam` so guest_01 is still shown, or pair host+guest_01.
- Use `3cam`/`3cam_broll`/`3cam_brollp` when all three are engaged, and to feature a specific
  guest (e.g. when guest_02 is telling his own story) while keeping everyone on screen.
- Lower thirds: top = "NAME | TITLE" of the current speaker (exact spelling from the roster);
  bottom = the topic. NEVER append the show name to a lower third — for the host that means
  "DAVID BAKER | HOST", not "... | HOST, STRAIGHT FROM THE HART".
- B-roll: only use a b-roll layout when a relevant clip exists in the provided B-ROLL LIBRARY.
  Set `broll_file` to an EXACT file name from that library — never invent a file name. Choose the
  b-roll panel shape by the clip: `*_broll` = a wide LANDSCAPE panel (good for documents, wide
  shots); `*_brollp` = a tall PORTRAIT panel (good for phone-shot vertical clips or tall images).
  List the cameras to keep on screen alongside the b-roll (e.g. `2cam_broll` = 2 cameras + a
  landscape panel; `3cam_brollp` = 3 cameras + a portrait panel).
- Do NOT emit intro / show_image / outro scenes, graphics, settings, or audio — the Show Kit
  owns all of that."""


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
    visual_system: str = "parlayvu_interview"
    assets_dir: Optional[str] = None
    cameras: Optional[dict] = None          # {host/guest_01/guest_02: {name, title}}
    show_notes: Optional[str] = None        # LOOSE pre-interview notes (topics/names/terms), not a structure
    broll_manifest: Optional[list] = None   # real b-roll files; auto-built from assets_dir
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


def _program_scenes_from_segments(analysis: dict) -> tuple[list[dict], list[dict]]:
    """Deterministic program scenes from Blake's segments (used if the planner fails).

    Returns (program_scenes, broll). Bookends/settings come from the Show Kit, not here.
    """
    program_scenes: list[dict] = []
    for seg in (analysis or {}).get("segments") or []:
        seg = seg if isinstance(seg, dict) else {}
        start = to_seconds(seg.get("start"))
        dur = max(0.0, to_seconds(seg.get("end")) - start)
        if dur <= 0:
            continue
        program_scenes.append({
            "layout": seg.get("suggested_layout") or "2cam",
            "source_start": seg.get("start") or "00:00:00.000",
            "duration": str(dur),  # seconds; the merge parses it
            "top_row_text": seg.get("lower_third_top") or "",
            "bottom_row_text": seg.get("lower_third_bottom") or seg.get("topic") or "",
            "notes": seg.get("summary") or "",
        })
    return program_scenes, []


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------
def _roster_block(state: PodcastPlanState) -> str:
    """Camera roster + show name + glossary for a planner prompt.

    Drives correct camera selection and exact spellings (names, show name, and brand/product
    terms the transcript commonly mis-transcribes, e.g. SaniJet).
    """
    parts = []
    roster = format_camera_roster(state.cameras)
    if roster:
        parts.append(
            "Camera roster (use these EXACT name spellings; the transcript may misspell them):\n"
            + roster
        )
    try:
        kit = load_show_kit(state.visual_system)
    except Exception:
        kit = {}
    if kit.get("show_name"):
        parts.append(f"Show name (exact spelling): {kit['show_name']}")
    if kit.get("known_terms"):
        parts.append(
            "Known terms — spell these EXACTLY, the transcript may misspell them: "
            + ", ".join(kit["known_terms"])
        )
    return ("\n" + "\n\n".join(parts) + "\n") if parts else ""


def _show_notes_block(state: PodcastPlanState) -> str:
    """Pre-interview show notes as LOOSE context only.

    These help with spellings, names, titles, terms, and lower-third topic phrasing, but the
    actual conversation usually diverges from any planned outline — so they must NOT be treated
    as a structure the segments/scenes follow.
    """
    notes = (state.show_notes or "").strip()
    if not notes:
        return ""
    return (
        "\nShow notes (LOOSE background only — pre-interview topics, names, and terms. The real "
        "conversation diverged from any plan, so DO NOT force the segments/scenes to follow this "
        "outline or its ordering; use it only as hints for correct spellings and lower-third "
        f"topic phrasing):\n{notes[:6000]}\n"
    )


def blake_node(state: PodcastPlanState) -> dict:
    llm = _agent_llm("blake")

    context_block = _roster_block(state) + _show_notes_block(state)
    if state.project_context:
        context_block += f"\nProject context:\n{json.dumps(state.project_context, default=str)[:2000]}\n"

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

    try:
        show_kit = load_show_kit(state.visual_system)
    except Exception as exc:
        logger.exception("Show Kit load failed")
        return {"error": f"Show Kit load failed: {exc}"}

    manifest = state.broll_manifest if state.broll_manifest is not None else build_broll_manifest(state.assets_dir)
    manifest_block = ""
    if manifest:
        def _b(b):
            line = f"- {b['file_name']}"
            if b.get("description"):
                line += f": {b['description']}"
            if b.get("tags"):
                line += f" [tags: {', '.join(b['tags'])}]"
            if b.get("usage"):
                line += f" ({b['usage']})"
            return line
        manifest_block = (
            "\nB-ROLL LIBRARY (use ONLY these exact file names for broll_file; match a clip to a "
            "beat by its description — 'specific' clips go on their topic, 'generic' clips can fill "
            "anywhere):\n" + "\n".join(_b(b) for b in manifest) + "\n"
        )

    editing_block = ""
    if show_kit.get("editing_style"):
        editing_block = f"\nEditing style:\n{show_kit['editing_style']}\n"

    llm = _agent_llm("alex")
    brand_block = f"\nBrand voice: {state.brand_voice}\n" if state.brand_voice else ""
    user = (
        f"Episode: {state.episode_title}{brand_block}"
        f"{_roster_block(state)}{_show_notes_block(state)}{editing_block}{manifest_block}\n"
        f"Segment analysis:\n{json.dumps(analysis, default=str)[:40000]}"
    )

    try:
        response = llm.invoke([
            SystemMessage(content=ALEX_PLAN_PROMPT),
            HumanMessage(content=user),
        ])
        out = _load_json(response.content)
        program_scenes = (out or {}).get("program_scenes") or []
        if not program_scenes:
            raise ValueError("planner produced no program scenes")
    except Exception as exc:
        logger.warning("Alex output unusable (%s) — building program scenes from segments", exc)
        program_scenes, _ = _program_scenes_from_segments(analysis)

    # Merge the per-episode program scenes onto the client's constant Show Kit format.
    # The b-roll library (real files) becomes the plan's broll[] so broll_file/broll_id resolve.
    plan = merge_with_show_kit(
        program_scenes=program_scenes,
        show_kit=show_kit,
        project=project,
        broll=manifest,
        assets_dir=state.assets_dir,
    )
    logger.info(
        "Video plan composed | scenes=%d (program=%d) broll=%d",
        len(plan["scenes"]), len(program_scenes), len(plan["broll"]),
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
    visual_system: str = "parlayvu_interview",
    assets_dir: Optional[str] = None,
    cameras: Optional[dict] = None,
    show_notes: Optional[str] = None,
) -> dict:
    """Run the Podcast Parlay planning workflow and return its final state dict.

    `visual_system` selects the client's Show Kit; pass `assets_dir` (the episode's assets
    folder) so the intro plays its full length and the real b-roll library is read; pass
    `cameras` (host/guest_01/guest_02 -> {name, title}) so the planner uses the right cameras
    and exact name spellings. `show_notes` is optional LOOSE pre-interview context (topics,
    names, terms) — it sharpens spellings and lower-thirds but is NOT treated as a structure
    the segments/scenes must follow (the real conversation typically diverges).
    """
    graph = get_podcast_plan_graph()
    initial = PodcastPlanState(
        transcript=transcript,
        episode_title=episode_title,
        project_id=project_id,
        client_id=client_id,
        brand_voice=brand_voice,
        project_context=project_context,
        visual_system=visual_system,
        assets_dir=assets_dir,
        cameras=cameras,
        show_notes=show_notes,
    )
    result = await graph.ainvoke(initial)
    return result if isinstance(result, dict) else result.model_dump()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "episode"


def _repo_rel(p: Path) -> str:
    try:
        return str(p.relative_to(Path.cwd())).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def persist_video_plan(
    *,
    client_id: str,
    episode_title: str,
    video_plan: dict,
    segment_analysis: Optional[dict] = None,
) -> dict[str, str]:
    """Write the plan (and segment analysis) under the client's planning folder.

    Returns repo-relative paths. Raises ValueError on a bad/escaping client_id.
    """
    if not client_id or any(sep in client_id for sep in ("/", "\\")) or client_id in (".", ".."):
        raise ValueError(f"Invalid client_id for plan persistence: {client_id!r}")

    slug = _slugify(episode_title)
    client_root = (CLIENT_ARTIFACTS_ROOT / client_id).resolve()
    plan_dir = (client_root / PLANS_SUBPATH / slug).resolve()
    if plan_dir != client_root and not plan_dir.is_relative_to(client_root):
        raise ValueError("Resolved plan path escapes the client artifacts root")

    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "video_plan.json"
    plan_path.write_text(json.dumps(video_plan, indent=2), encoding="utf-8")

    written = {
        "slug": slug,
        "plan_dir": _repo_rel(plan_dir),
        "video_plan_path": _repo_rel(plan_path),
    }
    if segment_analysis is not None:
        seg_path = plan_dir / "segment_analysis.json"
        seg_path.write_text(json.dumps(segment_analysis, indent=2), encoding="utf-8")
        written["segment_analysis_path"] = _repo_rel(seg_path)
    return written
