"""Build the Teams app installation package for ParlayVU's Nathan bot.

Generates color.png (192x192) and outline.png (32x32) if missing, then
zips them with manifest.json into infra/teams-app/parlayvu-teams-app.zip
ready to upload via Teams Admin Center -> Manage apps -> Upload.

Run:
    python infra/teams-app/build_app_package.py
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent


def _ensure_icons() -> None:
    """Generate placeholder PNGs if they don't exist yet.

    Teams requires the icons to be present and the right pixel dimensions.
    Anything renderable is acceptable for a working install — we use a
    simple solid background with a 'P' glyph as the placeholder. Swap in
    real branded artwork later by replacing these files.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print(
            "Pillow is required to generate placeholder icons.\n"
            "Install it: pip install Pillow",
            file=sys.stderr,
        )
        sys.exit(2)

    color_path = HERE / "color.png"
    outline_path = HERE / "outline.png"

    # Color icon — 192x192, dark slate background with a centered "P"
    if not color_path.exists():
        img = Image.new("RGBA", (192, 192), (31, 41, 55, 255))  # #1F2937
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 130)
        except OSError:
            font = ImageFont.load_default()
        text = "P"
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((192 - w) / 2 - bbox[0], (192 - h) / 2 - bbox[1] - 6),
            text,
            fill=(255, 255, 255, 255),
            font=font,
        )
        img.save(color_path, "PNG")
        print(f"Generated {color_path}")

    # Outline icon — 32x32, transparent background with a white "P"
    # Teams overlays this on its own background; pixels must be white only.
    if not outline_path.exists():
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 26)
        except OSError:
            font = ImageFont.load_default()
        text = "P"
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            ((32 - w) / 2 - bbox[0], (32 - h) / 2 - bbox[1] - 2),
            text,
            fill=(255, 255, 255, 255),
            font=font,
        )
        img.save(outline_path, "PNG")
        print(f"Generated {outline_path}")


def _build_zip() -> Path:
    out = HERE / "parlayvu-teams-app.zip"
    if out.exists():
        out.unlink()
    members = ["manifest.json", "color.png", "outline.png"]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for m in members:
            path = HERE / m
            if not path.is_file():
                raise FileNotFoundError(f"Missing {path}; can't build package")
            zf.write(path, m)
    return out


def main() -> int:
    _ensure_icons()
    out = _build_zip()
    print(f"\nBuilt Teams app package: {out}")
    print(f"  Bot ID: 2dc8aa66-9c5b-4ff5-9151-48408f1f6554")
    print(
        "\nNext steps (one-time per Teams tenant):\n"
        "  1. Open https://admin.teams.microsoft.com -> Teams apps -> Manage apps\n"
        f"  2. Click 'Upload new app' -> choose {out.name}\n"
        "  3. Approve it for org-wide use (or scope to specific users)\n"
        "  4. In the RamAir Team: ... -> Manage team -> Apps -> Add an app -> search 'ParlayVU' -> Add\n"
        "  5. In any channel of that team, type @ParlayVU — Nathan should appear in the autocomplete\n"
        "\nSee infra/teams-app/README.md for the full install + verify checklist."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
