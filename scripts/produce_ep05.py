"""End-to-end Podcast Parlay run for RamAir Ep05 — drives the real Nathan tools:
init -> plan (AI) -> draft (real FFmpeg render) -> request approval -> status.

This exercises the whole automated system on real assets. The render runs as a
background task inside generate_video_draft; we await it to completion here so a
standalone run actually finishes the video.

Usage:  python scripts/produce_ep05.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root on path

from dotenv import load_dotenv

load_dotenv(override=True)

from app import parlay_state as ps  # noqa: E402
from app.tools import video_parlay_tools as v  # noqa: E402

CLIENT = "ramair"
EPISODE = "Straight_From_The_Hart_Ep05"
CAPTION = "EP05: NEGATIVEAIR INCOMPATIBLE WITH FLEX DUCTS"


def banner(msg: str) -> None:
    print(f"\n{'=' * 70}\n{msg}\n{'=' * 70}", flush=True)


async def main() -> None:
    t0 = time.time()

    banner("STEP 1 — init_podcast_parlay_project")
    init = await v.init_podcast_parlay_project(client_id=CLIENT, episode_slug=EPISODE)
    print(json.dumps(init, indent=2)[:600], flush=True)

    banner("STEP 2 — generate_video_plan (AI cut from transcript)")
    plan = await v.generate_video_plan(
        client_id=CLIENT, episode_slug=EPISODE, episode_caption=CAPTION, show_start="00:22:01",
    )
    print("status:", plan.get("status"), "| scenes:", plan.get("scene_count"), flush=True)
    print("speaker_map:", json.dumps(plan.get("speaker_map", {})), flush=True)
    if plan.get("status") != "planned":
        print("PLAN FAILED:", plan.get("message"), flush=True)
        return

    banner("STEP 3 — generate_video_draft (longform_draft) — real render")
    draft = await v.generate_video_draft(client_id=CLIENT, episode_slug=EPISODE, stage=ps.LONGFORM_DRAFT)
    print("status:", draft.get("status"), "| version:", draft.get("version"), flush=True)
    print("waiting for background render to finish...", flush=True)
    pending = list(v._RENDER_TASKS)
    if pending:
        await asyncio.gather(*pending)
    print(f"render finished after {time.time() - t0:.0f}s total", flush=True)

    banner("STEP 4 — status after render")
    status = await v.get_parlay_status(client_id=CLIENT, episode_slug=EPISODE)
    print("stage:", status.get("stage"), flush=True)
    render_path = None
    for it in reversed(status.get("iterations") or []):
        if it.get("stage") == ps.LONGFORM_DRAFT:
            print("latest draft iteration:", json.dumps(it), flush=True)
            render_path = it.get("preview_path")
            break

    banner("STEP 5 — request_video_approval (longform_draft gate)")
    appr = await v.request_video_approval(
        client_id=CLIENT, episode_slug=EPISODE, stage=ps.LONGFORM_DRAFT,
        preview_path=render_path, summary="Ep05 long-form draft (AI-planned cut) ready for review.",
    )
    print("status:", appr.get("status"), "| approval_id:", (appr.get("approval") or {}).get("id"), flush=True)

    banner("RESULT")
    if render_path:
        f = Path(render_path)
        if not f.is_absolute():
            f = v.REPO_ROOT / render_path
        if f.exists():
            print(f"PRODUCED: {render_path}  ({f.stat().st_size / 1_000_000:.1f} MB)", flush=True)
        else:
            print(f"Expected render at {render_path} but file is missing", flush=True)
    else:
        print("No render path recorded — check the render log above.", flush=True)
    print(f"total elapsed: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
