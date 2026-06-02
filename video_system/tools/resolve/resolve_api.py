"""
Resolve API Connection & Helper Layer (v2)

This module provides a robust, well-documented interface to the DaVinci Resolve
Python scripting API. It handles the various ways the module can be discovered
on Windows and provides convenience wrappers for common operations.

Design goals:
- Fail with clear, actionable error messages.
- Support multiple discovery paths (env var, common install locations, etc.).
- Never assume Resolve is not running; the API requires a live instance.
- Keep this file focused on connection + low-level ops. Higher-level timeline
  construction lives in timeline_builder.py.

References:
- Blackmagic Design "DaVinci Resolve Scripting" documentation (PDF in Resolve install).
- Existing v1 renderer in ../render_video.py for visual parity targets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional


class ResolveConnectionError(Exception):
    """Raised when we cannot attach to a running Resolve instance."""
    pass


def _candidate_module_paths() -> list[Path]:
    """Return likely locations for DaVinciResolveScript.py / the Modules folder."""
    candidates: list[Path] = []

    # 1. Explicit environment variable (highest priority)
    env = os.environ.get("RESOLVE_PYTHON_API") or os.environ.get("DAVINCISCRIPT_PATH")
    if env:
        p = Path(env)
        candidates.append(p if p.is_dir() else p.parent)

    # 2. Common Windows install locations
    program_files = [
        Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve"),
        Path(r"C:\Program Files (x86)\Blackmagic Design\DaVinci Resolve"),
    ]
    for base in program_files:
        candidates.append(base / "Developer" / "Python" / "Modules")
        candidates.append(base / "Support" / "Developer" / "Python" / "Modules")
        candidates.append(base / "Developer" / "Scripting" / "Modules")          # Seen on some Resolve 21 installs
        candidates.append(base / "Support" / "Developer" / "Scripting" / "Modules")

    # 3. ProgramData locations (common on many Windows installs)
    progdata = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Blackmagic Design" / "DaVinci Resolve"
    candidates.extend([
        progdata / "Support" / "Developer" / "Python" / "Modules",
        progdata / "Support" / "Developer" / "Scripting" / "Modules",   # The one that worked for this user
        progdata / "Developer" / "Python" / "Modules",
        progdata / "Developer" / "Scripting" / "Modules",
    ])

    # 4. Current working directory / sibling (dev convenience)
    here = Path(__file__).resolve().parent
    candidates.append(here / "Modules")
    candidates.append(here.parent / "Modules")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def get_resolve() -> Any:
    """
    Attach to the running DaVinci Resolve instance and return the root object.

    Resolve **must** be running (and the project you want to work on should
    usually be open).

    Raises:
        ResolveConnectionError: with detailed diagnostic information if attachment fails.
    """
    # Avoid re-import pollution
    if "DaVinciResolveScript" in sys.modules:
        import DaVinciResolveScript as dvr  # type: ignore

        resolve = dvr.scriptapp("Resolve")
        if resolve:
            return resolve

    # Try to discover and inject the module path
    for path in _candidate_module_paths():
        if not path.exists():
            continue
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

        try:
            import DaVinciResolveScript as dvr  # type: ignore

            resolve = dvr.scriptapp("Resolve")
            if resolve:
                return resolve
        except ImportError:
            # Try next candidate
            continue
        finally:
            # Clean up the path we added if import failed for this candidate
            if str(path) in sys.path:
                sys.path.remove(str(path))

    # If we get here, we failed
    searched = "\n  - ".join(str(p) for p in _candidate_module_paths())
    msg = (
        "Could not connect to DaVinci Resolve.\n\n"
        "Prerequisites:\n"
        "  1. DaVinci Resolve must be running.\n"
        "  2. The Python scripting module must be discoverable.\n\n"
        "Searched locations:\n"
        f"  - {searched}\n\n"
        "Quick fixes to try:\n"
        "  - Set environment variable RESOLVE_PYTHON_API to the full path of the\n"
        "    'Modules' folder containing DaVinciResolveScript.py\n"
        "  - In Resolve: Workspace > Scripts > Script Console (to confirm scripting works)\n"
        "  - Re-run this script while Resolve is the foreground application.\n\n"
        "See tools/resolve/README.md and docs/V2_RESOLVE_AUTOMATION_DESIGN.md for setup."
    )
    raise ResolveConnectionError(msg)


def get_project_manager(resolve: Optional[Any] = None) -> Any:
    """Convenience wrapper."""
    if resolve is None:
        resolve = get_resolve()
    pm = resolve.GetProjectManager()
    if not pm:
        raise ResolveConnectionError("Connected to Resolve but GetProjectManager() returned None.")
    return pm


def get_current_project(resolve: Optional[Any] = None) -> Any:
    """Return the currently open project, or raise with guidance."""
    pm = get_project_manager(resolve)
    proj = pm.GetCurrentProject()
    if not proj:
        raise ResolveConnectionError(
            "No project is currently open in Resolve. Open or create one, then retry."
        )
    return proj


# --- Future low-level helpers (stubs for now) ---

def ensure_bin(project: Any, name: str) -> Any:
    """Create or return a Media Pool bin by name (to be implemented in Phase 2)."""
    raise NotImplementedError("ensure_bin will be implemented during Phase 2 timeline builder work.")


def add_marker(timeline: Any, frame: int, color: str, name: str, note: str = "") -> None:
    """Add a timeline marker (convenience). To be expanded."""
    # Placeholder — real implementation will use timeline.AddMarker(...)
    raise NotImplementedError("add_marker stub — implement during timeline builder development.")
