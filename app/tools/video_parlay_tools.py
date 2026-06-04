"""Video Parlay tools for Nathan.

These give Nathan direct actuation over the Podcast Parlay workflow defined in
video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md.

They follow the exact same patterns as the Dylan website tools:
- Call into video_system/ scripts or (future) Resolve automation.
- Use the core ParlayVU approvals system so that Teams cards, iteration via
  "changes_requested", project memory, and audit all work out of the box.
- Return rich results including preview links/paths and approval_ids.
- Are safe to call from the conversational tool loop (nathan_llm.py).

Current status: Functional stubs + real approval + project scaffolding integration.
Heavy rendering / Resolve calls are delegated to the video_system tools (which
the human can also run directly for now). As the v2 Resolve layer matures, these
stubs will call it more deeply.

See PODCAST_PARLAY_FULL_WORKFLOW.md for the exact stages, approval action_types,
iteration loops, and how Nathan is supposed to use these.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from app import parlay_state as ps
from app.approvals import request_approval
from app.client_config import ClientConfigError, load_client_config
from app.project_memory import record_agent_event

logger = logging.getLogger("parlayvu.tools.video_parlay")

# Anchor paths to the repo root (this file is app/tools/video_parlay_tools.py) so
# they resolve identically no matter what the process CWD is — the container and
# local runs don't always launch from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
VIDEO_SYSTEM_ROOT = REPO_ROOT / "video_system"
PROJECTS_ROOT = VIDEO_SYSTEM_ROOT / "projects"


def _repo_rel(p: Path) -> str:
    """Repo-relative POSIX path string for result payloads. Falls back to the
    absolute path (never raises) if `p` is outside the repo."""
    try:
        return str(Path(p).resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _refresh_state_mirror(client_id: str, episode_slug: str) -> Optional[str]:
    """Recompute status and write the readable parlay_state.json mirror.

    Best-effort: never let a state/DB hiccup break the actual video tool. Returns
    the latest preview link if one is known, so callers can surface it.
    """
    try:
        project_id = ps.parlay_project_id(client_id, episode_slug)
        project_dir = _get_project_dir(client_id, episode_slug)
        status = ps.compute_status(project_id, project_dir=project_dir)
        ps.mirror_to_disk(project_dir, status)
        return status.get("latest_preview")
    except Exception as exc:
        logger.warning("parlay state mirror skipped for %s/%s: %s", client_id, episode_slug, exc)
        return None


def _get_project_dir(client_id: str, episode_slug: str) -> Path:
    """Convention: projects/<ClientTitleCase>/<Show_EpXX> or similar.

    For simplicity we accept a full relative path or construct from client + slug.
    In practice Nathan will pass something like client_id="ramair",
    episode_slug="Straight_From_The_Hart_Ep06".
    """
    # Try direct if it looks like a path
    p = Path(episode_slug)
    if p.is_absolute() or (VIDEO_SYSTEM_ROOT / p).exists():
        return (VIDEO_SYSTEM_ROOT / p).resolve()

    # Common convention
    client_dir = client_id.title().replace("_", " ").replace("-", " ")
    # Try a few common show name patterns; for now just use the slug as the show_ep dir
    candidate = PROJECTS_ROOT / client_dir / episode_slug
    if candidate.exists():
        return candidate.resolve()

    # Fallback: create under a sensible name
    return (PROJECTS_ROOT / client_dir / episode_slug).resolve()


async def init_podcast_parlay_project(
    *,
    client_id: str,
    episode_slug: str,
    show_name: Optional[str] = None,
    raw_assets_note: Optional[str] = None,
) -> dict[str, Any]:
    """Initialize (or ensure) a video project folder for a Podcast Parlay episode.

    Runs the existing new_project scaffolding from video_system if the dir
    does not exist. Drops a small init note into PROJECT_README.md.

    This is the entry point Nathan calls when the user says "kick off the
    Podcast Parlay for the new interview" or similar.
    """
    project_dir = _get_project_dir(client_id, episode_slug)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Run the canonical new_project logic if the dir is basically empty
    assets_dir = project_dir / "assets"
    planning_dir = project_dir / "planning"
    if not assets_dir.exists() or not any(assets_dir.iterdir()):
        logger.info("Scaffolding new video project via new_project | %s", project_dir)
        # Prefer the Python one (cross platform); the .ps1 is Windows convenience
        try:
            subprocess.check_call(
                [
                    "python",
                    str(VIDEO_SYSTEM_ROOT / "tools" / "new_project.py"),
                    "--client",
                    client_id,
                    "--show",
                    show_name or episode_slug.split("_")[0] if "_" in episode_slug else "Podcast",
                    "--episode",
                    episode_slug.split("_")[-1] if "_" in episode_slug else episode_slug,
                ],
                cwd=VIDEO_SYSTEM_ROOT,
            )
        except Exception as exc:
            logger.warning("new_project.py call had issues (may already exist): %s", exc)

    # Ensure basic dirs
    (project_dir / "renders").mkdir(exist_ok=True)
    (project_dir / "previews").mkdir(exist_ok=True)
    planning_dir.mkdir(exist_ok=True)

    readme = project_dir / "PROJECT_README.md"
    if not readme.exists():
        readme.write_text(
            f"# {episode_slug}\n\n"
            "Podcast Parlay episode.\n\n"
            "Follow video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md.\n"
            "Raw assets go in assets/. Planning in planning/. Renders in renders/.\n\n"
            f"Initialized by Nathan for client_id={client_id}.\n",
            encoding="utf-8",
        )
    else:
        # Append a note
        with readme.open("a", encoding="utf-8") as f:
            f.write(f"\n\n[{(raw_assets_note or 'Nathan re-entered the project')}]\n")

    project_id = ps.parlay_project_id(client_id, episode_slug)
    record_agent_event(
        client_id=client_id,
        project_id=project_id,
        agent_name="nathan",
        event_type="video_project_initialized",
        channel="video_parlay",
        summary=f"Podcast Parlay project initialized: {episode_slug}",
        payload={"project_dir": _repo_rel(project_dir)},
    )

    # Seed the authoritative state machine at INTAKE and write the disk mirror.
    try:
        ps.set_stage(project_id, ps.INTAKE, by="nathan", note=raw_assets_note, client_id=client_id, force=True)
        _refresh_state_mirror(client_id, episode_slug)
    except Exception as exc:
        logger.warning("Could not seed parlay state for %s: %s", episode_slug, exc)

    return {
        "status": "initialized",
        "project_dir": _repo_rel(project_dir),
        "episode_slug": episode_slug,
        "client_id": client_id,
        "stage": ps.INTAKE,
        "message": "Project folder ready. Drop host/guest/b-roll assets into assets/ then tell me to generate the first draft plan.",
    }


async def generate_video_draft(
    *,
    client_id: str,
    episode_slug: str,
    stage: str = ps.LONGFORM_DRAFT,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Trigger (or simulate) generation of the next video render for a review stage.

    `stage` must be one of the canonical review stages in app/parlay_state.py:
      - 'longform_draft'      — assembled long-form (cuts + b-roll + music) for review
      - 'longform_captioned'  — captioned long-form for review
      - 'clips'               — the clip package for review
    Each call records a new versioned iteration (v1, v2, ...) for that stage so the
    revision loop is visible, and moves the state machine to that review stage.

    In the current foundation phase this writes a placeholder render marker; as the
    Resolve layer matures it will drive the real render and return a hosted preview.
    """
    if stage not in ps.REVIEW_STAGES:
        raise ValueError(
            f"generate_video_draft stage must be one of {sorted(ps.REVIEW_STAGES)}; got {stage!r}."
        )
    project_dir = _get_project_dir(client_id, episode_slug)

    # Basic validation using existing tools
    plan_json = project_dir / "planning" / "video_plan.json"
    if not plan_json.exists():
        # Try to convert if xlsx is there
        try:
            subprocess.check_call(
                [
                    "python",
                    str(VIDEO_SYSTEM_ROOT / "tools" / "spreadsheet_to_json.py"),
                    str(project_dir),
                ],
                cwd=VIDEO_SYSTEM_ROOT,
            )
        except Exception:
            pass

    # For now: produce a "draft" marker and a fake render path the human can replace
    renders_dir = project_dir / "renders"
    renders_dir.mkdir(exist_ok=True)

    draft_name = f"{stage}_v01.mp4"
    draft_path = renders_dir / draft_name

    # Touch a placeholder so the approval flow has something to point at
    draft_path.write_bytes(b"PLACEHOLDER - run actual Resolve render here\n")
    draft_rel = _repo_rel(draft_path)

    project_id = ps.parlay_project_id(client_id, episode_slug)

    # Record the event
    record_agent_event(
        client_id=client_id,
        project_id=project_id,
        agent_name="nathan",
        event_type="video_draft_generated",
        channel="video_parlay",
        summary=f"Video draft generated for stage {stage}",
        payload={
            "stage": stage,
            "draft_path": draft_rel,
            "notes": notes,
        },
    )

    # No hosted preview yet — this is a local placeholder render. We deliberately
    # do NOT fabricate a file:// "preview_url" that looks clickable in Teams but
    # isn't reachable; the real hosted URL arrives when the Resolve render lands.
    preview_url = None

    # Record this render as a new versioned iteration and move the state machine to
    # the matching review stage. This is what makes each edit loop VISIBLE: every
    # render becomes "[stage vN]" in the status view with its own preview link.
    version = None
    try:
        state = ps.record_iteration(
            project_id,
            stage=stage,
            preview_url=preview_url,
            preview_path=draft_rel,
            summary=notes,
            status="rendered",
            client_id=client_id,
        )
        # latest version number for this stage
        version = max(
            (it["version"] for it in state.get("iterations", []) if it.get("stage") == stage),
            default=None,
        )
        # Move to the review stage. A legal transition (planning→draft, or
        # re-rendering within the same review stage) is the normal path; only
        # fall back to force for an out-of-order jump, which we annotate.
        try:
            ps.set_stage(project_id, stage, by="nathan", note=notes, client_id=client_id)
        except ps.ParlayTransitionError:
            ps.set_stage(project_id, stage, by="nathan", note=f"(out-of-order) {notes or ''}", client_id=client_id, force=True)
        _refresh_state_mirror(client_id, episode_slug)
    except Exception as exc:
        logger.warning("Could not update parlay state on draft for %s: %s", episode_slug, exc)

    return {
        "status": "draft_ready",
        "stage": stage,
        "version": version,
        "episode_slug": episode_slug,
        "client_id": client_id,
        "preview_path": draft_rel,
        "preview_url": preview_url,
        "message": (
            f"Draft for {stage} (v{version}) ready at {draft_rel}. "
            "This is a placeholder marker — in a full run it would be a real Resolve "
            "proxy render with a hosted preview link. Tell me to request client "
            "approval or make changes first."
        ),
    }


async def request_video_approval(
    *,
    client_id: str,
    episode_slug: str,
    stage: str,
    preview_url: Optional[str] = None,
    preview_path: Optional[str] = None,
    summary: Optional[str] = None,
    extra_metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Create a ParlayVU Approval record for a video stage and return it.

    This is the key integration point. It uses the exact same approvals machinery
    as site deploys and meeting notes, so:
    - It appears in /approvals
    - Teams cards can be posted (extend build_*_approval_card for video kinds)
    - "changes_requested" + decision_notes drive the revision loops described
      in PODCAST_PARLAY_FULL_WORKFLOW.md
    - Everything is tied to the client/project for memory and audit.

    `stage` must be a canonical review stage: 'longform_draft', 'longform_captioned',
    or 'clips' (see app/parlay_state.py). The approval's action_type is derived from
    the stage via ps.ACTION_TYPE_FOR_STAGE so the publish gates match deterministically
    (notably 'clips' -> 'video_clip_package', NOT 'video_clips').
    """
    if stage not in ps.ACTION_TYPE_FOR_STAGE:
        raise ValueError(
            f"request_video_approval stage must be one of {sorted(ps.ACTION_TYPE_FOR_STAGE)}; got {stage!r}."
        )
    action_type = ps.ACTION_TYPE_FOR_STAGE[stage]

    try:
        config = load_client_config(client_id)
        display = config.display_name
    except ClientConfigError:
        display = client_id

    project_id = ps.parlay_project_id(client_id, episode_slug)
    project_name = f"{display} — {episode_slug}"

    approval = request_approval(
        client_id=client_id,
        project_id=project_id,
        project_name=project_name,
        requested_by_agent="nathan",  # or "alex" / "video_parlay"
        action_type=action_type,
        title=f"Review {stage.replace('_', ' ')} for {episode_slug}",
        summary=summary or f"Video draft ready for review. Preview: {preview_url or preview_path or '(see files)'}",
        metadata={
            "kind": action_type,
            "episode_slug": episode_slug,
            "stage": stage,
            "preview_url": preview_url,
            "preview_path": preview_path,
            "project_dir": _repo_rel(_get_project_dir(client_id, episode_slug)),
            **(extra_metadata or {}),
        },
    )

    record_agent_event(
        client_id=client_id,
        project_id=project_id,
        agent_name="nathan",
        event_type="video_approval_requested",
        channel="video_parlay",
        summary=f"Approval requested for {stage}",
        payload={"approval_id": approval["id"], "stage": stage, "action_type": action_type},
    )

    # Mark the open approval gate on the state machine so the status view shows
    # "client is reviewing X right now" with the preview link.
    try:
        ps.set_pending_approval(project_id, approval["id"], client_id=client_id)
        _refresh_state_mirror(client_id, episode_slug)
    except Exception as exc:
        logger.warning("Could not set pending approval on parlay state for %s: %s", episode_slug, exc)

    return {
        "status": "approval_requested",
        "approval": approval,
        "stage": stage,
        "message": (
            f"Approval {approval['id']} created for {stage}. "
            "A Teams card (once the video card builder is wired) will let the client Approve / Request Changes. "
            "Feedback will come back as decision_notes and we loop per the Podcast Parlay workflow."
        ),
    }


async def record_parlay_decision(
    *,
    client_id: str,
    episode_slug: str,
    stage: str,
    decision: str,
    notes: Optional[str] = None,
    by: str = "client",
) -> dict[str, Any]:
    """Apply a client's approval decision to the state machine (the loop hook).

    Call this after decide_approval() resolves a video approval (from the Teams card
    handler, or when the client gives feedback in chat):

      - decision="changes_requested" → stays in the same stage. The next
        generate_video_draft becomes the next version (v2, v3 ...) with a fresh
        preview link. This is exactly the subtitles / b-roll / scene-change loop.
      - decision="approved" → advances to the next milestone. If that milestone is a
        publish step, the state machine HARD-REQUIRES the matching approved approval
        (it cannot be entered on the LLM's say-so).

    Returns the updated state + the latest known preview link.
    """
    project_id = ps.parlay_project_id(client_id, episode_slug)
    try:
        state = ps.record_decision(
            project_id,
            stage=stage,
            decision=decision,
            notes=notes,
            by=by,
            client_id=client_id,
        )
    except ps.ParlayPublishNotApproved as exc:
        return {"status": "blocked", "reason": str(exc), "stage": stage}

    latest_preview = _refresh_state_mirror(client_id, episode_slug)

    record_agent_event(
        client_id=client_id,
        project_id=project_id,
        agent_name="nathan",
        event_type="video_decision_recorded",
        channel="video_parlay",
        summary=f"{decision} on {stage}",
        payload={"stage": stage, "decision": decision, "new_stage": state.get("stage")},
    )

    return {
        "status": "decision_recorded",
        "decision": decision,
        "stage": stage,
        "new_stage": state.get("stage"),
        "latest_preview": latest_preview,
        "message": (
            f"Recorded '{decision}' on {stage}. Episode is now at '{state.get('stage')}'. "
            + (
                "Re-render the next version and request approval again."
                if decision == "changes_requested"
                else "Cleared to proceed to the next stage."
            )
        ),
    }


async def get_parlay_status(
    *,
    client_id: str,
    episode_slug: str,
) -> dict[str, Any]:
    """Return the live status of an episode: current stage, iteration trail with
    preview links, and any open approval gate. Nathan calls this for "where is Ep06?"
    """
    project_id = ps.parlay_project_id(client_id, episode_slug)
    project_dir = _get_project_dir(client_id, episode_slug)
    status = ps.compute_status(project_id, project_dir=project_dir)
    ps.mirror_to_disk(project_dir, status)
    return {
        "status": "ok",
        "stage": status.get("stage"),
        "stage_label": status.get("stage_label"),
        "latest_preview": status.get("latest_preview"),
        "pending_approval": status.get("pending_approval"),
        "iterations": status.get("iterations"),
        "mermaid": ps.render_mermaid(status),
        "text": ps.render_status_text(status),
    }


# Convenience helper Nathan (or a future /video endpoint) can call for the common "first draft ready" moment.
async def create_longform_draft_and_request_approval(
    *,
    client_id: str,
    episode_slug: str,
    preview_url: Optional[str] = None,
    preview_path: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """High-level helper: render the long-form draft then immediately request the
    long-form draft approval gate. Prefer explicit stage calls for anything beyond
    this first-draft convenience.
    """
    draft = await generate_video_draft(
        client_id=client_id,
        episode_slug=episode_slug,
        stage=ps.LONGFORM_DRAFT,
        notes=notes,
    )
    approval = await request_video_approval(
        client_id=client_id,
        episode_slug=episode_slug,
        stage=ps.LONGFORM_DRAFT,
        preview_url=preview_url or draft.get("preview_url"),
        preview_path=preview_path or draft.get("preview_path"),
        summary=notes or "Long-form draft ready for review.",
    )
    return {**draft, **approval, "combined": True}
