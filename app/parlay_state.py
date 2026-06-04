"""Authoritative per-episode state machine for the Podcast Parlay.

This is the execution layer that the PODCAST_PARLAY_FULL_WORKFLOW.md spec describes
in prose. The spec is the *policy* (human-readable, git-versioned). This module is
the *state*: one ordered list of stages, an explicit set of allowed transitions, and
a hard guard on the two irreversible publish steps.

Design choices (deliberately lean):
- State lives in ``Project.metadata_json["parlay"]`` — no new table, no Alembic
  migration. Every episode already gets a Project row the first time an approval is
  requested, so there is always somewhere to hang the state.
- The DB is authoritative. We also mirror a plain ``parlay_state.json`` into the
  episode folder so a human can open it in any editor (the "I want to SEE it" need).
- Transitions are validated. Illegal jumps raise. The two publish stages additionally
  require a matching *approved* Approval row — code enforces the gate, never the LLM's
  belief that it was approved.

Stage <-> approval action_type mapping (action_types are produced by
request_video_approval as ``video_<stage>``):
    longform_draft      -> video_longform_draft
    longform_captioned  -> video_longform_captioned
    clips               -> video_clip_package  (special-cased; see ACTION_TYPE_FOR_STAGE)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("parlayvu.parlay_state")


# ── Stage definitions ─────────────────────────────────────────────────────────
# Ordered milestones. "*_in_review" semantics are implicit: a review stage means
# the draft for that stage is out for client approval. changes_requested keeps you
# in the same stage (new version); approved advances you to the next milestone.

INTAKE = "intake"
PLANNING = "planning"
LONGFORM_DRAFT = "longform_draft"
LONGFORM_APPROVED = "longform_approved"
LONGFORM_CAPTIONED = "longform_captioned"
CAPTIONED_APPROVED = "captioned_approved"
LONGFORM_PUBLISHED = "longform_published"
CLIPS = "clips"
CLIPS_APPROVED = "clips_approved"
CLIPS_PUBLISHED = "clips_published"
COMPLETE = "complete"

STAGES: list[str] = [
    INTAKE,
    PLANNING,
    LONGFORM_DRAFT,
    LONGFORM_APPROVED,
    LONGFORM_CAPTIONED,
    CAPTIONED_APPROVED,
    LONGFORM_PUBLISHED,
    CLIPS,
    CLIPS_APPROVED,
    CLIPS_PUBLISHED,
    COMPLETE,
]

STAGE_LABELS: dict[str, str] = {
    INTAKE: "Intake (assets + transcript)",
    PLANNING: "Planning (intro, scenes, music, b-roll)",
    LONGFORM_DRAFT: "Long-form draft — in review",
    LONGFORM_APPROVED: "Long-form draft approved",
    LONGFORM_CAPTIONED: "Captioned long-form — in review",
    CAPTIONED_APPROVED: "Captioned long-form approved",
    LONGFORM_PUBLISHED: "Long-form published (YouTube unlisted)",
    CLIPS: "Clips package — in review",
    CLIPS_APPROVED: "Clips approved",
    CLIPS_PUBLISHED: "Clips published + added to playlist",
    COMPLETE: "Episode complete",
}

# Allowed forward transitions. Review stages loop back to themselves (re-render a new
# version after changes_requested).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    INTAKE: {PLANNING},
    PLANNING: {LONGFORM_DRAFT},
    LONGFORM_DRAFT: {LONGFORM_DRAFT, LONGFORM_APPROVED},
    LONGFORM_APPROVED: {LONGFORM_CAPTIONED},
    LONGFORM_CAPTIONED: {LONGFORM_CAPTIONED, CAPTIONED_APPROVED},
    CAPTIONED_APPROVED: {LONGFORM_PUBLISHED},
    LONGFORM_PUBLISHED: {CLIPS},
    CLIPS: {CLIPS, CLIPS_APPROVED},
    CLIPS_APPROVED: {CLIPS_PUBLISHED},
    CLIPS_PUBLISHED: {COMPLETE},
    COMPLETE: set(),
}

# Stages that are review/iteration loops (each render = a new version, preview link).
REVIEW_STAGES: set[str] = {LONGFORM_DRAFT, LONGFORM_CAPTIONED, CLIPS}

# When a review stage is APPROVED, advance to this milestone.
APPROVED_ADVANCE: dict[str, str] = {
    LONGFORM_DRAFT: LONGFORM_APPROVED,
    LONGFORM_CAPTIONED: CAPTIONED_APPROVED,
    CLIPS: CLIPS_APPROVED,
}

# Irreversible publish stages: entering them REQUIRES an approved approval of the
# given action_type. This is the hard gate — deterministic, not LLM-judged.
PUBLISH_GUARDS: dict[str, str] = {
    LONGFORM_PUBLISHED: "video_longform_captioned",
    CLIPS_PUBLISHED: "video_clip_package",
}

# Map a review stage to the approval action_type it is reviewed under.
ACTION_TYPE_FOR_STAGE: dict[str, str] = {
    LONGFORM_DRAFT: "video_longform_draft",
    LONGFORM_CAPTIONED: "video_longform_captioned",
    CLIPS: "video_clip_package",
}


class ParlayTransitionError(ValueError):
    """Raised when a requested stage transition is not allowed."""


class ParlayPublishNotApproved(PermissionError):
    """Raised when a publish stage is entered without the required approved approval."""


# ── Identity ──────────────────────────────────────────────────────────────────

def parlay_project_id(client_id: str, episode_slug: str) -> str:
    """The single canonical project_id for a parlay episode.

    Everything (state, approvals, events) must agree on this so the visualizer and
    the approval gates look at the same row.
    """
    return f"{client_id}-{episode_slug}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "stage": INTAKE,
        "pending_approval_id": None,
        "history": [],       # [{"to": stage, "by": who, "note": str, "at": iso}]
        "iterations": [],     # [{"version": n, "stage": s, "preview_url": ..., "summary": ..., "status": ..., "at": iso}]
        "updated_at": _now_iso(),
    }


# ── DB access (authoritative) ─────────────────────────────────────────────────

def _db_available() -> bool:
    try:
        from app.database import engine
        return engine is not None
    except Exception:
        return False


def get_state(project_id: str) -> dict[str, Any]:
    """Return the parlay state dict for an episode (default INTAKE if none yet).

    Reads from Project.metadata_json["parlay"]. Raises RuntimeError only if the DB
    is not configured at all — callers that must tolerate that (the standalone
    visualizer) should check _db_available() first.
    """
    from app.database import session_scope
    from app.models import Project

    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            return _default_state()
        return (project.metadata_json or {}).get("parlay") or _default_state()


def _persist(project_id: str, state: dict[str, Any], *, client_id: Optional[str] = None) -> dict[str, Any]:
    """Write state back into Project.metadata_json. Creates the Project row if needed.

    Reassigns metadata_json wholesale so SQLAlchemy detects the change (plain JSON
    columns do not track in-place mutation).
    """
    from app.database import session_scope
    from app.models import Project
    from app.project_memory import ensure_project_context

    state["updated_at"] = _now_iso()
    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            # Derive a client_id if not given: convention is "<client_id>-<slug>".
            cid = client_id or project_id.split("-", 1)[0]
            project = ensure_project_context(
                session,
                client_id=cid,
                project_id=project_id,
                project_name=project_id.replace("-", " ").title(),
            )
        meta = dict(project.metadata_json or {})
        meta["parlay"] = state
        project.metadata_json = meta
        session.flush()
    return state


# ── Transitions ───────────────────────────────────────────────────────────────

def set_stage(
    project_id: str,
    to_stage: str,
    *,
    by: str = "nathan",
    note: Optional[str] = None,
    client_id: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Move the episode to ``to_stage``, validating the transition.

    Raises ParlayTransitionError on an illegal jump (unless force=True).
    Raises ParlayPublishNotApproved if entering a publish stage without the
    required approved approval (force does NOT bypass the publish gate — that is
    the whole point of the gate).
    """
    if to_stage not in STAGES:
        raise ParlayTransitionError(f"Unknown stage: {to_stage!r}")

    state = get_state(project_id)
    current = state.get("stage", INTAKE)

    if not force and to_stage != current and to_stage not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ParlayTransitionError(
            f"Illegal transition {current!r} -> {to_stage!r}. "
            f"Allowed from {current!r}: {sorted(ALLOWED_TRANSITIONS.get(current, set()))}"
        )

    # Publish gate is enforced regardless of force.
    if to_stage in PUBLISH_GUARDS:
        guard_publish(project_id, to_stage)

    state["stage"] = to_stage
    state.setdefault("history", []).append(
        {"to": to_stage, "by": by, "note": note, "at": _now_iso()}
    )
    return _persist(project_id, state, client_id=client_id)


def guard_publish(project_id: str, publish_stage: str) -> dict[str, Any]:
    """Confirm an approved approval exists for the action_type that gates publish_stage.

    Returns the approval dict on success. Raises ParlayPublishNotApproved otherwise.
    """
    required = PUBLISH_GUARDS.get(publish_stage)
    if required is None:
        raise ValueError(f"{publish_stage!r} is not a guarded publish stage")

    from app.approvals import list_approvals

    approvals = list_approvals(project_id=project_id, status="approved")
    for ap in approvals:
        if (ap.get("metadata") or {}).get("action_type") == required:
            return ap
    raise ParlayPublishNotApproved(
        f"Cannot enter {publish_stage!r}: no approved approval of type {required!r} "
        f"for project {project_id!r}. Get the client's approval first."
    )


# ── Iteration tracking (this is what makes the loop VISIBLE) ──────────────────

def record_iteration(
    project_id: str,
    *,
    stage: str,
    preview_url: Optional[str] = None,
    preview_path: Optional[str] = None,
    summary: Optional[str] = None,
    status: str = "in_review",
    client_id: Optional[str] = None,
) -> dict[str, Any]:
    """Append one render/version to the iteration trail and return the full state.

    Each subtitle correction, each b-roll re-time, each scene change produces a new
    render → call this with the new preview link. The version number auto-increments
    within the stage, so you get v1, v2, v3 of the long-form, of the captions, etc.
    """
    state = get_state(project_id)
    iterations = state.setdefault("iterations", [])
    version = 1 + sum(1 for it in iterations if it.get("stage") == stage)
    iterations.append(
        {
            "version": version,
            "stage": stage,
            "preview_url": preview_url,
            "preview_path": preview_path,
            "summary": summary,
            "status": status,
            "at": _now_iso(),
        }
    )
    return _persist(project_id, state, client_id=client_id)


def set_pending_approval(
    project_id: str,
    approval_id: Optional[str],
    *,
    client_id: Optional[str] = None,
) -> dict[str, Any]:
    state = get_state(project_id)
    state["pending_approval_id"] = approval_id
    return _persist(project_id, state, client_id=client_id)


def record_decision(
    project_id: str,
    *,
    stage: str,
    decision: str,
    notes: Optional[str] = None,
    by: str = "client",
    client_id: Optional[str] = None,
) -> dict[str, Any]:
    """Apply a client decision on a review stage and move the state accordingly.

    decision == "approved"            -> advance to the mapped milestone.
    decision == "changes_requested"   -> stay in the same stage; the next render
                                         (record_iteration) becomes the next version.
    Anything else (rejected/cancelled) -> stay; just log it in history.

    This is the hook the Teams approval-decision handler should call after
    decide_approval() returns, so the visible state tracks reality instead of
    being inferred.
    """
    state = get_state(project_id)
    state["pending_approval_id"] = None
    state.setdefault("history", []).append(
        {"to": state.get("stage"), "by": by, "note": f"{decision}: {notes or ''}".strip(), "at": _now_iso()}
    )

    # mark the latest iteration for this stage with the decision
    for it in reversed(state.get("iterations", [])):
        if it.get("stage") == stage:
            it["status"] = decision
            break

    _persist(project_id, state, client_id=client_id)

    if decision == "approved" and stage in APPROVED_ADVANCE:
        return set_stage(
            project_id,
            APPROVED_ADVANCE[stage],
            by=by,
            note=notes,
            client_id=client_id,
        )
    return get_state(project_id)


# ── Status assembly + visualization ───────────────────────────────────────────

def compute_status(project_id: str, project_dir: Optional[Path] = None) -> dict[str, Any]:
    """Combine the authoritative state with live approvals (and on-disk renders) into
    one dict suitable for rendering. This is the single read the visualizer uses.
    """
    state = get_state(project_id)

    pending = None
    latest_preview = None
    try:
        from app.approvals import list_approvals

        all_approvals = list_approvals(project_id=project_id)
        for ap in all_approvals:
            if ap.get("status") == "pending":
                pending = ap
                break
    except Exception as exc:
        logger.debug("approval lookup skipped: %s", exc)

    # Prefer the newest iteration with a preview link.
    for it in reversed(state.get("iterations", [])):
        if it.get("preview_url") or it.get("preview_path"):
            latest_preview = it.get("preview_url") or it.get("preview_path")
            break
    if not latest_preview and pending:
        latest_preview = (pending.get("metadata") or {}).get("preview_url")

    renders: list[str] = []
    if project_dir:
        rdir = Path(project_dir) / "renders"
        if rdir.exists():
            renders = sorted(p.name for p in rdir.glob("**/*.mp4"))

    return {
        "project_id": project_id,
        "stage": state.get("stage", INTAKE),
        "stage_label": STAGE_LABELS.get(state.get("stage", INTAKE), state.get("stage", INTAKE)),
        "pending_approval": pending,
        "latest_preview": latest_preview,
        "iterations": state.get("iterations", []),
        "history": state.get("history", []),
        "renders_on_disk": renders,
        "updated_at": state.get("updated_at"),
    }


def render_mermaid(status: dict[str, Any]) -> str:
    """A flowchart of the whole parlay with the current stage highlighted."""
    current = status.get("stage", INTAKE)
    lines = ["```mermaid", "flowchart TD"]
    # node ids must be mermaid-safe; stage names already are (snake_case)
    for stage in STAGES:
        label = STAGE_LABELS.get(stage, stage).replace('"', "'")
        lines.append(f'    {stage}["{label}"]')
    # edges
    for src, dests in ALLOWED_TRANSITIONS.items():
        for dst in sorted(dests):
            if dst == src:
                lines.append(f"    {src} -->|changes_requested| {src}")
            else:
                lines.append(f"    {src} --> {dst}")
    lines.append("    classDef current fill:#ffeb3b,stroke:#f57f17,stroke-width:3px;")
    lines.append("    classDef publish fill:#e8f5e9,stroke:#2e7d32;")
    lines.append(f"    class {current} current;")
    lines.append(f"    class {LONGFORM_PUBLISHED},{CLIPS_PUBLISHED} publish;")
    lines.append("```")
    return "\n".join(lines)


def render_status_text(status: dict[str, Any]) -> str:
    """Human-readable summary: where we are, the iteration trail with preview links,
    and the open approval gate (if any)."""
    lines = [
        f"Episode: {status['project_id']}",
        f"Current stage: {status['stage']}  ({status['stage_label']})",
        f"Last updated: {status.get('updated_at')}",
        "",
    ]
    pending = status.get("pending_approval")
    if pending:
        meta = pending.get("metadata") or {}
        lines.append(f"OPEN APPROVAL GATE → {meta.get('title') or pending.get('id')}")
        lines.append(f"   approval_id: {pending.get('id')}  status: {pending.get('status')}")
        if status.get("latest_preview"):
            lines.append(f"   preview: {status['latest_preview']}")
        lines.append("")
    elif status.get("latest_preview"):
        lines.append(f"Latest preview: {status['latest_preview']}")
        lines.append("")

    iterations = status.get("iterations", [])
    if iterations:
        lines.append("Iteration trail (each render = one client-reviewable preview):")
        for it in iterations:
            link = it.get("preview_url") or it.get("preview_path") or "(no preview link)"
            lines.append(
                f"  [{it.get('stage')} v{it.get('version')}] {it.get('status')}"
                f" — {it.get('summary') or ''}"
            )
            lines.append(f"        {link}")
        lines.append("")

    if status.get("renders_on_disk"):
        lines.append(f"Renders on disk: {', '.join(status['renders_on_disk'])}")
        lines.append("")

    lines.append("Full workflow spec: video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md")
    return "\n".join(lines)


def mirror_to_disk(project_dir: Path, status: dict[str, Any]) -> Optional[Path]:
    """Write a readable parlay_state.json into the episode folder. Best-effort.

    This is a *mirror* of the authoritative DB state, written so you can open the
    file and see exactly where the episode is without querying anything.
    """
    try:
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        out = project_dir / "parlay_state.json"
        payload = {
            "_note": "READ-ONLY MIRROR of DB state (app/parlay_state.py is authoritative). Do not hand-edit.",
            **status,
        }
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return out
    except Exception as exc:
        logger.warning("parlay_state.json mirror skipped: %s", exc)
        return None
