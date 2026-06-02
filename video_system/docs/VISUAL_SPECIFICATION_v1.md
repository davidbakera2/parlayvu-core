# Visual Specification — ramair_interview Template (v1 Reference)

**Purpose:** This document is the authoritative, machine- and human-readable specification of the current visual system. Any v2 Resolve implementation must be able to match or exceed the fidelity of this look before being considered production-ready.

**Source of Truth:** Code in `tools/render_video.py` (especially `make_overlay`, `make_onecam_lower_third_overlay`, `make_broll_card`, `render_program`) + style JSONs in `templates/visual_systems/parlayvu_interview/legacy/styles/` + layout PNGs in `templates/visual_systems/parlayvu_interview/legacy/layouts/`.

**Canvas:** 1920 × 1080 @ 24 fps (upscaled from 1280×720 base in the renderer).

---

## 1. Layout Frames (The "Matte" / Video Holes)

All layouts are sourced from 1280×720 palette PNGs in `layouts/`, upscaled to 1920×1080 with `LANCZOS`.

### Common Properties
- Mostly transparent (video shows through).
- Opaque regions use a dark navy frame color: **RGB(12, 34, 66)** ≈ `#0C2242`.
- Lower third bar region (y ≈ 600–700 in 1280×720 base) is present in all layouts.
- 1cam has a **special smaller lower third treatment**.

### Per-Layout Details

| Layout       | Main Video Regions                          | Lower Third Treatment                  | Notes |
|--------------|---------------------------------------------|----------------------------------------|-------|
| `1cam.png`   | Full frame except small lower third frame   | Small framed bar (bbox ~ (25,601)-(1257,700) in base) with explicit white border | Special `make_onecam_lower_third_overlay` path. White 2px border drawn around the cropped lower frame. |
| `2cam.png`   | Two equal boxes left/right                  | Full-width dark bar at bottom          | Standard interview dialogue. |
| `2cam_broll.png` | Two small left boxes + large right b-roll box | Full-width dark bar                    | B-roll on right is zoomed 1.0–1.3× depending on source. |
| `3cam.png`   | Three boxes (host left, guest middle, guest2 right or 2+1 fallback) | Full-width dark bar                    | Falls back to 2cam sizing if no guest_02. |
| `3cam_broll.png` | Three small upper boxes + large right b-roll | Full-width dark bar                    | B-roll dominant on right. |

**Exact positioning logic** lives in `vf_scale_to_box` + specific overlay coordinates in `render_program` (lines ~558–621 in current render_video.py).

**Background Video (optional):** When `background_video` setting is set, it is looped full-screen behind everything. The layout PNG is used as an alpha matte (black areas become transparent to reveal the background).

---

## 2. Lower Third Plate (The Signature Element)

Generated dynamically as RGBA PNG overlays per scene.

### Geometry (in 1920×1080 final space, derived from 1280×720 base via `sx`/`sy` scaling)

- Full lower bar area: roughly y=598–700 (scaled).
- **LEFT branding cell** (`LOWER_LEFT`): (28,604) → (169,697) — contains `show_image_lower_third.png`.
- **RIGHT logo cell** (`LOWER_RIGHT`): (1161,604) → (1254,697) — contains `logo_square.png` with white frame and slight overlap treatment.
- **TOP TEXT BOX** (white text on dark): (176,606) → (1157,631)
- **BOTTOM TEXT BOX** (black text on white): (184,640) → (1125,687)

### Styling (from `styles/lower_third.json` + code)

**Top Row (Speaker / Title):**
- Font: Arial Bold
- Size: dynamically fitted, max ~21pt base → ~31.5pt final (scaled), min 13pt base
- Color: pure white `#FFFFFF`
- Background: `#062442` (dark navy) — the bar itself provides this
- Case: UPPER
- Alignment: Centered horizontally within the text box

**Bottom Row (Topic):**
- Font: Arial Bold
- Size: dynamically fitted, max ~32pt base → ~48pt final, min 18pt base
- Color: pure black `#000000`
- Background: solid white (the bar provides a white band)
- Case: UPPER
- Alignment: Left-aligned within the text box (x starts at left edge of box)

**Branding Assets:**
- Left: `show_image_lower_third.png` — fitted with `paste_fit` (cover, centered, unsharp mask applied).
- Right: `logo_square.png` — fitted, trimmed of near-white, slight scale 0.98, offset_y +4, then white frame redrawn on the right cell.

**Special 1cam Lower Third:**
- Only the lower bar portion is composited.
- A white 2px border is explicitly drawn around the lower frame rectangle.
- This creates the "floating framed lower third" look unique to single-camera segments.

---

## 3. B-Roll Cards (Top-Right Callouts)

Generated in `make_broll_card`.

### Visual Style (hard-coded in renderer, not fully in JSON yet)

- Size: 520×78 (or 520×54 for single-line) in base, scaled.
- Background: Navy `#062442` with 72% alpha (`(8,39,70,205)` in code).
- Right accent bar: Blue `#2C84C6` width 12px scaled.
- Text:
  - Line 1 (main): White, Arial Bold, 22pt base fitted down to 12pt. Right-aligned.
  - Line 2 (secondary): Light blue `#EBF5FF`, Arial Regular, 16pt base fitted to 10pt. Right-aligned.
- Long single-line handling: word-wrap logic with special fallback if >2 lines needed.
- Placement: Top-right of frame, stacked downward when multiple cards are active for a scene. X = W - card_width - 42, Y starts at 48 + (index-1) * (height + 10).

**Timing:** Cards are tied to `Graphics` rows of type `broll_card` (or linked to a scene via `linked_scene_id`). They have independent in/out relative to the scene start.

---

## 4. Name Cards (Graphics type = "name_card")

From `styles/name_cards.json`:

- Default duration: 5 seconds
- Font: Arial Bold, 34pt base
- Color: white on semi-transparent black (`alpha 0.55`)
- Placement variants:
  - Most layouts: `top_right`
  - B-roll layouts: `top_right_over_broll`

Exact positioning and animation (fade in/out) is currently handled in the renderer via the Graphics timing in the plan.

---

## 5. Subtitles

From `styles/subtitles.json` + `make_template_subtitles.py` + FFmpeg `subtitles` filter using `.ass`:

- Font: Arial Bold, 42pt
- Case: UPPER
- Max 2 lines, ~44 chars/line
- Primary: white with black outline (2.4pt)
- Box background: black 35% alpha
- Alignment: bottom center
- Margins tuned so they sit **just above** the lower third bar (margin_bottom ≈ 201 in 1920×1080 space)

The `.ass` is generated from `.srt` using the style JSON.

---

## 6. Other Visual Behaviors

- **Intro**: Usually full-bleed host or dedicated intro clip, sometimes with a 1cam-style lower third if `intro_lower_third_scene_id` is set.
- **Show Image / Outro**: Ken Burns-style slow zoom on `show_image.png` (zoompan filter: 0.0012 increment up to 1.055).
- **Audio**: Consistent loudness normalization (-16 LUFS target in final normalize step), music cues mixed with ducking/fades defined in the `audio` sheet.
- **B-roll insertion**: Either as a full layout replacement (2cam_broll, 3cam_broll) or as timed overlay cards on top of interview layouts.
- **Background plate**: Looped full-bleed, revealed through transparent areas of the layout matte.

---

## 7. Exact Colors (Normalized)

- Dark navy frame / lower bar bg: `#0C2242` / `#062442` (minor palette variance exists)
- Logo cell frame / accent: white `#FFFFFF`
- B-roll card navy: `#062442` (72% alpha)
- B-roll card accent: `#2C84C6`
- Subtitle box: black 35% alpha
- Name card bg: black 55% alpha

---

## 8. Implementation Notes for v2 Resolve Port

**Must-Have Parity for Phase 3 Sign-off:**

1. Lower third plate geometry, colors, font sizing/fitting behavior, and branding asset placement must be visually indistinguishable from v1 at 100% zoom on a normal monitor.
2. The special 1cam lower third with white border treatment must exist.
3. B-roll cards must match size, color, typography, stacking, and right-accent treatment.
4. Layout "hole" proportions and framing for 2cam / 2cam_broll / 3cam variants must match when using the same sources.
5. Subtitle positioning relative to the lower third must be preserved.

**Nice-to-Have (can come later):**
- Identical text fitting algorithm (we can use Resolve's text sizing or script our own).
- Exact same slow-zoom parameters on show image.
- Pixel-perfect match on every anti-aliased edge (not required if overall impression matches).

**Recommended Starting Implementation Order in Resolve:**

1. Text+ lower third (top + bottom rows + white/dark bars) with manual positioning first.
2. Add left/right branding assets as stills on the same Fusion comp or separate video track.
3. Recreate 1cam special border treatment.
4. Add b-roll card generator (can start as pre-rendered PNGs from the Python `make_broll_card` for fidelity, then move to native).
5. Layout matting / multi-track cropping for the camera boxes.
6. Background video reveal through mattes.

---

## 9. References in Codebase

- Primary: `tools/render_video.py` — `Renderer.make_overlay`, `make_onecam_lower_third_overlay`, `make_broll_card`, `paste_fit`, scaling functions, `LOWER_*` constants.
- Styles: `templates/visual_systems/parlayvu_interview/legacy/styles/lower_third.json`, `name_cards.json`, `broll_cards.json`, `subtitles.json`.
- Layouts: `templates/visual_systems/parlayvu_interview/legacy/layouts/*.png`.
- Example output: Any `final_no_subtitles.mp4` or `previews/*_check*.jpg` from real projects.

---

**This document should be updated whenever the visual language intentionally evolves.** It is the contract between the old renderer and the new Resolve-based system.

**Next step after review:** Extract precise pixel measurements, font metrics, and timing defaults into machine-readable JSON (e.g. `templates/visual_systems/parlayvu_interview/visual_spec.json`) that both the old renderer and future Resolve tools can consume.