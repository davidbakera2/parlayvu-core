#!/usr/bin/env python3
"""Live status view for a Podcast Parlay episode.

This is the "I want to SEE where the episode is" tool. It reads the AUTHORITATIVE
state machine (app/parlay_state.py — backed by the DB), and prints:
  - the current stage, highlighted on the full workflow Mermaid diagram
  - the iteration trail (every render = one client-reviewable preview link)
  - the open approval gate, if the client is currently reviewing something

Usage (from the repo root, so the `app` package imports cleanly):

    python video_system/tools/visualize_parlay_status.py \
        projects/RamAir/Straight_From_The_Hart_Ep06 --project-id ramair-Straight_From_The_Hart_Ep06

    # or let it derive the project_id from --client + the folder name:
    python video_system/tools/visualize_parlay_status.py \
        projects/RamAir/Straight_From_The_Hart_Ep06 --client ramair

If no DATABASE_URL is configured (or the app package can't be imported), it falls
back to a rough stage guess from the files on disk so the tool still runs offline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the repo root importable no matter where we're invoked from.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _derive_project_id(project_dir: Path, explicit: str | None, client: str | None) -> str | None:
    if explicit:
        return explicit
    if client:
        # Convention: project_id == "<client_id>-<episode_slug>"; folder name is the slug.
        return f"{client}-{project_dir.name}"
    return None


def visualize_from_db(project_id: str, project_dir: Path) -> str | None:
    """Return the rich DB-backed view, or None if state can't be read."""
    try:
        from app import parlay_state as ps
    except Exception as exc:  # import failure -> caller falls back to file mode
        print(f"[info] DB-backed view unavailable ({exc}); falling back to file inference.", file=sys.stderr)
        return None

    if not ps._db_available():
        print("[info] DATABASE_URL not configured; falling back to file inference.", file=sys.stderr)
        return None

    try:
        status = ps.compute_status(project_id, project_dir=project_dir)
        mirror = ps.mirror_to_disk(project_dir, status)
        text = ps.render_status_text(status)
        mermaid = ps.render_mermaid(status)
        footer = f"\n(mirror written to {mirror})" if mirror else ""
        return f"{text}\n\n{mermaid}{footer}"
    except Exception as exc:
        print(f"[info] couldn't read DB state ({exc}); falling back to file inference.", file=sys.stderr)
        return None


def visualize_from_files(project_dir: Path) -> str:
    """Offline fallback: rough stage guess from folder contents. Clearly labelled as a
    guess — the DB-backed view above is the source of truth when available."""
    project_dir = project_dir.resolve()
    slug = project_dir.name

    has_assets = (project_dir / "assets").exists() and any((project_dir / "assets").iterdir())
    has_plan = (project_dir / "planning" / "video_plan.json").exists()
    renders = list((project_dir / "renders").glob("**/*.mp4")) if (project_dir / "renders").exists() else []
    has_draft = any("draft" in r.name.lower() for r in renders)
    has_captioned = any("caption" in r.name.lower() for r in renders)

    if has_captioned:
        stage = "longform_captioned"
    elif has_draft:
        stage = "longform_draft"
    elif has_plan:
        stage = "planning"
    elif has_assets:
        stage = "intake"
    else:
        stage = "intake"

    try:
        from app import parlay_state as ps

        status = {"stage": stage}
        mermaid = ps.render_mermaid(status)
    except Exception:
        mermaid = "(install deps / run from repo root to render the Mermaid diagram)"

    summary = [
        "[FILE-INFERENCE MODE — this is a GUESS from files, not the authoritative state]",
        f"Project: {slug}",
        f"Guessed stage: {stage}",
        f"Assets present: {has_assets}",
        f"Plan present: {has_plan}",
        f"Renders found: {len(renders)}",
        "",
        "For the real state (iterations, preview links, open approvals), run with",
        "--project-id <client-slug> against a configured DATABASE_URL.",
        "",
        "Full workflow spec: video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md",
    ]
    return "\n".join(summary) + "\n\n" + mermaid


def main() -> None:
    parser = argparse.ArgumentParser(description="Show the live status of a Podcast Parlay episode.")
    parser.add_argument("project_dir", help="Path to the episode folder, e.g. projects/RamAir/Straight_From_The_Hart_Ep06")
    parser.add_argument("--project-id", help="Authoritative project_id (e.g. ramair-Straight_From_The_Hart_Ep06).")
    parser.add_argument("--client", help="client_id, used with the folder name to derive the project_id.")
    args = parser.parse_args()

    p = Path(args.project_dir)
    if not p.exists():
        p = Path("video_system") / args.project_dir

    project_id = _derive_project_id(p, args.project_id, args.client)

    out = None
    if project_id:
        out = visualize_from_db(project_id, p)
    else:
        print("[info] no --project-id/--client given; using file inference.", file=sys.stderr)

    print(out if out is not None else visualize_from_files(p))


if __name__ == "__main__":
    main()
