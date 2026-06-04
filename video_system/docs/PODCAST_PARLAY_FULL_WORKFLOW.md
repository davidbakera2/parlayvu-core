# Podcast Parlay — Full Executable Workflow (Living Specification)

**Purpose:** This is the single source of truth for the complete Podcast Parlay process. It is designed to be:
- **Easy to view**: Mermaid diagram renders in GitHub, VS Code, Obsidian, etc.
- **Easy to develop and modify**: Edit this Markdown file (or the referenced plan JSONs/scripts). Changes are version-controlled and immediately available to Nathan via context loading.
- **Agent-executable**: Nathan (and specialists like Alex) are instructed to follow this document step-by-step. Tools in `video_system/tools/` + ParlayVU core (approvals, project memory, client_artifacts) make the steps actionable.
- **Client-visible where it matters**: Approvals and iteration happen inside the client's Teams channel using the existing ParlayVU approvals system (cards, "changes_requested", feedback notes).
- **Upgrade-friendly**: When you finish an episode and learn something ("we always forget end-card on first long-form upload"), update this file + the corresponding tool/prompt. No opaque graph state to untangle.

**Status:** v1 — Detailed from user requirements + current video_system + ParlayVU patterns (as of 2026-06).  
**Owner:** David (human) + Nathan (orchestrator) + Alex (visuals lead)  
**Related:** [podcast-parlay.md](../parlays/podcast-parlay.md) (high-level vision), [V2_RESOLVE_AUTOMATION_DESIGN.md](./V2_RESOLVE_AUTOMATION_DESIGN.md), video_system/projects/ structure, `app/approvals.py`, `app/nathan_llm.py` (tools), `client_artifacts/<client>/`.

---

## 1. High-Level Flow (Mermaid Visualization)

```mermaid
flowchart TD
    subgraph ingestion ["Ingestion"]
        A[Riverside Recording\nhost.mp4 + guest_01.mp4 + guest_02.mp4\n+ enhanced audio + timestamped transcript] --> B[Identify + export b-roll assets\nHuman drops into project/assets/]
    end

    subgraph planning ["Planning"]
        B --> C[Nathan + Alex: Load project context, transcript, brief\nDetermine intro section, overall structure, music placement\nPropose b-roll timing + lower thirds + layouts]
        C --> D[Update or generate planning/video_plan.json + .xlsx\nRun tools/new_project.py + validate + spreadsheet_to_json]
        D --> E[tools/resolve/build_timeline.py (or manual in Resolve)\nIncorporate music, branding, intro/outro per the plan]
    end

    subgraph video_assembly_draft ["Video Assembly Draft"]
        E --> F[Render proxy/draft video in Resolve (visuals, cuts, b-roll, lower thirds, music, intro/outro)\nOutput: renders/video_draft_v01.mp4 (temp or no final captions)]
        F --> G[Host preview (local path, temp upload, or YouTube unlisted draft)\nRecord in project memory]
    end

    subgraph captions_approval ["Captions Approval (Gate before final video production)"]
        G --> H[Generate / refine captions\nResolve captions track or make_template_subtitles.py + ASS/SRT from approved transcript/plan]
        H --> I[New captioned preview or captions file review + request_approval action_type=video_captions\nPost Teams Adaptive Card with preview/captions link + Approve/Reject/Request Changes]
        I --> J{Client / Human Decision in Teams?}
        J -->|Approved| K[Captions approved. Proceed to final video production with approved captions]
        J -->|changes_requested + feedback notes| L[Nathan reads decision_notes + prior plan + transcript\nDispatches Alex or calls edit tools: adjust caption text/timing/style, re-generate captions]
        L --> H
    end

    subgraph final_video_production ["Final Video Production + Approval"]
        K --> M[Incorporate approved captions into final Resolve timeline\nFinal color, audio polish, music integration, end card if applicable\nRender final long-form: renders/longform_final_v01.mp4]
        M --> N[Host final preview + request_approval action_type=video_production\nPost Teams Adaptive Card with final preview link + Approve/Reject/Request Changes]
        N --> O{Client / Human Decision in Teams?}
        O -->|Approved| P[Video production approved. Proceed to YouTube upload]
        O -->|changes_requested + feedback notes| Q[Nathan reads decision_notes + approved captions + plan\nDispatches Alex or calls edit tools: final tweaks in Resolve using approved captions as base]
        Q --> M
    end

    subgraph publish_long_form ["Publish Long-Form"]
        P --> R[Generate series-fitting thumbnail (template + episode specifics)\nCraft description from meeting notes + brief\nAdd appropriate end card]
        R --> S[Upload to YouTube via tool (stub today: yt CLI or API)\nSet unlisted, series metadata, playlist if applicable]
        S --> T[Record PublishedOutput + AgentEvent. Notify client]
    end

    subgraph clips ["Clips Phase 5-10 Shorts"]
        T --> U[Nathan + Alex: Scan transcript/plan for 5-10 high-value moments\nHook + key insight + CTA or brand moment]
        U --> V[Create clip sub-timelines or exports in Resolve\nApply captions per clip, consistent branding]
        V --> W[Render clip previews (individual + optional grid)\nPackage in renders/clips/ or temp hosted links]
        W --> X[request_approval action_type=clip_package\nTeams card(s) with links + Approve entire set / Request changes on specific clips]
        X --> Y{Client decision?}
        Y -->|Approved| Z[Per-clip: description, thumbnail variant, upload to YT, add to designated playlist]
        Y -->|iterate specific clips| V
    end

    Z --> AA[Mark episode complete in project memory + video project README\nCapture learnings for next Parlay upgrade]

    style A fill:#e1f5fe
    style I fill:#fff3e0,stroke:#ff9800
    style N fill:#fff3e0,stroke:#ff9800
    style X fill:#fff3e0,stroke:#ff9800
    style L fill:#f3e5f5
    style Q fill:#f3e5f5
    style S fill:#e8f5e9
    style Z fill:#e8f5e9
```

**Legend:**
- Orange boxes = Human approval gates (via existing ParlayVU Teams cards + `approvals` table).
- Purple = Iteration/revision loops (feedback notes drive re-work; state lives in plan + previous renders + AgentEvent).
- Green = Publish steps (side-effecting, always gated).
- Nathan is the persistent coordinator across all steps. He uses `get_project_context`, file tools, and new video tools. Alex (visuals) is the specialist for creative decisions on cuts, text, b-roll, thumbnails.

---

## 2. Detailed Step-by-Step (With Actors, Artifacts, Approvals, Iteration)

### Phase 0: Setup (Human + Nathan)
1. Complete interview in Riverside → export raw tracks + transcript (SRT/TXT/JSON with timestamps + speakers preferred).
2. Human (David) runs:
   ```powershell
   cd video_system
   python tools/new_project.py --client "RamAir" --show "Straight_From_The_Hart" --episode "Ep06"
   # or the .ps1 wrapper
   ```
   This scaffolds `projects/RamAir/Straight_From_The_Hart_Ep06/` with `assets/`, `planning/`, `renders/`, `previews/`, `PROJECT_README.md`, copy of starter `video_plan.xlsx`.
3. Drop assets:
   - `assets/host.mp4`, `guest_01.mp4`, `guest_02.mp4` (and any enhanced audio).
   - Identified b-roll files.
   - Branding: `show_image.png`, `show_image_lower_third.png`, `logo_square.png`, `intro.mp4`, `music.wav` (or client-specific overrides via `templates/client_overrides/`).
   - Optional: existing high-quality `.srt` into `planning/`.
4. Nathan is told (via Teams or `/nathan`): "Start Podcast Parlay for RamAir Straight_From_The_Hart Ep06. Raw files are in the project. b-roll is the duct cleaning footage from last week plus the new factory walk."
   - Nathan loads project via `get_project_context` (or direct file read on video project dir) + client config.
   - He (or Alex via dispatch) analyzes transcript for beats.

**State:** `video_project` folder + DB `Project` record (if using project_memory) + initial `AgentEvent`.

### Phase 1: Planning & First Draft Assembly (Nathan + Alex + Tools)
- Nathan/Alex propose:
  - Intro section (show image animation + host cold open or music bed).
  - Scene segmentation (use transcript timestamps + LLM for topic boundaries).
  - Layout choices per scene (1cam for host monologue, 2cam for dialogue, 2cam_broll or 3cam_broll when b-roll adds value).
  - Lower third text (speaker-aware, benefit/insight focused, brand voice from `00_Client_Brief` or prior episodes).
  - Precise b-roll placement + duration (human-provided b-roll files mapped by ID in plan).
  - Music ducking / sync points.
- Output: Update `planning/video_plan.xlsx` (or directly JSON) + run converters.
- Run Resolve integration:
  - `python tools/resolve/build_timeline.py <project_dir> --plan planning/video_plan_draft.json`
  - (Once implemented; currently hybrid with manual Resolve work + plan as guide.)
- Render proxy/draft (low bitrate or "Draft" render preset in Resolve Deliver page) to `renders/longform_draft_v01.mp4` (or versioned).
- Nathan confirms "Draft ready at <path or preview URL>".

**Artifacts:** `planning/video_plan.json`, `renders/...`, `AgentEvent`s for planning steps.

### Phase 2: Video Assembly Draft + Captions Approval (Captions Gate Before Video Production)
- After planning/assembly in Resolve:
  - Nathan triggers render of video assembly draft (visuals/cuts/b-roll/lower thirds/music focused, using temp or no captions yet): `generate_video_draft(..., stage="video_assembly_draft")`.
  - Preview the draft.
- Then generate/refine captions (Resolve track or `make_template_subtitles.py` + styles, or AI + Alex polish from transcript).
- Nathan calls: `request_video_approval(..., stage="video_captions", preview_url=..., summary="Captions for review on Ep06 draft.")`
  - Creates `Approval` record with action_type="video_captions".
  - Posts Teams card with captions preview (overlaid draft or .srt/.ass file link) + Approve/Reject/Request Changes.
- Client reviews captions (text + timing + style on preview).
- If **changes_requested**:
  - Feedback in decision_notes (e.g. "Slow down captions on the technical section at 04:12-04:45. Change 'Santa Jet package' to 'platinum disinfectant package'.").
  - Nathan loads notes + plan + transcript.
  - Dispatches Alex or edits captions via tool/script, re-generates preview.
  - Updates or new approval card.
- Loop until captions **Approved**.
- This is now the explicit gate: captions must be signed off before final video production.

**Why captions before video production approval:** Approving the content (captions are client-facing text/claims) early prevents expensive re-renders of the final polished video. The video production approval then confirms the full assembly with the *approved* captions baked in.

### Phase 3: Final Video Production + Approval
- Once captions approved:
  - Nathan triggers final video production: incorporate the *approved captions* into the Resolve timeline (dedicated captions track or burn), plus any final polish (color, Fairlight audio, exact music sync, end card).
  - Render the final long-form: `generate_video_draft(..., stage="video_production")` or equivalent final render command.
  - Produce final preview.
- `request_video_approval(..., stage="video_production", ...)` + card.
- Same iteration/feedback loop (now focused on final production aspects, knowing captions are already locked).
- Loop until "Approved".
- All iterations audited.

### Phase 4: Long-Form YouTube Publish (Gated)
- Approved video production (final with approved captions):
  - Nathan (or publishing specialist Riley) prepares:
    - Description: Pull from approved meeting notes, episode plan, client brief. Include timestamps if chapters, links, CTA.
    - Thumbnail: Use template (series-consistent) + episode-specific (guest photo, title treatment, number). Tool or Alex generates variants for quick choice.
    - End card: Standard series end card (subscribe, related episodes, website). Parameterized per show.
  - Tool: `publish_to_youtube_longform(project_dir=..., privacy="unlisted", playlist="Straight From The Hart", description=..., thumbnail_path=...)`
    - (Implementation: later integrate `google-api-python-client` + OAuth or service account. For now, the tool can output the exact command + metadata file for manual upload, or stub the record.)
  - Set unlisted.
  - Record in DB + project memory as `GeneratedOutput` (type="youtube_longform", uri= the YT link).
  - Notify client: "Long-form Ep06 (with approved captions) is up unlisted here: <link>. Ready for final review before public?"

### Phase 5: Clips (5-10 Shorts) Generation + Approval
- Nathan: "Clips phase for Ep06."
- Analyze (transcript + plan + approved video production notes) to pick 5-10 moments:
  - Strong hooks (first 10-15s of clip must grab).
  - Self-contained insights or stories.
  - Brand moments, calls-to-action, surprising facts.
  - Mix of 2cam dialogue, b-roll heavy, host direct-to-camera.
- For each:
  - Define sub-timeline (start/end relative to master).
  - Apply captions (often larger/bolder for shorts, vertical or 16:9 with safe areas) — using the already-approved captions as base where relevant.
  - Consistent branding (lower third or simplified, logo sting at end).
  - Music or sound design if short allows.
- Render individual clips + optional "review grid" (all 10 in one video or image strip).
- Package previews in `renders/clips/` or upload batch to a review folder / unlisted playlist.
- `request_approval(action_type="clip_package", metadata={"count": 8, "preview_grid_url": "...", "clips": [...]})`
  - Card allows bulk approve or "changes on clip 03 and 07".
- Iteration loop identical: feedback → targeted re-edit of specific clips (update plan or direct Resolve) → new previews → re-card or reply.

### Phase 6: Clips Publish
- Approved set:
  - Per clip: Generate tailored description (short hook + key quote + link to full episode + CTA).
  - Thumbnail variant (often face + big text overlay for shorts performance).
  - Upload each (tool supports batch).
  - Add each to the designated "Straight From The Hart Clips" or episode-specific playlist.
  - Record each as separate `GeneratedOutput`.
- Final notification + cross-post plan (Riley or Jordan for social).

### Phase 7: Close & Learn
- Nathan updates `PROJECT_README.md` with final links, timings, what worked.
- Records performance seeds if available (views later).
- "What should we change in the Parlay for next time?" discussion → edit this workflow doc + prompts + tools.

---

## 3. How to Easily Develop, View, and Manage / Upgrade This Workflow

**View:**
- Open this file in any Markdown viewer. The Mermaid at the top renders live (GitHub does it automatically on push; VS Code with Mermaid extension; Obsidian, Typora, etc.).
- For runtime view of a *specific episode*: Nathan can output (or a future `tools/visualize_parlay_status.py` can generate) a project-specific Mermaid showing completed steps, current pending approval, render versions, etc., based on files present + DB `Approval`/`AgentEvent` queries.
- Per-project `PROJECT_README.md` + `planning/video_plan.json` + `renders/` listing gives file-based "kanban".

**Develop / Modify (the key advantage over LangGraph Studio):**
- **This file is the spec.** To change the process (e.g., "always do a b-roll review gate right after planning before first render", or "add a mandatory end-card approval for clips", or "insert a 'client name pronunciation check' step"), edit the relevant section + the top Mermaid. Commit. Done.
- **Prompts:** Nathan's understanding lives in `app/agents/prompts.py` (NATHAN_BASE_SYSTEM and any parlay-specific additions) and `app/nathan_llm.py`. He is told to "load and follow `video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md` for any Podcast Parlay work, using the exact step names and gates." Update the prompt when the doc changes significantly.
- **Tools & Automation:** Heavy lifting is in editable Python:
  - `video_system/tools/new_project.py`, `spreadsheet_to_json.py`, `validate_project.py`, `make_template_subtitles.py`.
  - `video_system/tools/resolve/*.py` (the growing v2 layer — timeline builder, lower third population, etc.).
  - New tools we will add: `request_video_approval`, `render_draft`, `apply_plan_edit`, `generate_clips_from_plan`, `prepare_youtube_metadata`, `publish_youtube_video` (in `app/tools/video_parlay_tools.py` or directly callable from Nathan's tool loop).
  - These are plain functions/scripts. Test them standalone or by chatting with Nathan ("Use the video tool to init Ep07").
- **Approvals & Cards:** The iteration UI is the battle-tested Teams cards + `app/approvals.py` + handlers in `app/main.py` / `app/teams.py`. Extend `build_video_*_approval_card` functions for new stages (longform, captioned, clips). No need to change the graph.
- **State & Memory:** 
  - Episode folder = creative workspace (plan = intent, renders = versions).
  - ParlayVU `Project` + `GeneratedOutput` + `Approval` + `AgentEvent` = auditable cross-episode memory and client-visible status.
  - `client_artifacts/<client>/03_Deliverables/` or a `video/` subdir can mirror key finals + links.
- **Testing a change:** Run on a real or starter episode. Talk to Nathan in the internal `parlayvu` Teams channel ("Walk me through Podcast Parlay Ep06 using the current workflow doc"). Watch the cards appear, simulate client feedback, see the loops. Edit the md or a script and retry.
- **Scaling the team of agents:** Alex gets a dedicated prompt for visuals decisions. Future specialists (e.g., "Clip Strategist") get their slice. Nathan remains the single brain that knows the whole parlay and when to call whom or which tool.

**Why this is dramatically easier to manage than LangGraph Studio for this use case:**
- No hidden graph execution state that only Studio can inspect.
- The workflow is text + files + your existing approvals ledger — you (and future you or a teammate) can read it in a text editor at 2am.
- Iteration and client collaboration use the channel they already live in.
- Upgrades are literal diffs to this file + small Python changes. You can A/B a new step on one episode by branching the doc.
- The heavy creative work stays in the right tool (Resolve timeline for fine edits) while the orchestration, approvals, memory, and client loop stay in ParlayVU.

---

## 4. Immediate Next Implementation Steps (to make this live in Nathan)

1. **This document** (done — you are reading the result).
2. Add Nathan video tools (next code change):
   - `app/tools/video_parlay_tools.py` with functions: `init_or_load_video_project`, `run_draft_planning`, `render_video_draft`, `request_video_approval` (wraps core `request_approval` + posts card), `apply_feedback_to_plan`, `prepare_youtube_upload`, etc.
   - Wire them into `NATHAN_TOOLS` in `app/nathan_llm.py` and the execution handler (similar to the existing `dylan_generate_variations` handling).
   - Update `NATHAN_BASE_SYSTEM` (or add a loaded section) to reference this workflow doc for Podcast Parlay episodes.
3. Extend Teams cards for video approvals (`app/teams.py`).
4. Implement / stub the YouTube publish tool (metadata generation first, real upload second; use `scripts/` or a new module).
5. Enhance Resolve tools to support "render draft proxy" and "apply targeted edit from feedback".
6. Pilot on next real episode using the internal channel + a client tenant. Log everything back into memory.
7. Add a `tools/visualize_parlay_status.py` that, given a project dir + client_id, prints a live Mermaid "current state" diagram + open approvals.

Once the tools are wired, you can literally say to Nathan in chat: "Kick off the full Podcast Parlay for the new guest interview. I put the b-roll in assets/broll_factory_walk.mp4. Use the current workflow."

---

## 5. Open Questions & Evolution Hooks

- Preview hosting: Local path for internal? Temp YouTube unlisted for client review? Dedicated Cloudflare "video-previews" bucket with expiring links? (Dylan site previews show the pattern.)
- Clip count & selection: Hard 5-10 or "up to 12 high-value moments under 60s"?
- Vertical shorts vs horizontal? (Many clients want both.)
- Music licensing / client-provided vs ParlayVU library?
- Performance feedback loop: Later, add a tool that ingests YT analytics and updates client prefs / prompt examples ("clips with face + text overlay in first 3s performed 2x").
- Resolve project sharing across machines (see MEDIA_AND_GIT_STRATEGY.md — plan is portable, .drp archives or network project for the .drp database).

Update this document after every pilot episode with concrete learnings. That is how the Parlay gets smarter.

---

*This file + the video_system/tools/ + ParlayVU approvals + Nathan's tool loop = your easily editable, visualizable, client-integrated, upgradeable Podcast Parlay operating system. No Studio required.*

Next: Let's implement the first tool stubs and prompt updates so you can start using it immediately. Tell me which episode to pilot on or which tool to build first.
