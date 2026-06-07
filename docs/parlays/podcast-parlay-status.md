# Podcast Parlay — Working Status & Handoff

Snapshot for resuming after a context reset. Durable architecture is in
[podcast-parlay.md](./podcast-parlay.md), [podcast-parlay-runbook.md](./podcast-parlay-runbook.md),
and [podcast-parlay-build-plan.md](./podcast-parlay-build-plan.md). This file tracks the
*current in-flight episode and the open punch-list*.

## Where things stand
The Podcast Parlay runs end-to-end: transcript → Blake/Alex planning → Show Kit merge →
FFmpeg render. A full RamAir EP05 has been rendered several times and is being polished.
Branch: **`feat/podcast-parlay-planning`** (PR #2). All code committed.

## System map (code)
- `app/agents/workflows/podcast_parlay.py` — Blake (segments) → Alex (program scenes) graph; `run_podcast_parlay_planning(...)`.
- `app/agents/workflows/podcast_show_kit.py` — `load_show_kit`, `merge_with_show_kit`, `build_broll_manifest`, `format_camera_roster`.
- `app/agents/workflows/podcast_broll.py` — vision auto-description + `correct_broll_entry` (chat learning loop), `generate_broll_manifest`.
- `app/services/podcast_render.py` — `render_project` / `render_episode` (wraps the renderer).
- `video_system/tools/render_video.py` — the FFmpeg renderer.
- `video_system/templates/visual_systems/parlayvu_interview/` — Show Kit: `show_kit.json` (format, music, editing_style, known_terms, show_name) + `legacy/` template (layouts/styles).

## Current episode
- Project dir: `client_artifacts/ramair/03_Deliverables/podcast/straight-from-the-hart-test/` (gitignored).
  - `assets/` — real media + `broll.json` (vision descriptions; some `source:corrected`).
  - `planning/` — `transcript.srt`, `transcript.rebased.txt`, `video_plan.json`, `segment_analysis.json`, `show_notes.md`.
  - `renders/final_no_subtitles.mp4` — latest cut.
- **Trim offset:** trimmed cameras start at transcript **00:22:01.869** (last "Welcome to Straight from the Hart"). `transcript.rebased.txt` is already offset+trimmed (0:00 = footage start). Cameras are 2153.5s, perfectly synced.
- **Camera mapping (authoritative):** host = David Baker (Host); guest_01 = David Hart (Founder & CEO, RAM AIR International); guest_02 = John Miles (Chief Science Officer, Superstratum Labs).
- **B-roll corrections (in broll.json, source=corrected):** broll_03 = Superstratum (John's company); broll_07 = CIRI journal cover (show before article); broll_08 = the article; broll_09/10/11 = report pages (show in sequence).
- **Planning run:** needs `ANTHROPIC_API_KEY` (+`XAI_API_KEY`) in `.env`. Re-runs use Sonnet for both Blake+Alex via a `_agent_llm` monkeypatch in the run scripts.

## OPEN PUNCH-LIST (from latest review)
1. **Template render bug** — layout PNGs are 1280×720, renderer is 1920×1080 → thin black line around boxes + cameras don't fill tightly. Fix: regenerate layouts at **1920×1080** (preferred) OR overscan cameras in `render_program`.
2. **Low-res lower-third art** — `show_image_lower_third.png` (141×94) and `logo_square.png` (93×93) upscale to ~212×140 / ~139×140 → blurry. Need **hi-res source images** (~2–3×).
3. **Show notes** — `planning/show_notes.md` (EP05) should feed Blake/Alex as **LOOSE** context (topics/terms/names for lower-thirds), NOT a tight structure — the real conversation diverged.
4. **Re-allow 2cam** — `show_kit.json` editing_style currently says "avoid 2cam"; relax it (2cam host+the speaking guest is fine; e.g. 1:04 should be 2cam host+guest_01).
5. **Host lower-third** — clean to just "DAVID BAKER | HOST" (drop the redundant show name).
6. **B-roll** — re-describe the new `broll_02` image (replaced in assets); **exclude `broll_05`** (add a usage="exclude" path that `build_broll_manifest` filters).
7. **Rename** the project slug `straight-from-the-hart-test` → `ep05` (and use it as the episode title).
8. Then **re-run the planner** (with show_notes + 2cam + corrected b-roll) and **re-render** — but only AFTER the template geometry fix (#1) so we don't render 30+ min twice.

## To resume
Read this file + the project dir. Confirm `.env` keys. Address #1/#2 (assets/template) with
David, then re-run planning and render.
