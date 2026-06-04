# Video Production Runbook

## 1. Start A New Episode

Run:

```powershell
.	ools
ew_project.ps1 -Client "ClientName" -Show "Show_Name" -Episode "Ep01"
```

This creates:

```text
projects\ClientName\Show_Name_Ep01
```

## 2. Replace Project Assets

Put show/client-specific files in:

```text
projects\ClientName\Show_Name_Ep01ssets
```

Common replacements:

- `show_image.png`
- `show_image_lower_third.png`
- `logo_square.png`
- `intro.mp4`
- `music.wav`
- `host.mp4`
- `guest_01.mp4`
- b-roll files

## 3. Edit The Spreadsheet

Open:

```text
planningideo_plan.xlsx
```

Use `Scenes` for the edit, `Broll` for source clip mapping, `Graphics` for name cards and b-roll cards, `Assets` for branding, and `Settings` for project-level controls.

## 4. Validate And Convert

From the `video_system` folder:

```powershell
python .	oolsalidate_project.py .\projects\ClientName\Show_Name_Ep01 --template .	emplatesamair_interview	emplate_config.json
python .	ools\spreadsheet_to_json.py .\projects\ClientName\Show_Name_Ep01
```

## 5. Render

The next implementation step is to migrate the proven RamAir renderer into `toolsender_video.py` so it consumes `planningideo_plan.json`.

Until then, this system is the planning, styling, validation, and subtitle foundation.

**Full end-to-end process (including client approvals, iteration loops in Teams chat, captions round, YouTube unlisted + clips publishing):** See the living spec [docs/PODCAST_PARLAY_FULL_WORKFLOW.md](docs/PODCAST_PARLAY_FULL_WORKFLOW.md). It includes the exact Mermaid diagram, step-by-step with approval gates, how Nathan coordinates it, and how to evolve the workflow by editing this file + tools.
