# Resolve Integration Tools (v2)

This directory contains the new DaVinci Resolve automation layer for the video production system.

**Important:** This is a clean, Resolve-native implementation. We are not porting the old FFmpeg compositor logic. We are building for what Resolve does best.

## Philosophy

- The existing `templates/visual_systems/parlayvu_interview/` visual system (lower thirds, layouts, b-roll cards, branding treatment) is the **reference visual language** we must match. This is the reusable ParlayVU interview aesthetic (originally developed for RamAir).
- We use Resolve **natively** (Text+, Fusion, multicam, timeline structure, etc.).
- The structured plan is the portable "intent" layer.
- Code here must be clean, well-documented, and respect the broader Podcast Parlay integration inside ParlayVU.

## Critical First Step: Environment Validation

**Before doing anything else**, run the connection test:

```powershell
python tools/resolve/test_connection.py
```

Full instructions and troubleshooting live here:

→ **[SETUP.md](./SETUP.md)**

This is the first real gate. The entire automation capability depends on reliable Resolve scripting.

## Current Modules

- `resolve_api.py` — Robust connection helper + low-level operations. Handles Windows path discovery via `RESOLVE_PYTHON_API` env var.
- `test_connection.py` — The diagnostic script you should run first (see SETUP.md).
- `SETUP.md` — Detailed Windows setup and troubleshooting guide.

## Planned / Future Modules

- `build_timeline.py` — (implemented) Consumes a `video_plan.json` (or the episode project folder) and builds a timeline in Resolve with bins, tracks, clips laid out per scenes, and markers for lower thirds. This is the script referenced in the Podcast Parlay workflow. Run it while Resolve is open with your episode project active.
- Helpers for project template duplication, bin organization, Text+ population, etc.

## Current Status

See the design documents:

- [V2_RESOLVE_AUTOMATION_DESIGN.md](../../docs/V2_RESOLVE_AUTOMATION_DESIGN.md)
- [VISUAL_SPECIFICATION_v1.md](../../docs/VISUAL_SPECIFICATION_v1.md)
- [MEDIA_AND_GIT_STRATEGY.md](../../docs/MEDIA_AND_GIT_STRATEGY.md)

Timeline construction is now available via build_timeline.py (see usage below). The connection + low-level API foundation is solid; higher-level builders are being added incrementally.

**Orchestration & client approvals for the full Podcast Parlay (long-form + iterative review + captions + clips + YouTube):** See the executable workflow at `../../docs/PODCAST_PARLAY_FULL_WORKFLOW.md` and the Nathan-callable tools in `../../../app/tools/video_parlay_tools.py`. These wire the Resolve work into the ParlayVU approvals / Teams card / project memory system so clients review and iterate inside their existing channel.

## Usage Pattern (Future)

```powershell
# 1. Validate environment (do this first)
python tools/resolve/test_connection.py

# 2. Later, once the builder exists
python tools/resolve/timeline_builder.py `
    ..\projects\RamAir\Straight_From_The_Hart_Ep06 `
    --plan planning\video_plan_draft.json
```

Resolve **must** be running (with your episode project open) for build_timeline.py (or any automation) to work.

## Quick Start for Ep05 (or any episode) Right Now

1. Open DaVinci Resolve Studio.
2. Open/create a project for the episode (e.g. "Straight_From_The_Hart_Ep05").
3. Find your scripting Modules folder (search Explorer for `DaVinciResolveScript.py` — on your machine it was at `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`).
4. In a fresh PowerShell (repo root):
   ```powershell
   $env:RESOLVE_PYTHON_API = "C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"   # <-- your real path
   python video_system\tools\resolve\test_connection.py
   ```
5. Once the test passes:
   ```powershell
   python video_system\tools\resolve\build_timeline.py "video_system\projects\RamAir\Straight_From_The_Hart_Ep05"
   ```

**If you are stuck in the Script Console and cannot type:**

See the detailed troubleshooting in SETUP.md (the section about the console input box and the ARM emulation warning). The root cause is almost always using the non-native (emulated x64) Resolve on ARM hardware. Install the native ARM build of Resolve to make the console and external API fully functional.
6. In Resolve you now have a properly structured timeline built from the plan. Render your draft from the Deliver page into the episode's `renders/` folder, then tell the system (or Nathan) the new .mp4 so we can record the iteration and open the approval gate.

This is how we use Resolve for the Podcast Parlay as specified in the living workflow document.
