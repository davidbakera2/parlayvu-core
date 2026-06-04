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
import shutil
import subprocess
import sys
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
RENDER_SCRIPT = VIDEO_SYSTEM_ROOT / "tools" / "render_video.py"
SPREADSHEET_TO_JSON = VIDEO_SYSTEM_ROOT / "tools" / "spreadsheet_to_json.py"

# Strong references to in-flight background render tasks so the event loop does
# not garbage-collect them mid-run.
_RENDER_TASKS: "set[asyncio.Task]" = set()


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


def _ensure_plan_json(project_dir: Path) -> bool:
    """Make sure planning/video_plan.json exists, converting from the .xlsx via
    spreadsheet_to_json.py if needed. Returns True if a plan json is present."""
    plan_json = project_dir / "planning" / "video_plan.json"
    if plan_json.exists():
        return True
    xlsx = project_dir / "planning" / "video_plan.xlsx"
    if not xlsx.exists():
        return False
    try:
        subprocess.check_call(
            [sys.executable, str(SPREADSHEET_TO_JSON), str(project_dir)],
            cwd=str(VIDEO_SYSTEM_ROOT),
        )
    except Exception as exc:
        logger.warning("spreadsheet_to_json failed for %s: %s", project_dir, exc)
    return plan_json.exists()


def _safe_update_iteration(project_id: str, stage: str, version: int, *, client_id: str, **fields: Any) -> None:
    try:
        ps.update_iteration(project_id, stage=stage, version=version, client_id=client_id, **fields)
    except Exception as exc:
        logger.warning("Could not update iteration %s %s v%s: %s", project_id, stage, version, exc)


def _safe_event(client_id: str, project_id: str, event_type: str, summary: str, payload: dict[str, Any]) -> None:
    try:
        record_agent_event(
            client_id=client_id,
            project_id=project_id,
            agent_name="nathan",
            event_type=event_type,
            channel="video_parlay",
            summary=summary,
            payload=payload,
        )
    except Exception as exc:
        logger.warning("Could not record event %s for %s: %s", event_type, project_id, exc)


async def _run_render_job(
    *,
    client_id: str,
    episode_slug: str,
    project_id: str,
    project_dir: Path,
    stage: str,
    version: int,
    with_subtitles: bool,
    max_scenes: Optional[int],
) -> None:
    """Run render_video.py as a subprocess, then flip the iteration to rendered
    (or render_failed) and attach the produced file. Self-contained + defensive:
    this runs detached from the request, so it must never raise to the loop."""
    cmd = [sys.executable, str(RENDER_SCRIPT), str(project_dir)]
    if with_subtitles:
        cmd.append("--with-subtitles")
    if max_scenes:
        cmd += ["--max-scenes", str(max_scenes)]
    logger.info("Render job start | %s/%s stage=%s v%s", client_id, episode_slug, stage, version)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(VIDEO_SYSTEM_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _out, err = await proc.communicate()
        if proc.returncode != 0:
            tail = (err or b"").decode("utf-8", "replace")[-1000:]
            logger.error("Render job failed | %s rc=%s\n%s", episode_slug, proc.returncode, tail)
            _safe_update_iteration(project_id, stage, version, status="render_failed", client_id=client_id)
            _safe_event(client_id, project_id, "video_render_failed",
                        f"Render failed for {stage} v{version}",
                        {"stage": stage, "version": version, "returncode": proc.returncode, "error_tail": tail})
            _refresh_state_mirror(client_id, episode_slug)
            return

        # render_video.py writes renders/final_no_subtitles.mp4 (+ final_with_subtitles.mp4
        # when --with-subtitles and captions exist). Prefer the subtitled output.
        renders_dir = project_dir / "renders"
        candidates = []
        if with_subtitles:
            candidates.append(renders_dir / "final_with_subtitles.mp4")
        candidates.append(renders_dir / "final_no_subtitles.mp4")
        produced = next((c for c in candidates if c.exists()), None)
        if produced is None:
            logger.error("Render job produced no output file | %s %s", episode_slug, [str(c) for c in candidates])
            _safe_update_iteration(project_id, stage, version, status="render_failed", client_id=client_id)
            _safe_event(client_id, project_id, "video_render_failed",
                        f"Render produced no output for {stage} v{version}",
                        {"stage": stage, "version": version})
            _refresh_state_mirror(client_id, episode_slug)
            return

        # Snapshot to a versioned filename so the iteration trail keeps each render.
        versioned = renders_dir / f"{stage}_v{version:02d}.mp4"
        try:
            shutil.copy2(produced, versioned)
            render_rel = _repo_rel(versioned)
        except OSError as exc:
            logger.warning("Could not version render (%s); using raw output", exc)
            render_rel = _repo_rel(produced)

        _safe_update_iteration(project_id, stage, version, status="rendered",
                               preview_path=render_rel, client_id=client_id)
        _safe_event(client_id, project_id, "video_render_complete",
                    f"Render complete for {stage} v{version}",
                    {"stage": stage, "version": version, "render_path": render_rel})
        _refresh_state_mirror(client_id, episode_slug)
        logger.info("Render job done | %s/%s stage=%s v%s -> %s", client_id, episode_slug, stage, version, render_rel)
    except Exception:
        logger.exception("Render job crashed | %s/%s stage=%s v%s", client_id, episode_slug, stage, version)
        _safe_update_iteration(project_id, stage, version, status="render_failed", client_id=client_id)
        _refresh_state_mirror(client_id, episode_slug)


def _launch_render_job(**kwargs: Any) -> None:
    """Schedule a render as a background task on the running event loop.

    A full render is minutes long and must not block Nathan's tool call, so we
    fire-and-forget and let the iteration status report progress. NOTE (v1
    limitation): this is in-process and not durable across a container restart —
    acceptable for the current single-replica deploy; a durable job queue/worker
    is a later step. If there's no running loop (a sync script/test), run inline.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        asyncio.run(_run_render_job(**kwargs))
        return
    task = loop.create_task(_run_render_job(**kwargs))
    _RENDER_TASKS.add(task)
    task.add_done_callback(_RENDER_TASKS.discard)


async def generate_video_draft(
    *,
    client_id: str,
    episode_slug: str,
    stage: str = ps.LONGFORM_DRAFT,
    notes: Optional[str] = None,
    max_scenes: Optional[int] = None,
) -> dict[str, Any]:
    """Render the next version of a review stage and track it as an iteration.

    `stage` must be one of the canonical review stages in app/parlay_state.py:
      - 'longform_draft'      — assembled long-form (cuts + b-roll + music), no captions
      - 'longform_captioned'  — captioned long-form (burns planning/captions.srt)
      - 'clips'               — the clip package (not yet wired to a renderer)

    For the long-form stages this drives the real FFmpeg compositor
    (video_system/tools/render_video.py) against the episode's video_plan.json.
    Rendering runs as a BACKGROUND job (minutes long), so this returns
    immediately with status="rendering"; the iteration flips to "rendered" (with
    the produced file as its preview) when the job finishes. Poll get_parlay_status.
    `max_scenes` renders only the first N scenes — useful for a fast proxy/smoke render.
    """
    if stage not in ps.REVIEW_STAGES:
        raise ValueError(
            f"generate_video_draft stage must be one of {sorted(ps.REVIEW_STAGES)}; got {stage!r}."
        )
    project_dir = _get_project_dir(client_id, episode_slug)
    project_id = ps.parlay_project_id(client_id, episode_slug)

    def _record_and_advance(*, status: str, preview_path: Optional[str] = None) -> Optional[int]:
        """Append the iteration + move the state machine to this review stage.
        Returns the new version number for this stage (or None on failure)."""
        try:
            state = ps.record_iteration(
                project_id, stage=stage, status=status, preview_path=preview_path,
                summary=notes, client_id=client_id,
            )
            version = max(
                (it["version"] for it in state.get("iterations", []) if it.get("stage") == stage),
                default=None,
            )
            try:
                ps.set_stage(project_id, stage, by="nathan", note=notes, client_id=client_id)
            except ps.ParlayTransitionError:
                ps.set_stage(project_id, stage, by="nathan", note=f"(out-of-order) {notes or ''}",
                             client_id=client_id, force=True)
            _refresh_state_mirror(client_id, episode_slug)
            return version
        except Exception as exc:
            logger.warning("Could not update parlay state on draft for %s: %s", episode_slug, exc)
            return None

    # The clip package isn't producible by the long-form FFmpeg renderer yet.
    # Be honest: track the stage, but don't fake a render.
    if stage == ps.CLIPS:
        version = _record_and_advance(status="planned")
        return {
            "status": "not_rendered",
            "stage": stage,
            "version": version,
            "episode_slug": episode_slug,
            "client_id": client_id,
            "message": (
                "Clip rendering isn't wired to a renderer yet — render_video.py produces the "
                "long-form, not clips. The episode is marked at the clips stage; clip generation "
                "is a separate build. Want me to plan the clip moments in the meantime?"
            ),
        }

    # Long-form stages: ensure we have a plan to render from.
    if not _ensure_plan_json(project_dir):
        return {
            "status": "error",
            "stage": stage,
            "episode_slug": episode_slug,
            "client_id": client_id,
            "message": (
                f"No planning/video_plan.json for {episode_slug} (and no video_plan.xlsx to convert "
                "from). Plan the episode first, then I can render."
            ),
        }

    # Captioned stage burns planning/captions.srt; only request subtitles if present.
    captions_present = (project_dir / "planning" / "captions.srt").exists()
    with_subtitles = stage == ps.LONGFORM_CAPTIONED and captions_present

    version = _record_and_advance(status="rendering")
    if version is None:
        return {
            "status": "error",
            "stage": stage,
            "episode_slug": episode_slug,
            "client_id": client_id,
            "message": "Could not record the render iteration (state machine / DB issue). Render not started.",
        }

    _safe_event(client_id, project_id, "video_render_started",
                f"Render started for {stage} v{version}",
                {"stage": stage, "version": version, "with_subtitles": with_subtitles, "max_scenes": max_scenes})

    _launch_render_job(
        client_id=client_id,
        episode_slug=episode_slug,
        project_id=project_id,
        project_dir=project_dir,
        stage=stage,
        version=version,
        with_subtitles=with_subtitles,
        max_scenes=max_scenes,
    )

    caption_note = ""
    if stage == ps.LONGFORM_CAPTIONED and not captions_present:
        caption_note = " (no planning/captions.srt found — rendering without burned captions)"

    return {
        "status": "rendering",
        "stage": stage,
        "version": version,
        "episode_slug": episode_slug,
        "client_id": client_id,
        "preview_url": None,
        "message": (
            f"Render started for {stage} v{version}{caption_note}. It runs in the background "
            "(a few minutes for a full episode). I'll have the preview when it finishes — ask me "
            "for the status, or I'll request approval once it's rendered."
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
