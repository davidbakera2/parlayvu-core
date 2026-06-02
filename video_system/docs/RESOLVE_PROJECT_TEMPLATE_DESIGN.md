# Resolve Project Template Design (v2)

**Status:** Draft — Phase 1
**Date:** 2026-05-29
**Owner:** David + Grok
**Goal:** Define a clean, portable, Resolve-native template that faithfully carries the visual language from the existing `ramair_interview` system while being easy to duplicate, version, and drive via scripts.

---

## 1. Why We Need a Dedicated Resolve Template

The old v1 system used:
- Static layout PNGs as mattes
- Python + PIL to generate lower third overlays at render time
- FFmpeg for all compositing

For v2 we are **not** replicating that mechanism inside Resolve. Instead, we will build a proper Resolve project template that encodes the same visual intent using native tools:

- Text+ and Fusion compositions for lower thirds and cards
- Proper timeline track architecture
- Media Pool organization
- Render presets
- Color management

This template becomes the **carrier of the visual system** and the foundation for all scripted automation.

---

## 2. Core Requirements

The template must satisfy these principles:

1. **Visual Fidelity** — Must be able to produce results that match (or exceed) the current lower thirds, b-roll cards, name cards, 1cam special treatment, branding plate behavior, and overall aesthetic defined in [VISUAL_SPECIFICATION_v1.md](./VISUAL_SPECIFICATION_v1.md).

2. **Resolve-Native** — Use Text+, Fusion, timeline tracks, compound clips, and the Deliver page. No reliance on pre-baked PNG overlays from the old Python code as the primary path.

3. **Portable & Git-Friendly** — The template (or the means to recreate it) must live in the repository and work when pulled on another machine.

4. **Scriptable** — The timeline builder must be able to:
   - Duplicate the master template
   - Import media into the correct bins
   - Populate Text+ elements with data from `video_plan.json`
   - Create consistent timeline structures

5. **Practical for Iteration** — Human editors (you + future collaborators) must find it comfortable to work in directly.

---

## 3. Proposed Template Structure

### 3.1 Location in Repo (Updated Architecture)

As of May 2026, we are moving to a cleaner multi-client model:

```
video_system/
├── templates/
│   ├── visual_systems/
│   │   └── parlayvu_interview/           # Reusable visual system (formerly ramair_interview)
│   │       ├── legacy/                   # Old layouts + styles (v1 reference)
│   │       ├── resolve/                  # The Resolve template (v2)
│   │       │   ├── master_project/
│   │       │   ├── fusion/
│   │       │   ├── render_presets/
│   │       │   └── README.md
│   │       ├── template_config.json
│   │       └── README.md
│   │
│   └── client_overrides/                 # Light per-client customizations
│       └── <client>/
│
```

**Important:** The old `templates/ramair_interview/` location is being phased toward the new `visual_systems/parlayvu_interview/` structure for better long-term organization across multiple clients. See `docs/VISUAL_SYSTEMS_AND_CLIENT_CUSTOMIZATION.md`.

### 3.2 What the Master Project Should Contain

#### Project Settings
- Resolution: 1920 × 1080
- Frame rate: 24 fps (or 23.976 — decide and lock)
- Color management: DaVinci YRGB Color Managed or ACES (recommendation needed)
- Timeline resolution and output blanking as needed

#### Media Pool Organization (Bins)
- `01_Camera` (host, guest_01, guest_02, multicam clips)
- `02_B-Roll`
- `03_Graphics` (show_image, logo_square, show_image_lower_third, name cards, b-roll cards)
- `04_Audio` (music, sound design cues, voice tracks)
- `05_Branding` (intro, show image stills, lower third plates)
- `06_Archive` (old versions, reference)
- Smart bins for "Lower Thirds", "B-Roll Cards", etc.

#### Timeline Structure (Master Timeline Template)
Recommended track layout:

- **V1** — Main program (interview + b-roll inserts)
- **V2** — Lower Thirds (Text+)
- **V3** — Name Cards & B-Roll Cards (Text+ / Fusion)
- **V4** — Additional graphics / callouts (optional)
- **V5+** — Reserved for complex effects or picture-in-picture
- **Audio 1** — Host
- **Audio 2** — Guest(s)
- **Audio 3** — B-Roll / Music bed
- **Audio 4** — Sound design / cues
- **Subtitles** — Caption track

Pre-populate one "Template Timeline" with:
- Proper track naming and colors
- Example Text+ lower third (top + bottom row) already styled
- Example b-roll card
- Markers showing "Lower Third zone", "Card zone"
- Notes on the timeline explaining the structure

#### Pre-Built Styles (Text+ / Fusion)

**Lower Thirds (two variants):**
- Standard lower third (full width bar)
- 1cam special framed version (with white border treatment)

These should be saved as:
- Text+ presets, or
- Reusable Fusion compositions that can be instantiated via the Effects Library or macros

**B-Roll Cards:**
- The navy + blue accent card style from the spec
- Right-aligned text, stacking behavior handled via timeline positioning

**Name Cards:**
- Semi-transparent black background with white bold text
- Placement variants (top_right, top_right_over_broll)

#### Render Presets (Deliver Page)
- `Draft_Proxy_H264` — Fast, lower bitrate for review
- `Final_Master` — High quality (ProRes or DNxHR)
- `Social_Vertical_9x16`
- `Social_Square_1x1`
- `YouTube_1080p`

---

## 4. Distribution & Portability Strategy

Options ranked by cleanliness:

**Recommended: Hybrid Approach (Best Balance)**

1. Store a **master project** (exported as `.drp` Project Archive when possible) inside the repo under `templates/visual_systems/parlayvu_interview/resolve/master/`.
2. Provide a small Python helper (`tools/resolve/create_from_template.py`) that:
   - Duplicates the master project into the target episode folder
   - Renames it appropriately
   - Optionally creates the standard bin structure if the archive doesn't preserve it perfectly
3. Document the manual "Duplicate Project" workflow for when scripting isn't used.

**Alternative: Purely Script-Driven**
- No full project file in git
- The timeline builder script creates everything from scratch every time (bins + timeline + starter Text+ elements)
- More flexible long-term, but higher initial development cost and less "what you see is what you get" for manual editing.

**Hybrid is preferred** for the first version because it lets you (the human editor) open a familiar, pre-styled project immediately.

---

## 5. Lower Thirds & Transitions Strategy (Updated)

The user has directed:
- Invest **early in Fusion compositions**.
- Prioritize **simpler and smoother** results over exact replication of the old static template.
- Lower thirds need **entry/exit motion** (wipe, slide, etc.).
- Scene transitions should use **box morphing** (video boxes move and transform between layouts rather than hard cuts).

**Recommended Approach:**

- Build lower thirds as **proper Fusion compositions** from the beginning (with built-in animation).
- Design scene transitions using **Compound Clips + Fusion** for smooth morphing.
- The old layout PNGs are now primarily reference material, not the core implementation method.

See the following documents for detailed implementation direction:
- `resolve/FUSION_LOWER_THIRD_SPEC.md` (node structure, controls, animation approach)
- `resolve/ANIMATED_TRANSITIONS_AND_MOTION.md` (overall motion philosophy and box morphing)

---

## 6. Locked Decisions (May 2026)

- **Frame rate**: 24.000 fps
- **Color Management**: DaVinci YRGB Color Managed (Rec.709 Gamma 2.4)
- **Overall philosophy**: Simpler and smoother. We are deliberately *not* trying to replicate the old static v1 template pixel-for-pixel if it creates unnecessary complexity.
- **1cam treatment**: We are comfortable simplifying the white border floating frame effect. We will build a clean version first and prototype the bordered version as an option so you can compare.

## Remaining Open Questions

- How ambitious should the box morphing transitions be in the first version?
- What specific entry/exit animations feel right for lower thirds (we'll prototype options in Fusion).

---

## 7. Next Actions (Proposed Sequence)

1. Finalize this design document with your input on the open decisions.
2. Create supporting implementation documents (done):
   - `resolve/BUILD_GUIDE.md` — Step-by-step guide to build the master project inside Resolve.
   - `resolve/TIMELINE_TRACK_LAYOUT.md` — Definitive track architecture.
   - `resolve/style_parameters.json` — Bridge between the Visual Spec and Resolve (Text+, positioning, colors).
3. Manually build the first version of the master project inside Resolve while following the BUILD_GUIDE.
4. Export it as a project archive into `resolve/master_project/`.
5. Document the duplication workflow.
6. Begin scripting support (timeline builder integration).

---

## 8. Relationship to Other Documents

- [VISUAL_SPECIFICATION_v1.md](./VISUAL_SPECIFICATION_v1.md) — The source of truth for what the template must visually achieve.
- [V2_RESOLVE_AUTOMATION_DESIGN.md](./V2_RESOLVE_AUTOMATION_DESIGN.md) — Overall architecture.
- [MEDIA_AND_GIT_STRATEGY.md](./MEDIA_AND_GIT_STRATEGY.md) — How this template must behave across machines.

---

This document should be the working spec while we build the actual template. We will iterate it as we learn what works best in Resolve 21.

---

**Ready for review and decisions on the open questions above.** Once we lock the high-level approach, we can start building the actual project inside Resolve.