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
import json
import logging
import os
import re
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

# --- Planner (transcript -> video_plan.json) -----------------------------------
PLAN_MODEL = "claude-sonnet-4-6"
PLAN_MAX_TOKENS = 8000
PLAN_TRANSCRIPT_CAP = 150_000   # chars of transcript fed to the planner (full-episode transcripts run large)
PLAN_BRIEF_CAP = 6_000

# Interview camera angles (role -> conventional source filename).
_ROLE_FILES = {"host": "host.mp4", "guest_01": "guest_01.mp4", "guest_02": "guest_02.mp4"}
# Branding/system assets identified by FILENAME STEM (extension-agnostic, so the
# corrected show_image.jpg / background.mov / music.mp3 are recognized too). These
# are never footage or b-roll. stem -> asset role.
_BRANDING_STEMS = {
    "intro": "intro",
    "show_image": "show_image",
    "show_image_lower_third": "show_image_lower_third",
    "logo_square": "logo_square",
    "music": "music",
    "background": "background",  # full-frame background layer, not foreground b-roll
}
_VALID_LAYOUTS = {"1cam", "2cam", "2cam_broll", "3cam", "3cam_broll"}
_LAYOUT_ROLE_COUNT = {"1cam": 1, "2cam": 2, "2cam_broll": 2, "3cam": 3, "3cam_broll": 3}
# B-roll must be VISUAL — a video or image. Audio files (music.wav/.mp3) are never
# b-roll; feeding one to a *_broll layout makes ffmpeg fail ([N:v] matches no streams).
_BROLL_EXT = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff",
}


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


def _find_transcript(planning_dir: Path, explicit: Optional[str]) -> Optional[Path]:
    """Locate the transcript to plan from. Prefers an explicit path, then the
    largest speaker-labeled .txt (Riverside export), then the largest .srt/.vtt."""
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = planning_dir / explicit
        return p if p.exists() else None
    if not planning_dir.exists():
        return None
    txts = [t for t in planning_dir.glob("*.txt") if "caption" not in t.name.lower()]
    if txts:
        return max(txts, key=lambda p: p.stat().st_size)
    for ext in ("*.srt", "*.vtt"):
        files = list(planning_dir.glob(ext))
        if files:
            return max(files, key=lambda p: p.stat().st_size)
    return None


def _load_brief(client_id: str, *, cap: int = PLAN_BRIEF_CAP) -> str:
    """Best-effort read of the client's 00_Client_Brief markdown for names,
    titles, topic framing, and brand voice. Empty string if none."""
    base = REPO_ROOT / "client_artifacts" / client_id / "00_Client_Brief"
    if not base.exists():
        return ""
    parts = []
    for md in sorted(base.glob("*.md")):
        try:
            parts.append(md.read_text(encoding="utf-8"))
        except OSError:
            continue
    return "\n\n".join(parts)[:cap]


def _classify_assets(project_dir: Path) -> dict[str, Any]:
    """Sort the project's media into cameras / branding / b-roll (by stem + ext)."""
    assets_dir = project_dir / "assets"
    present = sorted(p.name for p in assets_dir.glob("*") if p.is_file()) if assets_dir.exists() else []
    cameras = [n for n in present if n in _ROLE_FILES.values()]
    branding = {n: _BRANDING_STEMS[Path(n).stem.lower()] for n in present if Path(n).stem.lower() in _BRANDING_STEMS}
    broll = [
        n for n in present
        if Path(n).suffix.lower() in _BROLL_EXT and n not in cameras and n not in branding
    ]
    return {"present": present, "cameras": cameras, "branding": branding, "broll": broll}


def _pick_asset(branding: dict[str, str], key: str, ext_pref: tuple[str, ...]) -> str:
    """Pick the branding file for `key`, preferring the given extensions in order
    (so the new show_image.jpg wins over a stale show_image.png)."""
    files = [name for name, k in branding.items() if k == key]
    for ext in ext_pref:
        for f in files:
            if Path(f).suffix.lower() == ext:
                return f
    return sorted(files)[0] if files else ""


def _tc_to_secs(value: str) -> float:
    """Parse 'HH:MM:SS.mmm' / 'MM:SS.mmm' / 'SS' (minutes may exceed 59) to seconds."""
    value = (value or "").strip().replace(",", ".")
    if not value:
        return 0.0
    parts = value.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return 0.0
    secs = 0.0
    for n in nums:
        secs = secs * 60 + n
    return secs


def _trim_transcript_to_show(text: str, show_start_secs: float) -> str:
    """Drop pre-show chatter: return the transcript from the first speaker header
    whose timestamp is at/after `show_start_secs`. Headers look like
    'Speaker Name (MM:SS.mmm)' where minutes may exceed 59. No-op if none match."""
    header = re.compile(r'^.*?\((\d+):(\d+(?:\.\d+)?)\)\s*$', re.M)
    for m in header.finditer(text):
        secs = int(m.group(1)) * 60 + float(m.group(2))
        if secs >= show_start_secs:
            return text[m.start():]
    return text


def _strip_json_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


async def _draft_scenes_with_llm(
    *,
    episode_caption: str,
    transcript: str,
    brief: str,
    assets: dict[str, Any],
    speaker_map: Optional[dict[str, str]],
    notes: Optional[str],
    show_start: Optional[str] = None,
) -> dict[str, Any]:
    """Ask Sonnet to segment the transcript into a scene plan. Returns the parsed
    JSON {speaker_map, scenes:[...]}. Raises RuntimeError if the API key is absent."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required to draft a video plan")

    broll_ids = [Path(b).stem for b in assets.get("broll", [])]
    roles_available = [r for r, f in _ROLE_FILES.items() if f in assets.get("cameras", [])] or ["host"]

    fixed_map = json.dumps(speaker_map) if speaker_map else "null"
    show_start_block = ""
    if show_start:
        show_start_block = (
            f"\nSHOW START: The actual episode begins at {show_start} (the host's "
            "\"Welcome to Straight From the Hart\"). EVERYTHING BEFORE THAT is pre-show "
            "setup/chatter (mic checks, \"can you hear me\", waiting) — IGNORE it completely. "
            f"Your FIRST scene must start at {show_start}.\n"
        )
    prompt = f"""You are Alex, ParlayVU's video editor, drafting the scene-by-scene plan for an
interview episode. You turn a speaker-labeled transcript into a structured cut.

EPISODE CAPTION (use verbatim as every scene's bottom_row_text): {episode_caption}

CAMERA ROLES available (you may place these on screen): {roles_available}
B-ROLL available (reference by broll_id = these exact ids, else leave ""): {broll_ids}
PROVIDED SPEAKER MAP (use as-is if not null): {fixed_map}
{show_start_block}
CLIENT BRIEF (for correct names, titles, topic, brand voice):
{brief or "(none provided)"}

TRANSCRIPT (speaker-labeled; timestamps look like "Name (MM:SS.mmm)" and are ABSOLUTE
recording times — minutes may exceed 59, e.g. "(63:12.450)" = 1:03:12.450. These are the
exact positions in the camera footage, so use them directly as scene start/end):
{transcript}

TASK: Output ONE JSON object, nothing else:
{{
  "speaker_map": {{"<transcript speaker name>": "host" | "guest_01" | "guest_02", ...}},
  "scenes": [
    {{
      "scene_id": "S001",
      "layout": "1cam" | "2cam" | "2cam_broll" | "3cam" | "3cam_broll",
      "start": "HH:MM:SS.mmm",
      "end": "HH:MM:SS.mmm",
      "primary_camera": "host" | "guest_01" | "guest_02",
      "active_roles": ["host", "guest_01"],
      "top_row_text": "NAME | TITLE",
      "topic_heading": "SHORT SUBJECT HEADING FOR WHAT IS BEING DISCUSSED",
      "broll_id": "",
      "notes": "why this scene/layout"
    }}
  ]
}}

RULES:
- speaker_map: the show host/interviewer is "host"; map remaining speakers to
  "guest_01" then "guest_02" in order of first appearance. Honor the provided map if given.
- Segment by topic/turn into scenes of roughly 20s-120s, covering the whole show
  through to the end of the transcript. Use the transcript timestamps for start/end,
  output as "HH:MM:SS.mmm" (convert the transcript's MINUTES:SECONDS, where minutes
  may exceed 59 — e.g. transcript (63:12.450) -> "01:03:12.450"). Scenes must be
  sequential and non-overlapping, and never start before the SHOW START.
- layout: "1cam" when one person holds the floor (monologue/cold open);
  "2cam" for two-person dialogue; "3cam" when all three are engaged. Use the
  "*_broll" variants only when a listed broll_id genuinely illustrates the moment.
- active_roles must match the layout: 1 role for 1cam, 2 for 2cam*, 3 for 3cam*.
  primary_camera must be one of active_roles (the dominant speaker).
- Only use roles present in CAMERA ROLES available.
- top_row_text: the on-screen lower third for the primary speaker, "NAME | TITLE"
  in the brand's style. Pull real names/titles from the brief/transcript.
- topic_heading: the LOWER-BOTTOM subject line — a short, punchy heading (≈3-7
  words) describing what is being discussed in this scene. Keep the SAME heading
  across consecutive scenes on the same topic, and CHANGE it when the discussion
  moves to a new subject (typically every few minutes). This is what the viewer
  reads to know "what are they talking about right now", so make it specific and
  benefit/insight-oriented, not generic.
- broll_id: only a value from B-ROLL available, otherwise "".
{f"- Director note to honor: {notes}" if notes else ""}
Output ONLY the JSON object."""

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=PLAN_MODEL,
        max_tokens=PLAN_MAX_TOKENS,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(b.text for b in response.content if hasattr(b, "text"))
    data = json.loads(_strip_json_fence(raw))
    if not isinstance(data, dict) or "scenes" not in data:
        raise ValueError("Planner did not return the expected {speaker_map, scenes} JSON")
    return data


def _coerce_roles(layout: str, primary: str, active: list[str]) -> tuple[str, list[str]]:
    """Reconcile active_roles with what the layout requires so the renderer
    (which enforces exact camera counts for 2cam/3cam) won't reject the scene."""
    order = ["host", "guest_01", "guest_02"]
    active = [r for r in active if r in _ROLE_FILES] or ([primary] if primary in _ROLE_FILES else ["host"])
    if primary not in active:
        primary = active[0]
    need = _LAYOUT_ROLE_COUNT.get(layout, len(active))
    if len(active) > need:
        # keep primary + fill toward the needed count, preserving order
        kept = [primary] + [r for r in order if r in active and r != primary]
        active = kept[:need]
    elif len(active) < need:
        for r in order:
            if r not in active:
                active.append(r)
            if len(active) >= need:
                break
        active = active[:need]
    return primary, active


def _assemble_video_plan(
    episode_slug: str,
    episode_caption: str,
    llm_out: dict[str, Any],
    assets: dict[str, Any],
    lower_thirds: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Turn the LLM's {speaker_map, scenes} into the full video_plan.json the
    FFmpeg renderer consumes (scenes + broll + assets + settings).

    `lower_thirds` (role -> "Name | Title") overrides the top lower third per
    speaker — the authoritative source for guest titles the LLM can't know.
    Each scene's bottom lower third is the LLM's per-scene topic_heading (so it
    changes with the discussion), falling back to the episode caption.
    """
    lower_thirds = lower_thirds or {}
    broll_by_stem = {Path(b).stem: b for b in assets.get("broll", [])}

    scenes: list[dict[str, Any]] = []
    for i, s in enumerate(llm_out.get("scenes", []), start=1):
        layout = s.get("layout") if s.get("layout") in _VALID_LAYOUTS else "2cam"
        primary = s.get("primary_camera") or "host"
        active = s.get("active_roles") or [primary]
        primary, active = _coerce_roles(layout, primary, active)
        broll_id = (s.get("broll_id") or "").strip()
        broll_file = broll_by_stem.get(broll_id, "")
        if not broll_file and "broll" in layout:
            # b-roll layout but no valid b-roll chosen — fall back to the plain layout
            layout = layout.replace("_broll", "")
            broll_id = ""
            primary, active = _coerce_roles(layout, primary, active)
        scenes.append({
            "enabled": True,
            "scene_id": s.get("scene_id") or f"S{i:03d}",
            "start": s.get("start", ""),
            "end": s.get("end", ""),
            "duration": "",  # renderer infers from start/end
            "source_start": "",
            "layout": layout,
            "primary_camera": primary,
            "host_source": _ROLE_FILES["host"] if "host" in active else "",
            "guest_01_source": _ROLE_FILES["guest_01"] if "guest_01" in active else "",
            "guest_02_source": _ROLE_FILES["guest_02"] if "guest_02" in active else "",
            "broll_id": broll_id,
            "broll_file": broll_file,
            "broll_source_start": "",
            "top_row_text": lower_thirds.get(primary) or s.get("top_row_text", ""),
            "bottom_row_text": s.get("topic_heading") or episode_caption,
            "char": "",
            "notes": s.get("notes", ""),
        })

    broll_section = [{"broll_id": Path(b).stem, "file_name": b, "default_source_start": ""} for b in assets.get("broll", [])]
    branding = assets.get("branding", {})
    assets_section = [{"asset_key": key, "file_name": name, "purpose": key} for name, key in branding.items()]

    intro_file = _pick_asset(branding, "intro", (".mp4", ".mov", ".m4v"))
    show_image_file = _pick_asset(branding, "show_image", (".jpg", ".jpeg", ".png", ".webp"))
    background_file = _pick_asset(branding, "background", (".mp4", ".mov", ".m4v"))
    music_file = _pick_asset(branding, "music", (".wav", ".mp3"))

    # Show the first scene's lower third (the host's name) over the intro too.
    intro_lt_scene = scenes[0]["scene_id"] if scenes else ""
    settings_section = [
        {"setting": "auto_intro", "value": "true" if intro_file else "false"},
        {"setting": "intro_asset", "value": intro_file},
        {"setting": "intro_lower_third_scene_id", "value": intro_lt_scene},
        {"setting": "auto_opening_show_image", "value": "true" if show_image_file else "false"},
        {"setting": "show_image_asset", "value": show_image_file},
        {"setting": "auto_outro_show_image", "value": "true" if show_image_file else "false"},
        # Background plays behind multi-box layouts (2cam/3cam) only — the renderer
        # never applies it to intro / show_image / 1cam.
        {"setting": "background_video", "value": background_file},
        # Best-effort FFmpeg voice cleanup per mic. Turn OFF when the source audio
        # is already enhanced (Riverside Magic Audio) to avoid double-processing.
        {"setting": "voice_cleanup", "value": "true"},
    ]

    # Music bed over the intro + opening show image + a few seconds into the show,
    # then fades out (anchored to intro_start). Mirrors the gold plan's intro_music.
    audio_section: list[dict[str, Any]] = []
    if music_file:
        audio_section.append({
            "enabled": True, "audio_id": "intro_music", "anchor": "intro_start",
            "file": music_file, "start": "00:00:00.000", "end": "",
            "duration": "00:00:40.000", "source_start": "00:00:00.000",
            "volume": "0.2", "fade_in": "00:00:01.000", "fade_out": "00:00:10.000",
        })

    return {
        "project": episode_slug,
        "_generated_by": "generate_video_plan (Nathan/Alex draft — review before rendering)",
        "speaker_map": llm_out.get("speaker_map", {}),
        "scenes": scenes,
        "graphics": [],
        "broll": broll_section,
        "assets": assets_section,
        "audio": audio_section,
        "settings": settings_section,
    }


async def generate_video_plan(
    *,
    client_id: str,
    episode_slug: str,
    episode_caption: Optional[str] = None,
    transcript_path: Optional[str] = None,
    show_start: Optional[str] = None,
    speaker_map: Optional[dict[str, str]] = None,
    lower_thirds: Optional[dict[str, str]] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Draft planning/video_plan.json from the episode transcript (the planning
    step that used to be hand-authored in a spreadsheet).

    Reads the transcript (auto-detected in planning/, or `transcript_path`), the
    client brief, and the available footage/b-roll, then has Alex segment the
    interview into scenes with layouts, lower-thirds, and b-roll placement. Writes
    a complete video_plan.json that generate_video_draft can render immediately.
    Always review/iterate the draft — it's a starting cut, not final.
    """
    project_dir = _get_project_dir(client_id, episode_slug)
    planning = project_dir / "planning"
    project_id = ps.parlay_project_id(client_id, episode_slug)

    # Look in planning/ first, then assets/ (clients sometimes drop the transcript
    # alongside the footage).
    transcript_file = _find_transcript(planning, transcript_path) or _find_transcript(project_dir / "assets", None)
    if transcript_file is None:
        return {
            "status": "error",
            "episode_slug": episode_slug,
            "message": (
                f"No transcript found in {_repo_rel(planning)}/ or the assets/ folder. Drop a "
                "speaker-labeled transcript (e.g. the Riverside .txt), or pass transcript_path."
            ),
        }

    transcript = transcript_file.read_text(encoding="utf-8", errors="replace")
    # Drop pre-show setup chatter so the cut starts at the show (keep a little lead;
    # the LLM is also told the exact show start).
    if show_start:
        transcript = _trim_transcript_to_show(transcript, max(0.0, _tc_to_secs(show_start) - 10))
    transcript = transcript[:PLAN_TRANSCRIPT_CAP]
    caption = (episode_caption or episode_slug.replace("_", " ")).strip()
    brief = _load_brief(client_id)
    assets = _classify_assets(project_dir)

    try:
        llm_out = await _draft_scenes_with_llm(
            episode_caption=caption, transcript=transcript, brief=brief,
            assets=assets, speaker_map=speaker_map, notes=notes, show_start=show_start,
        )
    except Exception as exc:
        logger.exception("Video plan drafting failed for %s", episode_slug)
        return {"status": "error", "episode_slug": episode_slug, "message": f"Couldn't draft the plan: {exc}"}

    plan = _assemble_video_plan(episode_slug, caption, llm_out, assets, lower_thirds=lower_thirds)
    planning.mkdir(parents=True, exist_ok=True)
    plan_path = planning / "video_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    # Advance the state machine to PLANNING (force from intake if needed).
    try:
        ps.set_stage(project_id, ps.PLANNING, by="nathan", note=notes, client_id=client_id)
    except ps.ParlayTransitionError:
        ps.set_stage(project_id, ps.PLANNING, by="nathan", note="(plan drafted)", client_id=client_id, force=True)
    except Exception as exc:
        logger.warning("Could not set PLANNING stage for %s: %s", episode_slug, exc)
    _refresh_state_mirror(client_id, episode_slug)

    _safe_event(client_id, project_id, "video_plan_drafted",
                f"Drafted video plan for {episode_slug} ({len(plan['scenes'])} scenes)",
                {"scene_count": len(plan["scenes"]), "transcript": transcript_file.name,
                 "plan_path": _repo_rel(plan_path)})

    scenes_preview = [
        {"scene_id": s["scene_id"], "layout": s["layout"], "start": s["start"],
         "end": s["end"], "top_row_text": s["top_row_text"]}
        for s in plan["scenes"][:8]
    ]
    return {
        "status": "planned",
        "episode_slug": episode_slug,
        "client_id": client_id,
        "plan_path": _repo_rel(plan_path),
        "scene_count": len(plan["scenes"]),
        "speaker_map": plan["speaker_map"],
        "scenes_preview": scenes_preview,
        "transcript_used": transcript_file.name,
        "message": (
            f"Drafted a {len(plan['scenes'])}-scene plan for {episode_slug} from "
            f"{transcript_file.name}. Review the scenes/lower-thirds (and the speaker map "
            f"{plan['speaker_map']}), tweak if needed, then I can render the draft."
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
