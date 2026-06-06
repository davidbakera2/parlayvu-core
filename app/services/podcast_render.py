"""Podcast Parlay — Execute adapter (FFmpeg).

The Podcast Parlay's Execute stage: turn an approved ``video_plan`` into a rendered video.
This wraps ``video_system/tools/render_video.py`` (the FFmpeg renderer) behind a callable so
the parlay/operator can render without touching the CLI.

The renderer is a "dumb adapter" — it consumes the plan and the client's Show Kit and emits
mp4s. We invoke it as a subprocess and return the output paths.

Project layout the renderer expects (and that ``render_episode`` assembles):

    <project>/
      planning/video_plan.json   # the approved plan
      assets/                     # episode media (host.mp4, guest_01.mp4, ...) + Show Kit assets
      renders/                    # output (created): final_no_subtitles.mp4 [, final_with_subtitles.mp4]
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("parlayvu.services.podcast_render")

REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "video_system" / "tools" / "render_video.py"

# The renderer's own CLI default (templates/ramair_interview) is only a README stub; the real
# complete Show Kit (layouts + styles + config) is parlayvu_interview/legacy. Default to it.
DEFAULT_TEMPLATE = (
    REPO_ROOT / "video_system" / "templates" / "visual_systems"
    / "parlayvu_interview" / "legacy" / "template_config.json"
)


def render_project(
    *,
    project_dir: Path | str,
    template: Optional[Path | str] = None,
    with_subtitles: bool = False,
    max_scenes: Optional[int] = None,
) -> dict:
    """Render a prepared project directory to ``renders/*.mp4``.

    Args:
        project_dir: a folder containing ``planning/video_plan.json`` and ``assets/``.
        template: path to a Show Kit ``template_config.json`` (defaults to the RamAir kit).
        with_subtitles: also render ``final_with_subtitles.mp4``.
        max_scenes: render only the first N enabled scenes (smoke tests).

    Returns a dict with the output paths. Raises FileNotFoundError for missing inputs and
    RuntimeError if the renderer exits non-zero.
    """
    project_dir = Path(project_dir).resolve()
    plan_path = project_dir / "planning" / "video_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"No video_plan.json at {plan_path}")
    if not RENDERER.is_file():
        raise FileNotFoundError(
            f"Renderer not found at {RENDERER}. Is video_system present in this checkout?"
        )
    template_path = Path(template).resolve() if template else DEFAULT_TEMPLATE
    if not template_path.is_file():
        raise FileNotFoundError(f"Show Kit template not found at {template_path}")

    cmd: list[str] = [sys.executable, str(RENDERER), str(project_dir), "--template", str(template_path)]
    if with_subtitles:
        cmd.append("--with-subtitles")
    if max_scenes is not None:
        cmd += ["--max-scenes", str(max_scenes)]

    logger.info("Rendering podcast project | project=%s template=%s", project_dir, template_path)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error(
            "Renderer failed (rc=%s)\nSTDOUT (tail):\n%s\nSTDERR (tail):\n%s",
            proc.returncode, (proc.stdout or "")[-2000:], (proc.stderr or "")[-2000:],
        )
        raise RuntimeError(f"Renderer failed (rc={proc.returncode}): {(proc.stderr or '')[-500:]}")

    no_subs = project_dir / "renders" / "final_no_subtitles.mp4"
    if not no_subs.is_file():
        raise RuntimeError(f"Renderer reported success but {no_subs} is missing")

    result = {"status": "rendered", "project_dir": str(project_dir), "no_subtitles": str(no_subs)}
    if with_subtitles:
        result["with_subtitles"] = str(project_dir / "renders" / "final_with_subtitles.mp4")
    logger.info("Render complete | %s", result["no_subtitles"])
    return result


def render_episode(
    *,
    client_id: str,
    slug: str,
    template: Optional[Path | str] = None,
    with_subtitles: bool = False,
    max_scenes: Optional[int] = None,
) -> dict:
    """Render a persisted episode plan into the client's deliverables.

    Convention: the render project lives at
    ``client_artifacts/<client_id>/03_Deliverables/podcast/<slug>/`` with ``assets/`` (the
    episode media, supplied by the client/producer) and ``planning/video_plan.json`` (copied
    from the planning layer's persisted plan if not already present).
    """
    from app.client_config import CLIENT_ARTIFACTS_ROOT

    for value, label in ((client_id, "client_id"), (slug, "slug")):
        if not value or any(sep in value for sep in ("/", "\\")) or value in (".", ".."):
            raise ValueError(f"Invalid {label} for render: {value!r}")

    client_root = (CLIENT_ARTIFACTS_ROOT / client_id).resolve()
    project_dir = (client_root / "03_Deliverables" / "podcast" / slug).resolve()

    planning_dir = project_dir / "planning"
    planning_dir.mkdir(parents=True, exist_ok=True)
    project_plan = planning_dir / "video_plan.json"

    if not project_plan.is_file():
        # Pull the approved plan from the planning layer's location.
        persisted = client_root / "02_Planning" / "podcast_plans" / slug / "video_plan.json"
        if not persisted.is_file():
            raise FileNotFoundError(
                f"No plan to render: neither {project_plan} nor {persisted} exists. "
                f"Run the planning stage first."
            )
        shutil.copy2(persisted, project_plan)
        logger.info("Copied approved plan into render project | %s -> %s", persisted, project_plan)

    return render_project(
        project_dir=project_dir,
        template=template,
        with_subtitles=with_subtitles,
        max_scenes=max_scenes,
    )
