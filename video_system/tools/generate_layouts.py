"""Regenerate the interview layout masks at the renderer's native resolution.

The layout PNGs are hard-edged 3-colour masks: transparent where camera video
shows through, opaque white for the gutters/frames, and navy (12,34,66) for the
lower-third strip. They were authored at 1280x720 (BASE_W x BASE_H in
``render_video.py``) but the renderer composites at 1920x1080 (W x H). When the
renderer up-scales a 720p mask with LANCZOS it anti-aliases those hard edges,
producing a faint seam around every camera box and cameras that don't fill
tightly.

This tool re-exports the masks at native 1920x1080 using NEAREST resampling, so
the edges stay hard (exactly the same 3 colours, no anti-aliasing) and land on
the same coordinates the renderer uses to place cameras. The 1280x720 originals
are kept as the design source under ``layouts_src_1280/``; edit those and re-run
this script to regenerate.

Usage:
    python video_system/tools/generate_layouts.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# Match render_video.py's canvas.
W, H = 1920, 1080

TEMPLATE_ROOT = (
    Path(__file__).resolve().parent.parent
    / "templates"
    / "visual_systems"
    / "parlayvu_interview"
    / "legacy"
)
SRC_DIR = TEMPLATE_ROOT / "layouts_src_1280"
DST_DIR = TEMPLATE_ROOT / "layouts"


def regenerate() -> None:
    sources = sorted(SRC_DIR.glob("*.png"))
    if not sources:
        raise SystemExit(f"No source layouts found in {SRC_DIR}")
    for src in sources:
        dst = DST_DIR / src.name.lower()  # renderer references lowercase names
        mask = Image.open(src).convert("RGBA")
        # NEAREST keeps the mask's hard 3-colour edges; LANCZOS would blur them.
        out = mask.resize((W, H), Image.Resampling.NEAREST)
        out.save(dst)
        print(f"{src.stem}: {mask.size} -> {out.size}  ({dst.name})")


if __name__ == "__main__":
    regenerate()
