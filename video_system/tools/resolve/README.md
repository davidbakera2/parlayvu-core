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

- `timeline_builder.py` — Will consume a `video_plan.json` and build a timeline in Resolve.
- Helpers for project template duplication, bin organization, Text+ population, etc.

## Current Status

See the design documents:

- [V2_RESOLVE_AUTOMATION_DESIGN.md](../../docs/V2_RESOLVE_AUTOMATION_DESIGN.md)
- [VISUAL_SPECIFICATION_v1.md](../../docs/VISUAL_SPECIFICATION_v1.md)
- [MEDIA_AND_GIT_STRATEGY.md](../../docs/MEDIA_AND_GIT_STRATEGY.md)

We are still in the careful foundation phase. No timeline construction code yet.

## Usage Pattern (Future)

```powershell
# 1. Validate environment (do this first)
python tools/resolve/test_connection.py

# 2. Later, once the builder exists
python tools/resolve/timeline_builder.py `
    ..\projects\RamAir\Straight_From_The_Hart_Ep06 `
    --plan planning\video_plan_draft.json
```

Resolve **must** be running for any of this to work.
