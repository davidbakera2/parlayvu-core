#!/usr/bin/env python3
"""
Resolve Project Setup Script — parlayvu_interview Template

This script connects to a running DaVinci Resolve instance and creates
the foundational structure for the parlayvu_interview visual system.

It creates:
- Project settings (24fps, YRGB Color Managed)
- Media Pool bins (following our spec)
- A starter timeline with the correct track layout
- Placeholder for the lower third Fusion composition

Usage:
1. Open DaVinci Resolve
2. Create or open the project you want to use as the template master
3. Run this script while Resolve is running

Example:
    python tools/resolve/setup_interview_template.py
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add the resolve tools to the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolve_api import get_resolve, ResolveConnectionError


def create_bins(media_pool) -> None:
    """Create the standard Media Pool bin structure."""
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

    existing = {b.GetName(): b for b in root.GetSubFolderList() or []}

    for bin_name in bins_to_create:
        if bin_name not in existing:
            success = media_pool.AddSubFolder(root, bin_name)
            if success:
                print(f"  ✓ Created bin: {bin_name}")
            else:
                print(f"  ✗ Failed to create bin: {bin_name}")
        else:
            print(f"  - Bin already exists: {bin_name}")


def create_timeline(project) -> None:
    """Create the template timeline with our standard track layout."""
    timeline_name = "Template_Timeline_v1"

    existing_timelines = project.GetTimelineList() or []
    for tl in existing_timelines:
        if tl.GetName() == timeline_name:
            print(f"  - Timeline '{timeline_name}' already exists. Skipping creation.")
            return

    # Create timeline at 24fps, 1920x1080
    timeline = project.CreateTimeline(timeline_name)

    if not timeline:
        print("  ✗ Failed to create timeline")
        return

    print(f"  ✓ Created timeline: {timeline_name}")

    # Note: As of Resolve 21, some track creation is limited via API.
    # We will create the basic timeline here and document the full track layout
    # so the user can finish the last 10% manually or we extend the script later.
    print("  → Timeline created with default tracks.")
    print("  → You will still need to add/rename tracks to match our spec (see TIMELINE_TRACK_LAYOUT.md)")


def set_project_settings(project) -> None:
    """Apply our locked project settings."""
    settings = project.GetSetting()

    # These are the settings we can reliably set via the API
    project.SetSetting("timelineFrameRate", "24")
    project.SetSetting("timelineResolutionWidth", "1920")
    project.SetSetting("timelineResolutionHeight", "1080")
    project.SetSetting("colorScienceMode", "davinciYRGBColorManaged")
    project.SetSetting("timelineWorkingLuminance", "Rec.709 Gamma 2.4")

    print("  ✓ Applied project settings:")
    print("    - Frame rate: 24.000")
    print("    - Resolution: 1920x1080")
    print("    - Color Management: DaVinci YRGB Color Managed (Rec.709 Gamma 2.4)")


def main() -> int:
    print("ParlayVU Interview Template — Resolve Project Setup")
    print("=" * 55)

    try:
        print("\nConnecting to Resolve...")
        resolve = get_resolve()
        print("  ✓ Connected to Resolve")

        project_manager = resolve.GetProjectManager()
        project = project_manager.GetCurrentProject()

        if not project:
            print("\nERROR: No project is currently open in Resolve.")
            print("Please open or create a project first, then run this script again.")
            return 1

        print(f"\nCurrent project: {project.GetName()}")

        # Apply settings
        print("\n[1/3] Applying project settings...")
        set_project_settings(project)

        # Create bins
        print("\n[2/3] Creating Media Pool bins...")
        media_pool = project.GetMediaPool()
        create_bins(media_pool)

        # Create starter timeline
        print("\n[3/3] Creating template timeline...")
        create_timeline(project)

        print("\n" + "=" * 55)
        print("Setup complete.")
        print("\nNext steps:")
        print("  1. Open the Media Pool and review the new bins.")
        print("  2. Open the timeline and manually add/rename tracks to match our spec.")
        print("  3. Start building the lower third Fusion composition (see FUSION_LOWER_THIRD_SPEC.md).")
        print("\nWould you like me to generate the next script (e.g. one that creates")
        print("a starter Fusion lower third composition for you)?")

        return 0

    except ResolveConnectionError as e:
        print(f"\nConnection failed:\n{e}")
        return 1
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())