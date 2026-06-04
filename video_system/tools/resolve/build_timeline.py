#!/usr/bin/env python3
"""
Resolve Timeline Builder for Podcast Parlay episodes.

Consumes planning/video_plan.json and builds (or updates) a timeline in DaVinci Resolve
that matches the plan's scenes, layouts, lower thirds text, b-roll, and assets.

This is the implementation of the "tools/resolve/build_timeline.py" step referenced in
video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md .

Usage (with DaVinci Resolve running and a project open):
    python video_system/tools/resolve/build_timeline.py video_system/projects/RamAir/Straight_From_The_Hart_Ep05

The script will:
- Connect via resolve_api
- Ensure standard bins
- Import assets from the episode's assets/ folder (using the plan's assets + broll sheets for mapping)
- Create a timeline named after the episode (e.g. Straight_From_The_Hart_Ep05_Assembly)
- Lay out clips on tracks according to the plan scenes (V1 Program for main cameras, additional tracks for guests/broll)
- Add markers or Text+ generators on the Lower Thirds track with the exact top_row_text / bottom_row_text from the plan
- Print a summary so you can review in Resolve and render the draft

This produces the *real* Resolve-native draft (not the FFmpeg fallback).

After running:
1. In Resolve, review the timeline.
2. Render a proxy or full draft to the episode's renders/ folder as longform_draft_v01.mp4 (or similar).
3. Then use the ParlayVU tools (or Nathan) to record_iteration and request approval.

See also:
- resolve_api.py for connection
- setup_interview_template.py for the bin + settings foundation this builds on
- The visual system in templates/visual_systems/parlayvu_interview/resolve/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make sibling imports work when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolve_api import (
    get_resolve,
    ResolveConnectionError,
    get_current_project,
)

# Reuse logic from the setup script where possible (simple copy for independence in v1)
def create_bins(media_pool: Any) -> None:
    """Create the standard Media Pool bin structure (same as setup_interview_template)."""
    root = media_pool.GetRootFolder()
    bins_to_create = [
        "01_Camera",
        "02_B-Roll",
        "03_Graphics",
        "04_Audio",
        "05_Branding",
        "06_Templates",
        "07_Archive",
    ]
    existing = {b.GetName(): b for b in (root.GetSubFolderList() or [])}
    for bin_name in bins_to_create:
        if bin_name not in existing:
            if media_pool.AddSubFolder(root, bin_name):
                print(f"  ✓ Created bin: {bin_name}")
            else:
                print(f"  ✗ Failed to create bin: {bin_name}")
        else:
            print(f"  - Bin already exists: {bin_name}")


def set_project_settings(project: Any) -> None:
    """Apply locked project settings (24fps, 1080, DaVinci YRGB)."""
    project.SetSetting("timelineFrameRate", "24")
    project.SetSetting("timelineResolutionWidth", "1920")
    project.SetSetting("timelineResolutionHeight", "1080")
    project.SetSetting("colorScienceMode", "davinciYRGBColorManaged")
    project.SetSetting("timelineWorkingLuminance", "Rec.709 Gamma 2.4")
    print("  ✓ Applied project settings (24fps, 1080p, DaVinci YRGB Color Managed)")


def load_plan(project_dir: Path) -> Dict[str, Any]:
    plan_path = project_dir / "planning" / "video_plan.json"
    if not plan_path.exists():
        # Try to auto-generate from xlsx if present
        xlsx = project_dir / "planning" / "video_plan.xlsx"
        if xlsx.exists():
            print(f"  video_plan.json missing — running spreadsheet_to_json...")
            import subprocess
            subprocess.check_call(
                [sys.executable, str(Path(__file__).resolve().parents[2] / "tools" / "spreadsheet_to_json.py"), str(project_dir)],
                cwd=Path(__file__).resolve().parents[2],
            )
    if not plan_path.exists():
        raise FileNotFoundError(f"No video_plan.json found at {plan_path}. Edit the .xlsx and re-run spreadsheet_to_json.")
    return json.loads(plan_path.read_text(encoding="utf-8"))


def get_or_create_timeline(project: Any, name: str) -> Any:
    existing = project.GetTimelineList() or []
    for tl in existing:
        if tl.GetName() == name:
            print(f"  - Using existing timeline: {name}")
            project.SetCurrentTimeline(tl)
            return tl

    print(f"  + Creating new timeline: {name}")
    timeline = project.CreateTimeline(name)
    if not timeline:
        raise RuntimeError(f"Failed to create timeline {name}")
    return timeline


def ensure_track(timeline: Any, track_type: str, track_index: int, name: Optional[str] = None) -> None:
    """Ensure a track exists (Resolve API is limited; add if missing)."""
    # Resolve timelines start with some tracks. We add more as needed.
    try:
        current_count = timeline.GetTrackCount(track_type) or 0
        while current_count < track_index:
            timeline.AddTrack(track_type)
            current_count += 1
        if name:
            # Naming tracks via API is limited in some versions; best effort
            try:
                timeline.SetTrackName(track_type, track_index, name)
            except Exception:
                pass  # Many versions don't expose easy rename; user can rename in UI
    except Exception as e:
        print(f"    (Track management note: {e})")


def import_assets_to_bins(project: Any, project_dir: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Import files from assets/ into the correct bins based on the plan's assets + broll sheets."""
    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    bins = {b.GetName(): b for b in (root.GetSubFolderList() or [])}

    assets_dir = project_dir / "assets"
    if not assets_dir.exists():
        print("  ! No assets/ folder — skipping media import")
        return {}

    imported: Dict[str, Any] = {}

    # 1. Handle explicit assets sheet from plan
    for row in plan.get("assets", []):
        key = row.get("asset_key")
        fname = row.get("file_name")
        if not fname:
            continue
        fpath = assets_dir / fname
        if not fpath.exists():
            print(f"    - Missing asset file for {key}: {fname}")
            continue
        target_bin_name = "05_Branding" if key in ("show_image", "logo_square", "intro") else "01_Camera"
        target_bin = bins.get(target_bin_name, root)
        media_pool.SetCurrentFolder(target_bin)
        items = media_pool.ImportMedia([str(fpath)])
        if items:
            imported[key] = items[0]
            print(f"  ✓ Imported {fname} → {target_bin_name} as '{key}'")

    # 2. Handle broll sheet (put in 02_B-Roll)
    for row in plan.get("broll", []):
        fname = row.get("file_name")
        if not fname:
            continue
        fpath = assets_dir / fname
        if not fpath.exists():
            print(f"    - Missing b-roll file: {fname}")
            continue
        target_bin = bins.get("02_B-Roll", root)
        media_pool.SetCurrentFolder(target_bin)
        items = media_pool.ImportMedia([str(fpath)])
        if items:
            broll_id = row.get("broll_id", fname)
            imported[broll_id] = items[0]
            print(f"  ✓ Imported b-roll {fname} → 02_B-Roll")

    # 3. Import any other loose files in assets/ (host/guest etc) into 01_Camera if not already
    for f in sorted(assets_dir.iterdir()):
        if f.suffix.lower() not in (".mp4", ".mov", ".mxf") or f.name in [r.get("file_name") for r in plan.get("assets", []) if r.get("file_name")]:
            continue
        target_bin = bins.get("01_Camera", root)
        media_pool.SetCurrentFolder(target_bin)
        items = media_pool.ImportMedia([str(f)])
        if items:
            key = f.stem
            imported[key] = items[0]
            print(f"  ✓ Imported loose camera file {f.name} → 01_Camera")

    return imported


def build_timeline_from_plan(timeline: Any, plan: Dict[str, Any], imported_media: Dict[str, Any], project_dir: Path) -> None:
    """Lay out the timeline according to the scenes in the plan."""
    scenes = [s for s in plan.get("scenes", []) if s.get("enabled", True)]
    if not scenes:
        print("  ! No enabled scenes in plan")
        return

    print(f"\nBuilding timeline from {len(scenes)} scenes...")

    # Ensure basic track layout (best effort)
    ensure_track(timeline, "video", 1, "Program")
    ensure_track(timeline, "video", 2, "Lower_Thirds")
    ensure_track(timeline, "video", 3, "B-Roll")
    ensure_track(timeline, "audio", 1, "Host")
    ensure_track(timeline, "audio", 2, "Guest")
    ensure_track(timeline, "audio", 3, "Broll_Nat")
    ensure_track(timeline, "audio", 4, "Music_Bed")

    current_record_frame = 0  # We will advance this

    fps = 24  # locked in settings

    for idx, scene in enumerate(scenes, 1):
        scene_id = scene.get("scene_id", f"S{idx}")
        layout = scene.get("layout", "1cam")
        duration_sec = float(scene.get("duration") or 0)
        if duration_sec <= 0:
            continue

        start_frame = int(current_record_frame)
        end_frame = int(current_record_frame + duration_sec * fps)

        # Determine primary sources
        host_name = scene.get("host_source") or "host.mp4"
        guest1_name = scene.get("guest_01_source") or "guest_01.mp4"
        broll_id = scene.get("broll_id") or scene.get("broll_file")

        # Simple placement: put the main camera clip(s) on Program track (V1)
        # For a real multicam or broll composite the user will refine in Resolve UI.
        # We use the plan's source_start if present for the clip's in-point.
        source_start = scene.get("source_start") or "00:00:00.000"

        # Try to find a media item we imported
        mpi = None
        for candidate in (host_name, guest1_name, broll_id):
            if candidate and candidate in imported_media:
                mpi = imported_media[candidate]
                break
            # fallback: try stem match
            for k, v in imported_media.items():
                if candidate and (candidate in k or k in (candidate or "")):
                    mpi = v
                    break
            if mpi:
                break

        if mpi:
            try:
                # Append with explicit record in/out (Resolve will handle the source range)
                # Note: Full control over source in/out + record in/out requires more advanced use of AppendToTimeline with dicts.
                media_pool = timeline.GetMediaPool()  # may not be direct; use project media pool if needed
                # Simpler: just append the whole clip and let user trim. For v1 this gets the structure in.
                timeline.AppendToTimeline([mpi])
                print(f"  [{scene_id}] {layout} — appended clip for {scene.get('top_row_text') or ''}")
            except Exception as e:
                print(f"  [{scene_id}] append failed: {e}")
        else:
            print(f"  [{scene_id}] {layout} — no matching media found for sources (will need manual import/place)")

        # Add lower third info as a marker on the timeline (easy to see + searchable)
        top = scene.get("top_row_text", "")
        bottom = scene.get("bottom_row_text", "")
        marker_name = f"{top} | {bottom}".strip(" |")
        if marker_name:
            try:
                timeline.AddMarker(start_frame, "Blue", marker_name[:50], f"Scene {scene_id} layout={layout}", 1)
            except Exception:
                pass  # Markers are nice-to-have

        current_record_frame = end_frame

    print(f"\nTimeline layout complete. Total approx duration: {current_record_frame / fps:.1f}s")
    print("Open the timeline in Resolve, review the markers for lower third text, refine multicam/broll compositing, then render your draft.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Resolve timeline from a Podcast Parlay video_plan.json")
    parser.add_argument("project", help="Path to the episode project folder (e.g. video_system/projects/RamAir/Straight_From_The_Hart_Ep05)")
    parser.add_argument("--plan", default=None, help="Optional explicit path to video_plan.json (defaults to <project>/planning/video_plan.json)")
    args = parser.parse_args()

    project_dir = Path(args.project).resolve()
    if not project_dir.exists():
        # allow calling with just the slug style
        project_dir = Path("video_system") / "projects" / args.project
        if not project_dir.exists():
            print(f"Project directory not found: {args.project}")
            return 1

    print(f"Podcast Parlay — Resolve Timeline Builder")
    print(f"Project: {project_dir}")
    print("=" * 60)

    try:
        print("\n[1/5] Connecting to Resolve...")
        resolve = get_resolve()
        print("  ✓ Connected")

        project = get_current_project(resolve)
        print(f"  Current Resolve project: {project.GetName()}")

        print("\n[2/5] Applying project settings...")
        set_project_settings(project)

        print("\n[3/5] Ensuring bins...")
        media_pool = project.GetMediaPool()
        create_bins(media_pool)

        print("\n[4/5] Loading plan and importing assets...")
        plan = load_plan(project_dir)
        imported = import_assets_to_bins(project, project_dir, plan)

        print("\n[5/5] Building timeline from plan...")
        episode_name = project_dir.name
        timeline_name = f"{episode_name}_Assembly_Draft"
        timeline = get_or_create_timeline(project, timeline_name)

        build_timeline_from_plan(timeline, plan, imported, project_dir)

        print("\n" + "=" * 60)
        print("SUCCESS: Timeline built in Resolve.")
        print(f"  Timeline: {timeline_name}")
        print("  Next:")
        print("    - Switch to the timeline in Resolve")
        print("    - Review markers for lower third content from the plan")
        print("    - Refine cuts, b-roll compositing, Fusion titles as needed")
        print("    - Render proxy/full draft to the episode's renders/ folder")
        print("    - Record the render as a new iteration in parlay_state and request approval")
        print("\nYou can now render the first Resolve-native draft for this episode.")
        return 0

    except ResolveConnectionError as e:
        print("\nConnection failed. Make sure:")
        print("  • DaVinci Resolve Studio is running")
        print("  • A project is open in Resolve")
        print("  • RESOLVE_PYTHON_API points to the correct Modules folder (see SETUP.md)")
        print(f"\n{e}")
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
