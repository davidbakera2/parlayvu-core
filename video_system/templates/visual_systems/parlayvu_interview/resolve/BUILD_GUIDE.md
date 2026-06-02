# parlayvu_interview — Master Resolve Project Build Guide

**Goal:** Create the first version of the reusable Resolve Project Template that faithfully reproduces the visual language defined in the Visual Specification.

This guide is designed to be followed inside DaVinci Resolve. Work through it step by step.

---

## 1. Project Creation & Settings

1. Open DaVinci Resolve.
2. Create a **new project** named: `ParlayVU_Interview_Template_v1`
3. Go to **Project Settings** and configure:

   **General**
   - Timeline resolution: 1920 × 1080
   - Timeline frame rate: **24.000 fps** (locked)
   - Timeline start timecode: 01:00:00:00 (standard)

   **Color Management** (locked)
   - **DaVinci YRGB Color Managed**
   - Timeline color space: Rec.709 Gamma 2.4
   - Output color space: Rec.709 Gamma 2.4

   **Master Settings**
   - Video monitoring: HD 1080p 24

4. Save the project.

---

## 2. Media Pool Structure (Create These Bins)

Create the following top-level bins in the Media Pool (right-click → New Bin):

```
01_Camera
02_B-Roll
03_Graphics
04_Audio
05_Branding
06_Templates
07_Archive
```

### Recommended Sub-bins

**01_Camera**
- Host
- Guest_01
- Guest_02
- Multicam_Clips

**03_Graphics**
- Lower_Thirds
- Name_Cards
- Broll_Cards
- Callouts

**05_Branding**
- Show_Images
- Logos
- Lower_Third_Plates
- Intros

**06_Templates**
- Timeline_Templates
- Text+_Presets
- Fusion_Comps

---

## 3. Timeline Track Architecture

Create a new timeline called **"Template_Timeline"**.

Recommended track layout:

| Track Type | Name                  | Purpose                                      | Notes |
|------------|-----------------------|----------------------------------------------|-------|
| Video 1    | V1_Program            | Main interview + b-roll inserts              | Primary video |
| Video 2    | V2_Lower_Thirds       | Speaker name/title + topic text              | Text+ or Fusion |
| Video 3    | V3_Graphics_Cards     | Name cards + b-roll cards                    | Text+ / Fusion |
| Video 4    | V4_Additional         | Optional callouts, logos, etc.               | Reserved |
| Audio 1    | A1_Host               | Host camera audio                            | |
| Audio 2    | A2_Guest              | Guest camera audio                           | |
| Audio 3    | A3_Broll_Music        | B-roll nat sound + music bed                 | |
| Audio 4    | A4_SoundDesign        | Sound design cues, stingers                  | |
| Subtitles  | Subs                  | Captions track                               | |

### Track Color Recommendations (for clarity)
- V1: Blue
- V2: Orange (lower thirds)
- V3: Green (cards/graphics)
- Audio tracks: Standard colors

---

## 4. Lower Third Implementation (Fusion-First Approach)

**Updated Direction:** We are investing early in **Fusion compositions** for lower thirds. This gives us proper entry/exit animation (wipe, slide, morph, etc.) and much smoother results.

**Primary Reference:**
`FUSION_LOWER_THIRD_SPEC.md` — Detailed node structure, controls to expose, and animation approach.

See also: `ANIMATED_TRANSITIONS_AND_MOTION.md` for the overall motion philosophy.

### Lower Third Strategy

- Build the complete lower third (bar + two text rows + branding plates) as a **reusable Fusion composition**.
- The composition should include built-in entry and exit animations.
- Expose clean controls: Top Text, Bottom Text, Show/Hide Branding, Animation In/Out triggers.
- The 1cam special framed treatment can be a switchable mode inside the same composition.

### Lower Third Construction (Standard Version)

Create two Text+ generators on V2:

#### Top Row (Speaker / Title)
- Font: Arial Bold
- Size: ~38–42 pt (adjust to match visual spec)
- Color: White (#FFFFFF)
- Background: Dark navy bar (we will create this via a solid generator or still image plate)
- Alignment: Centered
- Case: Uppercase

#### Bottom Row (Topic)
- Font: Arial Bold
- Size: ~52–58 pt
- Color: Black (#000000)
- Background: White plate
- Alignment: Left-aligned within the text area
- Case: Uppercase

**Branding Plates (Left & Right)**
- Use still images from `05_Branding/Lower_Third_Plates`
- Position them on V2 or a dedicated sub-track
- Match the exact placement from the Visual Specification (see `legacy/` reference images)

### 1cam Special Treatment
- Create a separate Text+ preset or compound clip that includes the white border frame treatment around the lower third area.
- This can live in `06_Templates/Lower_Thirds/1cam_Special`

---

## 5. B-Roll Cards & Name Cards

**B-Roll Cards**
- Style: Dark navy background with blue right accent bar
- Text: Right-aligned, white main line + light blue secondary line
- Create as Text+ (or Fusion) generators
- Store reusable versions in `06_Templates/Broll_Cards`

**Name Cards**
- Semi-transparent black background
- White bold text
- Create 2–3 variants (standard, executive, etc.)

---

## 6. Render Presets (Deliver Page)

Create and save the following render presets:

1. **Draft_Proxy** — H.264, 1920x1080, Medium quality, fast encode
2. **Final_Master** — High quality (ProRes 422 HQ or DNxHR HQ)
3. **Social_Vertical_1080x1920** — 9:16 vertical
4. **Social_Square** — 1:1

---

## 7. Next Actions After Building the Base

Once the basic structure + one working lower third is in place:

- Export the project as a **Project Archive** (.drp) into the `master_project/` folder.
- Document any manual steps required after duplication.
- Begin scripting support (future timeline builder will duplicate this project and populate it).

---

## Updated Direction (May 2026)

- We are going **Fusion-first** for lower thirds and transitions.
- We want **simpler and smoother** results. We do **not** need to match the old static template pixel-for-pixel if it adds complexity.
- Scene transitions should feature **box morphing** (video boxes move and transform between layouts instead of hard cutting).
- Lower third text should have **purposeful entry and exit motion** (wipe, slide, etc.).

See `ANIMATED_TRANSITIONS_AND_MOTION.md` for detailed direction.

## Locked Decisions (May 2026)

- **Frame rate**: 24.000 fps
- **Color Management**: DaVinci YRGB Color Managed (Rec.709 Gamma 2.4)
- **Philosophy**: Simpler + smoother. We are not chasing exact replication of the old static template if it adds complexity.
- **1cam treatment**: We are open to simplifying the white border floating frame. We will prototype both versions so you can compare.

## Remaining Open Items

- How elaborate the box morphing transitions should be in v1.
- Exact animation style for lower third entry/exit (we'll prototype a few options in Fusion).

---

**Status:** This guide will be updated as we build the actual template inside Resolve.

When you're ready to start building inside Resolve, open this guide and begin at Step 1. Let me know when you want to tackle any of the open decisions above.