# Video System v2 — Resolve + AI Automation Design

**Status:** Draft — Phase 0 (Planning & Specification)
**Date:** 2026-05-27
**Owner:** David + Grok
**Goal:** A clean, maintainable, high-quality evolution of the existing video production system that leverages DaVinci Resolve as the primary editing environment while adding strong AI assistance for the first draft.

---

## 1. Why v2? (Problem Statement)

The current system (v1) is powerful:

- Excellent visual consistency via `templates/ramair_interview/` (layouts, lower thirds, b-roll cards, name cards, subtitles).
- Deterministic FFmpeg-based renderer in `tools/render_video.py`.
- Rich planning model (`video_plan.xlsx` → `video_plan.json`).

**Core limitations for scaling:**

- Creating the first draft is labor-intensive (manual or near-manual scene-by-scene planning in the spreadsheet).
- Iteration is slow: every trim, text change, or layout tweak requires editing the plan + full re-render.
- No native NLE timeline for fine creative work (color, audio, pacing, last-mile graphics).
- The custom compositor, while precise, is hard to extend and does not benefit from Resolve's professional toolset.

**v2 Objective:**

Produce a **strong, on-brand first draft** automatically (AI segments + layout choices + generated lower thirds), then perform the majority of creative iteration inside a proper DaVinci Resolve timeline. The existing visual system is preserved and becomes the reference specification.

We move fast on the boring parts, slow and deliberate on the creative parts.

---

## 2. Architecture Principles (Non-Negotiable)

These principles guide every decision:

1. **Visual Fidelity First**
   - The existing `templates/ramair_interview/` (layouts PNGs + style JSONs + renderer logic in `make_overlay` / `make_broll_card` etc.) is the **authoritative visual specification**.
   - Any Resolve implementation must be able to match the current look to a high degree of precision before we declare it production-ready.

2. **Planning Layer = Intent; Resolve Timeline = Realization**
   - `video_plan.json` (and its spreadsheet source) remains the machine-readable "creative intent" document.
   - The Resolve timeline is the editable realization of that intent.
   - Changes in Resolve can (optionally) be exported back to an updated plan for reproducibility.

3. **AI for Acceleration, Not Replacement**
   - AI (transcription + segmentation + text generation + layout suggestions) is used aggressively for the **initial draft only**.
   - All final creative decisions remain with the human operator + collaborative review with Grok.
   - The system must make it easy to override or ignore AI suggestions.

4. **Resolve-Native Implementation (No Shoehorning)**
   - Resolve is used as a first-class native platform using its own tools (Text+, Fusion, multicam clips, timeline structure, Media Pool, Deliver page, etc.).
   - We do **not** attempt to port or emulate the v1 FFmpeg + PIL compositor logic inside Resolve.
   - The visual language (lower thirds, layouts, b-roll cards, branding treatment, 1cam special case, etc.) is preserved with high fidelity. The old *implementation mechanism* is deliberately left behind.

5. **Resolve is the Primary Creative Environment for New Work**
   - New episodes use Resolve for assembly, trimming, color, Fairlight audio, final graphics, and delivery.
   - The old FFmpeg renderer is preserved for existing projects during transition and as a supporting tool for narrow tasks (proxies, certain normalization, legacy compatibility). It is not the target for new development.

6. **Clean Separation & Extensibility**
   - New code lives in well-named modules (`tools/resolve/`, `tools/ai/`).
   - The core template stays untouched unless we deliberately evolve the visual language.
   - Existing projects and the old render path must continue to work without modification.

7. **Documentation & Reproducibility**
   - Every significant component has clear docs.
   - A new project can be taken from raw assets to locked picture by following a documented runbook.
   - The system is understandable by a future maintainer (or future Grok).

8. **Pragmatic Hybrid When Beneficial**
   - We are not religious about "everything in Resolve."
   - If certain narrow tasks are better served by FFmpeg (fast proxies, loudness normalization, legacy renders), we use the right tool for the job without compromising the primary Resolve-native path.

---

## 3. Target User Workflow (Ideal State)

### New Episode — First Draft (Target: < 45 minutes to first Resolve timeline)

1. `new_project.ps1 -Client "RamAir" -Show "Straight_From_The_Hart" -Episode "Ep06"`
2. Drop raw assets into `assets/` (host, guest_01, intro, show_image*, logo_square, music, b-roll, optional transcripts).
3. (Optional) Drop any existing high-quality `.srt`/`.txt` into `planning/`.
4. Run: `python tools/generate_draft_plan.py projects/RamAir/Straight_From_The_Hart_Ep06`
   - Produces `planning/video_plan_draft.json` + summary report.
   - Optionally updates `video_plan.xlsx` for human review.
5. Review/adjust the draft plan (or let it be aggressive on first pass).
6. Run: `python tools/resolve/build_timeline.py projects/RamAir/... --plan planning/video_plan_draft.json`
   - Resolve must be running.
   - Creates (or uses) a project from the Resolve template.
   - Imports media into organized bins.
   - Builds timeline with:
     - Proper cuts / multicam angles per segment.
     - Lower third Text+ generators populated with AI-generated text.
     - B-roll inserts and cards where suggested.
     - Intro / show image / outro bookends.
     - Markers for "AI suggested review points".
7. Deliver a quick draft render from Resolve (proxy quality) to `renders/draft_v01.mp4`.

### Iteration Phase (The Real Power)

- You watch sections in Resolve.
- We discuss specific fixes in chat ("Tighten the cut between S007 and S008 by 4 frames", "Rewrite the bottom lower third on the 2cam_broll segment about negative pressure to be more benefit-focused", "Add a name card for the guest at 07:12 using the new title from the brief").
- I produce either:
  - Direct instructions you execute in Resolve, or
  - A small script / patch to the plan that applies the change via the Resolve API, or
  - Updated lower-third text + timing that you can paste.
- Major picture locks happen via direct timeline editing (J/L cuts, ripple, slip, etc.).
- Minor text/graphic tweaks can be driven from the plan or directly in timeline.

### Final Delivery

- Color grade (often per-section or using groups).
- Fairlight audio polish + music integration.
- Final subtitles (Resolve captions track, exported to multiple formats).
- Deliverables via Deliver page render presets (master, web, social cuts, vertical, etc.).

---

## 4. System Components (High-Level)

### 4.1 Planning & AI Layer (New)

- `tools/generate_draft_plan.py`
  - Transcription engine (local first choice: faster-whisper or WhisperX for word-level + basic speaker).
  - Segmentation + reasoning module (prompts + logic that calls Grok or a local model).
  - Layout suggestion engine (rules + LLM judgment).
  - Lower third text generator (speaker-aware, topic summarization, style enforcement).
  - B-roll / graphic opportunity detector.
  - Output: structured `video_plan_draft.json` compatible with existing schema + human report.

- Optional: `tools/ai/` package for reusable prompt templates, transcription wrappers, etc.

### 4.2 Resolve Integration Layer (New)

- `tools/resolve/resolve_api.py` — robust connection helper + common operations (get project, create timeline, import media, apply text to generator, etc.). Handles Windows path quirks and multiple discovery methods.
- `tools/resolve/timeline_builder.py` — the main script that consumes a plan JSON and constructs the timeline.
- `tools/resolve/project_template/` or a documented "Master Project" that users duplicate (contains pre-built timeline structure, Text+ lower third macros/compositions, render presets, bins, etc.).

### 4.3 Template Evolution

- `templates/visual_systems/parlayvu_interview/` (formerly `ramair_interview`) remains the reference visual system.
- The Resolve template lives under `templates/visual_systems/parlayvu_interview/resolve/`.
  - The Resolve project template assets.
  - Exported Fusion compositions for complex lower thirds / cards (if we go beyond Text+).
  - A `visual_spec.md` that precisely documents measurements, colors, timings, and behaviors extracted from the v1 renderer.

- Long-term: we may generate the Resolve lower third styles programmatically from the existing `styles/*.json` files so there is one source of truth.

### 4.4 Compatibility & Migration

- Old renderer, `spreadsheet_to_json.py`, `validate_project.py`, etc. continue to work unchanged.
- Existing projects are untouched.
- New flag or separate render path for "Resolve-backed" projects.
- Future bridge tool: "Export current Resolve timeline state back to video_plan.json" (for reproducibility or handoff to the old renderer).

### 4.5 Supporting Tooling

- Enhanced `new_project.py` that can optionally scaffold Resolve template elements.
- Preview / QA frame tools updated to work with Resolve timelines (or export stills from Resolve).
- Runbook updates (`RUNBOOK.md` and per-project `PROJECT_README.md`).

---

## 5. Key Technical Challenges & Proposed Approaches

### 5.1 Faithfully Recreating the Visual System in Resolve

**Lower Thirds (the hardest and most important part):**

Current v1 behavior (from `render_video.py:make_overlay` + `lower_third.json`):
- Dark navy bar (#062442) across bottom with left branding image + right logo square.
- Top row: bold white Arial ~38pt, centered in upper portion of the bar.
- Bottom row: bold black Arial ~56pt on white background in lower portion.
- Special 1cam treatment (smaller framed lower third with white border treatment).
- B-roll cards: specific navy rounded rectangle with blue accent, right-aligned white text, positioned top-right with stacking.

**Resolve approaches (ranked):**

A. **Text+ on dedicated video track + background plate** (recommended starting point)
   - Use one of the layout PNGs (upscaled) as a background "matte" with transparent holes.
   - Position and crop camera/b-roll sources into the holes using precise resize + crop + position on multiple video tracks.
   - Use Text+ generators for the two rows of the lower third, styled to match.
   - Advantage: very close to current compositor model; easy to drive from script.

B. **Pure Fusion Title macro / compound clip**
   - Build a reusable Fusion composition that contains the entire lower third + branding plates + text.
   - Instantiate via Text+ or a saved macro on the timeline.
   - More powerful animation potential.

C. **Hybrid**: Pre-render complex lower third plates (with branding images) as transparent PNG sequences or MOVs from the existing Python code, then composite simple text + video in Resolve. Good for v1 parity during transition.

We will prototype A first, then evaluate fidelity vs. editability.

### 5.2 Multicam & Layout Switching

- Best practice: Create a **Multicam clip** from the primary sources (host + guest_01 + guest_02) synced on common audio or timecode.
- In the timeline, cut between angles or use the multicam viewer.
- The AI plan can suggest "use angle X for this segment" or "use 2cam layout".
- For b-roll heavy segments, we can have dedicated tracks or use the "b-roll" source as an additional angle or as an overlay track.

### 5.3 Resolve Python API on Windows (Practical Reality)

From initial investigation:
- `DaVinciResolveScript` is not on the default Python path.
- Common working pattern: Resolve must be **running**. Script does `sys.path.insert(...)` pointing at the correct Modules folder (location varies by Resolve version and install type).
- Reliable discovery order we will implement:
  1. Environment variable `RESOLVE_PYTHON_API`.
  2. Common Windows install paths + `Developer/Python/Modules`.
  3. `%PROGRAMDATA%\Blackmagic Design\...`
  4. Fallback with clear error + setup instructions.

We will create a small test script early (`tools/resolve/test_connection.py`) that users run while Resolve is open.

### 5.4 AI Segmentation Quality

Success criteria for first-draft AI:
- Segments feel "mostly right" (not perfect) — good topic boundaries, reasonable length.
- Lower thirds are 80%+ usable as starting points (correct speaker, reasonable topic phrasing).
- Layout suggestions are directionally correct (>70% of the time).

We will iterate the prompts and post-processing rules aggressively using real episodes (Ep04/Ep05 are excellent test material).

Transcription quality is foundational. Local Whisper (large-v3 or turbo) + word-level timestamps via WhisperX or stable-ts is the target for privacy and cost.

---

## 6. Phased Implementation Roadmap

**Phase 0 — Foundation & Specification (Current)**
- This design document.
- Detailed visual spec extraction from v1 renderer + templates.
- Resolve API connection research + test harness on this machine.
- Project scaffolding (`docs/`, `tools/resolve/`, updated folder conventions).
- Architecture review with user.

**Phase 1 — AI Draft Planner (Standalone)**
- Transcription + basic segmentation.
- Lower third text generation (top + bottom) with style enforcement.
- Simple layout suggestion rules.
- Output of a usable `video_plan_draft.json`.
- Human review report.
- Test on 1–2 existing episodes; measure quality.

**Phase 2 — Minimal Resolve Timeline Builder**
- Robust `resolve_api.py`.
- Ability to create a timeline, import media into bins, add basic clips with cuts.
- Drive simple Text+ lower thirds from plan data.
- End-to-end: assets → draft plan → Resolve timeline with 3–5 segments + lower thirds.
- First draft render from Resolve.

**Phase 3 — Visual Fidelity & Layouts**
- Implement the multi-box camera + b-roll layouts using the layout PNGs or equivalent cropping logic.
- Recreate lower third plate + branding assets + b-roll cards to high visual match.
- Name cards on the style defined in `name_cards.json`.
- Handle 1cam special case.

**Phase 4 — Full Draft Automation + Iteration Tools**
- Complete layout + b-roll suggestion logic.
- Markers and notes for AI suggestions.
- Basic iteration helpers (e.g., "update lower third text for scene S012").
- Audio cue handling from the existing plan schema.
- Updated runbooks.

**Phase 5 — Polish, Bridges & Production Hardening**
- Color / Fairlight best practices for this template.
- Export timeline state back to plan JSON (optional).
- Proxy workflow guidance for long episodes.
- Performance & reliability hardening.
- Final documentation + training material.

We proceed one phase at a time, with review gates. No gold-plating.

---

## 7. Open Questions & Decisions Needed (Early)

1. **Transcription engine priority**: Local Whisper (faster-whisper + torch) vs. OpenAI API vs. leveraging whatever transcripts come from the recording platform (Riverside, etc.). Recommendation: local for long-form client work.

2. **Resolve template distribution**: Do we ship a `.drp` file inside the repo, or document "duplicate this master project" + provide a script that configures it? (Leaning toward documented master + automation script.)

3. **Lower third implementation path for v1 parity** (see 5.1): Start with Text+ + background plate, or invest early in a Fusion composition? We can decide after Phase 2 prototype.

4. **Multicam vs. manual track layout**: Default to creating a Multicam clip for the main interview sources, with b-roll handled on separate tracks?

5. **Versioning of the visual template**: When we create the Resolve version, do we bump the template name (e.g., `ramair_interview_v2`) or keep it under the same name with internal versioning?

These can be resolved as we work through the phases.

---

## 8. Success Metrics (How We Know It's Working)

- Time from raw assets to first usable Resolve timeline: target < 60 min (including AI + one human review pass).
- Lower third text acceptance rate on first draft: > 70% of lines need only minor edits.
- Visual match to v1 renderer on equivalent scenes: side-by-side review shows no embarrassing differences at normal viewing distance.
- Iteration speed: a "change this lower third text and tighten two cuts" request can be executed and re-rendered in < 10 minutes.
- Existing projects continue to render exactly as before.
- A new operator can follow the runbook and produce a complete episode with only light guidance.

---

## 9. Next Immediate Actions (After This Document is Approved)

1. Complete visual specification capture (extract exact colors, positions, timings, 1cam special handling, b-roll card geometry from `render_video.py` and style JSONs into `docs/visual_specification.md`).
2. Locate and validate a working Resolve Python API connection method on this exact machine + document the setup steps.
3. Create the initial directory structure and stub files for `tools/resolve/`.
4. Choose and prototype the transcription + first segmentation approach on a 5–10 minute section of an existing episode.
5. Review and lock Phase 0/1 scope with user.

---

**End of Design Document v0.1**

This is a living document. Update it as we make decisions and learn from prototypes. Do not start major implementation until the relevant section has been reviewed.