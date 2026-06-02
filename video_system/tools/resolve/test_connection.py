#!/usr/bin/env python3
"""
Diagnostic script: Verify DaVinci Resolve Python API connectivity.

This is the **first real validation gate** for the entire Resolve v2 automation system.

Usage (while DaVinci Resolve is running with a project open):
    python tools/resolve/test_connection.py

Exit codes:
    0 = Success
    1 = Failure (see output + SETUP.md)

See: tools/resolve/SETUP.md for detailed Windows setup instructions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sure we can import sibling modules when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from resolve_api import get_resolve, ResolveConnectionError


def main() -> int:
    print("DaVinci Resolve Python API Connection Test")
    print("=" * 60)
    print("This is a foundational validation step for the v2 system.")
    print("Resolve must be running with at least one project open.\n")

    # Show helpful environment info
    env_var = os.environ.get("RESOLVE_PYTHON_API")
    if env_var:
        print(f"[Env] RESOLVE_PYTHON_API is set to:\n      {env_var}\n")
    else:
        print("[Env] RESOLVE_PYTHON_API is NOT set (we will try discovery).\n")

    try:
        print("[1/4] Attempting to attach to running Resolve instance...")
        resolve = get_resolve()
        print("      ✓ Successfully attached to Resolve.")

        print("\n[2/4] Querying Resolve version and basic capabilities...")
        try:
            version = resolve.GetVersion()
            print(f"      Resolve version info: {version}")
        except Exception:
            print("      (Could not retrieve detailed version — this is often normal)")

        pm = resolve.GetProjectManager()
        print("      Project Manager available.")

        print("\n[3/4] Checking current project state...")
        current = pm.GetCurrentProject()
        if current:
            print(f"      Current project: {current.GetName()}")

            # Safe timeline listing — Resolve 21 beta can return None or have the method unavailable on fresh projects
            try:
                timeline_list = getattr(current, "GetTimelineList", None)
                if timeline_list and callable(timeline_list):
                    timelines = timeline_list() or []
                else:
                    timelines = []
                print(f"      Number of timelines in project: {len(timelines)}")
                if timelines:
                    for t in timelines[:3]:
                        print(f"        - {t.GetName()}")
            except Exception as e:
                print(f"      (Could not list timelines safely — this is common on fresh/empty projects in Resolve 21 beta)")
                print(f"      Detail: {e}")
        else:
            print("      (No project currently open in Resolve)")
            print("      → This is acceptable for the pure connection test,")
            print("        but you will want a project open for actual automation work.")

        print("\n[4/4] Basic API functionality verified successfully.")

        print("\n" + "=" * 60)
        print("SUCCESS: Resolve Python scripting is working on this machine.")
        print("\nNext steps:")
        print("  1. Read tools/resolve/SETUP.md for context on what we just validated.")
        print("  2. We can now proceed to designing the Resolve Project Template")
        print("     that will carry your visual language (lower thirds, layouts, etc.).")
        print("\nDo not proceed to building the timeline builder until this test passes cleanly.")
        return 0

    except ResolveConnectionError as e:
        print("\n" + "=" * 60)
        print("FAILURE: Could not establish a connection to DaVinci Resolve.")
        print("\n" + str(e))
        print("\nRecommended actions:")
        print("  1. Read the full troubleshooting guide: tools/resolve/SETUP.md")
        print("  2. Make sure Resolve is running and has a project open.")
        print("  3. Try setting the RESOLVE_PYTHON_API environment variable.")
        print("  4. Re-run this script after any changes.")
        print("\nIf you are still stuck after following SETUP.md, copy the entire")
        print("output above (including the searched paths) and share it.")
        return 1

    except Exception as e:
        print(f"\nUnexpected error type: {type(e).__name__}")
        print(f"Message: {e}")
        import traceback
        traceback.print_exc()
        print("\nPlease share the full traceback above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
