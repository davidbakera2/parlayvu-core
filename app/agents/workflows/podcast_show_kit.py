"""Show Kit merge — combine per-episode planning with a client's constant podcast format.

The two-layer model (see docs/parlays/podcast-parlay-runbook.md):
  - **Show Kit** (this module's input): the constant per-client format — background video,
    music cues, intro/outro bookends, render settings. Lives at
    video_system/templates/visual_systems/<visual_system>/show_kit.json.
  - **Video Plan program scenes** (from Alex): the per-episode interview cuts — layout,
    source_start, duration, lower-third text, b-roll.

`merge_with_show_kit()` wraps the program scenes in the Show Kit's bookends, lays out a
coherent final timeline (intro plays its full length), and attaches the Show Kit's settings,
music cues, and asset map — producing a complete, render-ready `video_plan`.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("parlayvu.podcast_show_kit")

# app/agents/workflows/podcast_show_kit.py -> repo root is parents[3]
VISUAL_SYSTEMS_DIR = (
    Path(__file__).resolve().parents[3] / "video_system" / "templates" / "visual_systems"
)

PROGRAM_LAYOUTS = {"1cam", "2cam", "2cam_broll", "3cam", "3cam_broll"}


# --------------------------------------------------------------------------- time helpers
def to_seconds(value: Any, default: float = 0.0) -> float:
    """Parse 'HH:MM:SS.mmm' (or seconds) to float seconds. Tolerates a leading '-'."""
    if value in (None, ""):
        return default
    s = str(value).strip()
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    try:
        if ":" in s:
            parts = [float(p) for p in s.split(":")]
            while len(parts) < 3:
                parts.insert(0, 0.0)
            secs = parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            secs = float(s)
    except ValueError:
        return default
    return -secs if neg else secs


def hhmmss(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def probe_duration(path: Path) -> Optional[float]:
    """Best-effort media duration via ffprobe; None if unavailable."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


# --------------------------------------------------------------------------- show kit
def load_show_kit(visual_system: str = "parlayvu_interview") -> dict:
    path = VISUAL_SYSTEMS_DIR / visual_system / "show_kit.json"
    if not path.is_file():
        raise FileNotFoundError(f"Show Kit not found for visual system {visual_system!r}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_broll_manifest(assets_dir: Optional[Path | str]) -> list[dict]:
    """Scan the episode assets folder for the real b-roll files Alex may use.

    Merges in vision-generated descriptions/tags/usage from assets/broll.json when present
    (see app/agents/workflows/podcast_broll.py) so Alex can place b-roll by meaning.
    """
    if not assets_dir:
        return []
    assets_dir = Path(assets_dir)
    if not assets_dir.is_dir():
        return []

    try:
        from app.agents.workflows.podcast_broll import load_broll_descriptions
        descriptions = load_broll_descriptions(assets_dir)
    except Exception:
        descriptions = {}

    manifest = []
    for p in sorted(assets_dir.iterdir()):
        if p.is_file() and p.stem.lower().startswith("broll") and p.name != "broll.json":
            entry = {"broll_id": p.stem, "file_name": p.name}
            d = descriptions.get(p.name)
            if d:
                entry["description"] = d.get("description", "")
                entry["tags"] = d.get("tags", [])
                entry["usage"] = d.get("usage", "")
            manifest.append(entry)
    return manifest


def format_camera_roster(cameras: Optional[dict]) -> str:
    """Render the camera->person map for a planner prompt.

    `cameras` maps slots (host / guest_01 / guest_02) to a name string or
    {name, title}. Returns one line per populated slot.
    """
    if not cameras:
        return ""
    lines = []
    for slot in ("host", "guest_01", "guest_02"):
        person = cameras.get(slot)
        if not person:
            continue
        if isinstance(person, str):
            lines.append(f"{slot} = {person}")
        else:
            name = person.get("name", "")
            title = person.get("title", "")
            lines.append(f"{slot} = {name}" + (f" ({title})" if title else ""))
    return "\n".join(lines)


def _intro_duration(intro_cfg: dict, assets_dir: Optional[Path]) -> float:
    """Full intro length: probe the intro asset when play_full + media available; else default."""
    default = to_seconds(intro_cfg.get("default_duration"), 15.0)
    if intro_cfg.get("play_full") and assets_dir:
        probed = probe_duration(Path(assets_dir) / intro_cfg.get("asset", "intro.mp4"))
        if probed and probed > 0:
            return probed
    return default


def merge_with_show_kit(
    *,
    program_scenes: list[dict],
    show_kit: dict,
    project: str,
    graphics: Optional[list[dict]] = None,
    broll: Optional[list[dict]] = None,
    assets_dir: Optional[Path | str] = None,
) -> dict:
    """Assemble a full Ep04-format video_plan from program scenes + a Show Kit.

    program_scenes: per-episode interview scenes, each with at least ``layout``,
    ``source_start`` and ``duration`` (trimmed-video time), plus lower-third text and
    optional b-roll fields. Bookends, settings, audio, and assets come from the Show Kit.
    """
    assets_dir = Path(assets_dir) if assets_dir else None
    bookends = show_kit["bookends"]
    intro_cfg, osi_cfg, outro_cfg = bookends["intro"], bookends["opening_show_image"], bookends["outro"]

    intro_dur = _intro_duration(intro_cfg, assets_dir)
    osi_dur = to_seconds(osi_cfg.get("duration"), 5.0)
    outro_dur = to_seconds(outro_cfg.get("duration"), 5.0)

    scenes: list[dict] = []
    t = 0.0

    # Intro (full length) + opening show image.
    scenes.append({
        "enabled": True, "scene_id": intro_cfg["scene_id"], "layout": "intro",
        "start": hhmmss(0.0), "end": hhmmss(intro_dur), "duration": hhmmss(intro_dur),
        "host_source": intro_cfg.get("asset", "intro.mp4"), "notes": "Opening intro clip",
    })
    t += intro_dur
    scenes.append({
        "enabled": True, "scene_id": osi_cfg["scene_id"], "layout": "show_image",
        "start": hhmmss(t), "end": hhmmss(t + osi_dur), "duration": hhmmss(osi_dur),
        "host_source": osi_cfg.get("asset", "show_image.png"), "notes": "Opening show image",
    })
    t += osi_dur

    # Program scenes (the interview), laid end-to-end. source_start stays in trimmed time.
    first_program_id: Optional[str] = None
    for i, ps in enumerate(program_scenes, start=1):
        layout = ps.get("layout", "2cam")
        if layout not in PROGRAM_LAYOUTS:
            logger.warning("Skipping program scene with non-program layout %r", layout)
            continue
        sid = ps.get("scene_id") or f"S{i:03d}"
        first_program_id = first_program_id or sid
        dur = to_seconds(ps.get("duration"), 0.0)

        # Active cameras for this scene. Alex may name them explicitly (e.g. ["host",
        # "guest_02"] to show the host with the second guest); otherwise infer from layout.
        cams = ps.get("cameras")
        if not cams:
            n = 3 if layout.startswith("3cam") else (1 if layout == "1cam" else 2)
            cams = ["host", "guest_01", "guest_02"][:n]

        scene = {
            "enabled": True, "scene_id": sid, "layout": layout,
            "start": hhmmss(t), "end": hhmmss(t + dur), "duration": hhmmss(dur),
            "source_start": ps.get("source_start", ""),
            "primary_camera": ps.get("primary_camera") or (cams[0] if cams else "host"),
            "top_row_text": ps.get("top_row_text", ""),
            "bottom_row_text": ps.get("bottom_row_text", ""),
            "notes": ps.get("notes", ""),
        }
        for cam in ("host", "guest_01", "guest_02"):
            if cam in cams:
                scene[f"{cam}_source"] = f"{cam}.mp4"
        if "broll" in layout:
            scene["broll_id"] = ps.get("broll_id", "")
            if ps.get("broll_file"):
                scene["broll_file"] = ps["broll_file"]
        scenes.append(scene)
        t += dur

    # Closing show image (outro).
    scenes.append({
        "enabled": True, "scene_id": outro_cfg["scene_id"], "layout": "outro",
        "start": hhmmss(t), "end": hhmmss(t + outro_dur), "duration": hhmmss(outro_dur),
        "host_source": outro_cfg.get("asset", "show_image.png"), "notes": "Closing show image",
    })

    # Settings: Show Kit defaults + the dynamically-resolved intro lower-third scene.
    settings = [dict(s) for s in show_kit.get("settings", [])]
    if first_program_id:
        settings = [s for s in settings if s.get("setting") != "intro_lower_third_scene_id"]
        settings.append({
            "setting": "intro_lower_third_scene_id", "value": first_program_id,
            "notes": "Auto: first interview scene's lower third is shown over the intro.",
        })

    return {
        "project": project,
        "scenes": scenes,
        "graphics": graphics or [],
        "broll": broll or [],
        "assets": [dict(a) for a in show_kit.get("assets", [])],
        "settings": settings,
        "audio": [dict(a) for a in show_kit.get("audio", [])],
    }
