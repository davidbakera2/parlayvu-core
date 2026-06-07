"""Re-run Podcast Parlay planning for RamAir "Straight from the Hart" EP05.

Drives ``app.agents.workflows.podcast_parlay.run_podcast_parlay_planning`` with the
episode's real inputs and writes the result into the project's ``planning/`` folder
(``video_plan.json`` + ``segment_analysis.json``) where the renderer reads it.

Inputs wired here:
- transcript: ``planning/transcript.rebased.txt`` — already offset+trimmed so 0:00 is the
  start of the synced camera footage (the planner's source_start values are footage-relative).
- cameras: the EP05 roster with CLEAN role titles (host title is just "Host" — the planner is
  also instructed never to fold the show name into a lower third).
- assets_dir: the episode assets so the real b-roll library is read (excludes any clip marked
  usage="exclude" in broll.json) and the intro plays its full length.
- show_notes: ``planning/show_notes.md`` as LOOSE context (topics/names/terms), not a structure.

Both Blake and Alex run on Claude Sonnet here (the default map puts Blake on Grok) via an
``_agent_llm`` monkeypatch, with a high max_tokens so the large scene JSON isn't truncated.

Requires ANTHROPIC_API_KEY (and XAI_API_KEY) in ``.env``. Does NOT render — run
``python video_system/tools/render_video.py <project> --template <show_kit>`` afterwards.

Usage:
    python scripts/run_podcast_ep05_planning.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECT = REPO / "client_artifacts" / "ramair" / "03_Deliverables" / "podcast" / "ep05"

# Authoritative camera mapping. Titles are role/affiliation ONLY — no show name (see #5).
CAMERAS = {
    "host":     {"name": "David Baker", "title": "Host"},
    "guest_01": {"name": "David Hart",  "title": "Founder & CEO, RAM AIR International"},
    "guest_02": {"name": "John Miles",  "title": "Chief Science Officer, Superstratum Labs"},
}

# Both planners on Sonnet; max_tokens well above the default 1500 so a 30+ scene plan
# serialises without truncating into invalid JSON.
SONNET_MODEL = "claude-sonnet-4-6"
SONNET_MAX_TOKENS = 8000


def _load_env() -> None:
    env = REPO / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _sonnet():
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=SONNET_MODEL,
        api_key=os.environ["ANTHROPIC_API_KEY"],
        temperature=0.2,
        max_tokens=SONNET_MAX_TOKENS,
    )


async def main() -> None:
    _load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set (put it in .env)")

    planning = PROJECT / "planning"
    transcript_path = planning / "transcript.rebased.txt"
    if not transcript_path.is_file():
        raise SystemExit(f"transcript not found: {transcript_path}")
    transcript = transcript_path.read_text(encoding="utf-8")

    notes_path = planning / "show_notes.md"
    show_notes = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else None

    from app.agents.workflows import podcast_parlay as pp

    sonnet = _sonnet()
    pp._agent_llm = lambda name: sonnet  # noqa: E731 — Blake + Alex both on Sonnet

    result = await pp.run_podcast_parlay_planning(
        transcript=transcript,
        episode_title="EP05",
        project_id="ep05",
        client_id="ramair",
        visual_system="parlayvu_interview",
        assets_dir=str(PROJECT / "assets"),
        cameras=CAMERAS,
        show_notes=show_notes,
    )

    if result.get("error"):
        raise SystemExit(f"Planning failed: {result['error']}")

    plan = result.get("video_plan") or {}
    scenes = plan.get("scenes", [])
    if not scenes:
        raise SystemExit("Planning produced no scenes")

    (planning / "video_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    seg = result.get("segment_analysis")
    if seg:
        (planning / "segment_analysis.json").write_text(json.dumps(seg, indent=2), encoding="utf-8")

    layouts = [s.get("layout") for s in scenes]
    print(f"OK: {len(scenes)} scenes written to {planning / 'video_plan.json'}")
    print("   layouts:", ", ".join(layouts))


if __name__ == "__main__":
    asyncio.run(main())
