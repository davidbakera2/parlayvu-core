# How to Run Resolve Automation Scripts

## Prerequisites
- DaVinci Resolve must be running
- You must have a project open
- The environment variable `RESOLVE_PYTHON_API` must be set (we already did this earlier)

## Running a Script

Open PowerShell and run:

```powershell
cd C:\Users\DavidBaker\parlayvu-core\video_system
python tools\resolve\setup_interview_template.py
```

The script will:
- Connect to your running Resolve instance
- Apply our locked project settings (24 fps + DaVinci YRGB Color Managed)
- Create the standard Media Pool bins
- Create a starter timeline

## What This Actually Does For You

Instead of you manually creating 7 bins and setting up project settings every time, the script does it in ~5 seconds.

This is the beginning of me doing real work inside Resolve for you.

## Next Things I Can Build For You

Tell me which one you want next:

1. **Create a basic Fusion Lower Third composition** via script (generates a starter .comp or uses the API to add a Fusion title)
2. **Create the full timeline track layout** automatically (V1 Program, V2 Lower Thirds, V3 Cards, proper audio tracks, etc.)
3. **Import a set of starter assets** into the correct bins
4. **Generate a complete starter project** from scratch (new project + everything)

Just say the number or describe what you want me to make Resolve do.