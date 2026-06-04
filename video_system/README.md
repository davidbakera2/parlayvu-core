# Video System

This folder is the reusable rendering system for interview, podcast, webinar, and client thought-leadership videos.

## Core Idea

- `templates` define reusable layouts and styles.
- `projects` contain client/show-specific source files, graphics, spreadsheets, captions, previews, and final renders.
- `tools` convert the spreadsheet into JSON, validate project assets, generate styled subtitles, and render videos.

## Standard Workflow

1. Copy `projects/_starter_project` to a new client/show folder.
2. Replace files in the new project's `assets` folder.
3. Edit `planning/video_plan.xlsx`.
4. Run `tools/validate_project.py`.
5. Run `tools/spreadsheet_to_json.py`.
6. Render previews and QA frames.
7. Render final no-subtitles and final with-subtitles versions.

The standard timing model is `full_rendered`: spreadsheet `start` and `end` times match the final video you review, including intro, opening show image, interview, and outro. Use `source_start` only when a scene needs to begin at a specific point inside `host.mp4`, `guest_01.mp4`, or another source file.

## Useful Commands

Create a new project:

```powershell
.	ools
ew_project.ps1 -Client "RamAir" -Show "Straight_From_The_Hart" -Episode "Ep02"
```

Validate a project:

```powershell
python .	oolsalidate_project.py .\projects\RamAir\Straight_From_The_Hart_Ep02 --template .	emplatesamair_interview	emplate_config.json
```

Convert spreadsheet to JSON:

```powershell
python .	ools\spreadsheet_to_json.py .\projects\RamAir\Straight_From_The_Hart_Ep02
```

Generate styled subtitles:

```powershell
python .	ools\make_template_subtitles.py .\projects\RamAir\Straight_From_The_Hart_Ep02\planning\captions.srt .\projects\RamAir\Straight_From_The_Hart_Ep02\planning\captions.ass --style .	emplatesamair_interview\styles\subtitles.json
```

## Client Branding

For most clients, swap only:

- `assets/show_image.png`
- `assets/show_image_lower_third.png`
- `assets/logo_square.png`
- `assets/intro.mp4`
- `assets/music.wav`
- source camera files and b-roll files

The template stays the same unless the client needs a genuinely different visual system.

## Background Video Style

Set `background_video` on the workbook `Settings` tab to a file in the project `assets` folder, such as `background.mov` or `background.mp4`.

The renderer treats this as a standard full-screen style layer: it loops for the full program, fills the entire 1920x1080 frame, and crops overflow as needed. It will show through the transparent areas around and between camera/b-roll boxes.

---

## v2 Development (Resolve + AI Automation)

We are building a cleaner, more automated system that uses **DaVinci Resolve** as the primary NLE for editing and delivery, while adding strong AI assistance for the initial draft (automatic segmentation, layout selection, and lower-third generation).

This is being built **natively for Resolve** (no shoehorning of the old FFmpeg compositor) and as a proper part of the broader **Podcast Parlay** inside the ParlayVU system.

**Key documents:**
- `docs/V2_RESOLVE_AUTOMATION_DESIGN.md` — architecture, principles, roadmap.
- `docs/VISUAL_SPECIFICATION_v1.md` — the visual language contract (what we must match).
- `docs/MEDIA_AND_GIT_STRATEGY.md` — how to keep this portable across machines via GitHub.
- `docs/VISUAL_SYSTEMS_AND_CLIENT_CUSTOMIZATION.md` — how we organize visual systems for multiple clients + light customization model.
- `tools/resolve/SETUP.md` — **Start here** for getting Resolve Python scripting working on Windows.

**Current status:** Careful foundation phase. Git/media strategy and basic Resolve scaffolding are in place. Next gate is validating the scripting API on this machine.

The v1 FFmpeg renderer and all existing projects continue to work unchanged.

See `tools/resolve/README.md` + `tools/resolve/SETUP.md` for the new integration code.

**Full Podcast Parlay workflow (the complete client-facing process with approvals, iteration via Teams, long-form + clips, YouTube delivery):** Read and follow [docs/PODCAST_PARLAY_FULL_WORKFLOW.md](docs/PODCAST_PARLAY_FULL_WORKFLOW.md). This is the single editable source of truth with Mermaid visualization. Nathan and the team are wired to treat it as the operating manual. Edit it to upgrade the process.
