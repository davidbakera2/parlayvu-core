"""Full render of the CURRENT Ep05 plan (no re-planning), through the real tools:
generate_video_draft (full FFmpeg render) -> status -> request approval.

Use this after the plan/opening is approved so the reviewed cut is rendered as-is.
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


async def main() -> None:
    t0 = time.time()
    print("STEP 1 — generate_video_draft (longform_draft) — full render of current plan", flush=True)
    draft = await v.generate_video_draft(client_id=CLIENT, episode_slug=EPISODE, stage=ps.LONGFORM_DRAFT)
    print("status:", draft.get("status"), "| version:", draft.get("version"), flush=True)
    pending = list(v._RENDER_TASKS)
    if pending:
        await asyncio.gather(*pending)
    print(f"render finished after {time.time() - t0:.0f}s", flush=True)

    status = await v.get_parlay_status(client_id=CLIENT, episode_slug=EPISODE)
    render_path = None
    for it in reversed(status.get("iterations") or []):
        if it.get("stage") == ps.LONGFORM_DRAFT and it.get("status") == "rendered":
            render_path = it.get("preview_path")
            break
    print("stage:", status.get("stage"), "| render_path:", render_path, flush=True)

    appr = await v.request_video_approval(
        client_id=CLIENT, episode_slug=EPISODE, stage=ps.LONGFORM_DRAFT,
        preview_path=render_path, summary="Ep05 long-form draft (full 32-scene cut) ready for review.",
    )
    print("approval:", (appr.get("approval") or {}).get("id"), flush=True)

    if render_path:
        f = Path(render_path)
        if not f.is_absolute():
            f = v.REPO_ROOT / render_path
        if f.exists():
            print(f"PRODUCED: {render_path}  ({f.stat().st_size / 1_000_000:.1f} MB)", flush=True)
        else:
            print(f"Expected render at {render_path} but file is missing", flush=True)
    else:
        print("No rendered path recorded — check for skipped scenes / errors.", flush=True)
    print(f"total elapsed: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
