"""Podcast Parlay — b-roll auto-description (Claude vision) with a correctable manifest.

Each b-roll clip in an episode's assets is described once by Claude vision (an image is sent
directly; a video clip's midpoint frame is extracted with ffmpeg). Results — a one-line
description, tags, and a specific/generic usage flag — are stored in `assets/broll.json` so
Alex can place b-roll by *meaning* rather than by file name.

Learning loop: producer corrections (made in chat -> `correct_broll_entry`) are marked
`source: "corrected"` and are **preserved** when descriptions are regenerated, so the manifest
only improves over time.
"""
from __future__ import annotations

import base64
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("parlayvu.podcast_broll")

MANIFEST_NAME = "broll.json"
VISION_MODEL = "claude-sonnet-4-6"

IMAGE_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv"}

DESCRIBE_PROMPT = """You are cataloguing one b-roll clip for an interview-style video about
HVAC duct cleaning and indoor air quality. The image is either a still or a frame sampled
from a short video clip. Return ONLY JSON, no markdown:

{"description": "one concise sentence: what is shown and when an editor would cut to it",
 "tags": ["3-6 short keywords"],
 "usage": "specific" or "generic"}

- "specific": tied to a particular topic, person, product, or document (use only on that beat).
- "generic": general/atmospheric footage usable across many beats."""


# --------------------------------------------------------------------------- vision
def _probe_duration(path: Path) -> Optional[float]:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def _frame_from_video(path: Path) -> bytes:
    """Extract a representative (midpoint) frame from a video clip as PNG bytes."""
    dur = _probe_duration(path) or 2.0
    ts = max(0.0, dur / 2.0)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "frame.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", str(path), "-frames:v", "1", str(out)],
            check=True, capture_output=True,
        )
        return out.read_bytes()


def _prepare_image(path: Path) -> tuple[str, str]:
    """Return (base64 data, media_type) for the clip — sampling a frame for video."""
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        data, media_type = _frame_from_video(path), "image/png"
    else:
        media_type = IMAGE_MEDIA_TYPES.get(ext, "image/png")
        data = path.read_bytes()
    return base64.b64encode(data).decode("ascii"), media_type


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _vision_describe(b64_data: str, media_type: str) -> dict:
    """One Claude vision call -> {description, tags, usage}. Patched in tests."""
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=VISION_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64_data}},
            {"type": "text", "text": DESCRIBE_PROMPT},
        ]}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return json.loads(_strip_fence(text))


def describe_broll_file(path: Path | str) -> dict:
    """Auto-describe a single b-roll file. Returns a manifest entry (source='auto')."""
    path = Path(path)
    b64, media_type = _prepare_image(path)
    out = _vision_describe(b64, media_type)
    return {
        "file": path.name,
        "description": str(out.get("description", "")).strip(),
        "tags": [str(t) for t in (out.get("tags") or [])],
        "usage": out.get("usage") if out.get("usage") in ("specific", "generic") else "specific",
        "source": "auto",
    }


# --------------------------------------------------------------------------- manifest
def _manifest_path(assets_dir: Path | str) -> Path:
    return Path(assets_dir) / MANIFEST_NAME


def _broll_files(assets_dir: Path | str) -> list[Path]:
    assets_dir = Path(assets_dir)
    valid = set(IMAGE_MEDIA_TYPES) | VIDEO_EXTS
    if not assets_dir.is_dir():
        return []
    return sorted(
        p for p in assets_dir.iterdir()
        if p.is_file() and p.stem.lower().startswith("broll") and p.suffix.lower() in valid
    )


def load_broll_descriptions(assets_dir: Path | str) -> dict[str, dict]:
    """Read assets/broll.json into {file_name: entry}; empty if absent/unreadable."""
    p = _manifest_path(assets_dir)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {e["file"]: e for e in data if isinstance(e, dict) and e.get("file")}
    except Exception:
        return {}


def _write(assets_dir: Path | str, by_file: dict[str, dict]) -> list[dict]:
    entries = [by_file[k] for k in sorted(by_file)]
    _manifest_path(assets_dir).write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return entries


def generate_broll_manifest(assets_dir: Path | str, *, redescribe_auto: bool = False) -> list[dict]:
    """Ensure every b-roll file has a description in assets/broll.json.

    Corrected entries are always preserved. Auto entries are kept unless redescribe_auto.
    New files are described via vision.
    """
    existing = load_broll_descriptions(assets_dir)
    by_file: dict[str, dict] = {}
    for path in _broll_files(assets_dir):
        cur = existing.get(path.name)
        if cur and (cur.get("source") == "corrected" or not redescribe_auto):
            by_file[path.name] = cur
            continue
        try:
            by_file[path.name] = describe_broll_file(path)
        except Exception as exc:
            logger.warning("b-roll describe failed for %s: %s", path.name, exc)
            by_file[path.name] = cur or {
                "file": path.name, "description": "", "tags": [], "usage": "generic", "source": "auto",
            }
    return _write(assets_dir, by_file)


def correct_broll_entry(
    assets_dir: Path | str,
    file: str,
    *,
    description: Optional[str] = None,
    tags: Optional[list[str]] = None,
    usage: Optional[str] = None,
) -> dict:
    """Apply a producer correction (the chat learning loop) and mark it 'corrected'."""
    by_file = load_broll_descriptions(assets_dir)
    entry = by_file.get(file) or {"file": file, "description": "", "tags": [], "usage": "specific"}
    if description is not None:
        entry["description"] = description
    if tags is not None:
        entry["tags"] = tags
    if usage is not None:
        entry["usage"] = usage
    entry["source"] = "corrected"
    by_file[file] = entry
    _write(assets_dir, by_file)
    return entry
