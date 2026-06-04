import sys
import os
mod_path = os.environ.get("RESOLVE_PYTHON_API") or r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
if mod_path and mod_path not in sys.path:
    sys.path.insert(0, mod_path)
import DaVinciResolveScript as dvr
r = dvr.scriptapp("Resolve")
print("Attached:", r)
if r:
    print("Version:", r.GetVersion())
    pm = r.GetProjectManager()
    proj = pm.GetCurrentProject()
    print("Project:", proj.GetName() if proj else "none")
else:
    print("Still none")