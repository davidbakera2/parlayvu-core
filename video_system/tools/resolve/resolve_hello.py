# Simple diagnostic script for Resolve Python scripting
# Run this via fuscript or from Resolve GUI Scripts to activate/test the API.

import sys
import os

# Ensure the module can be found when run via fuscript from external cmd
mod_path = os.environ.get("RESOLVE_PYTHON_API") or r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
if mod_path and mod_path not in sys.path:
    sys.path.insert(0, mod_path)

import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
if resolve:
    print("SUCCESS: Attached to Resolve from within script!")
    print("Version:", resolve.GetVersion())
    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    if proj:
        print("Current project:", proj.GetName())
    else:
        print("No current project")
else:
    print("FAILED: Could not attach to Resolve")
