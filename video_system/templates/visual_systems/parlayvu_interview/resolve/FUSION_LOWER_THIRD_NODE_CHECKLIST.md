# Fusion Lower Third — Node Checklist (Practical)

Use this as a working checklist while building inside Fusion.

## Phase 1 — Base Layout (No Animation Yet)

- [ ] Create a solid background for the main bar (dark navy `#062442`)
- [ ] Add Left Branding Plate input (MediaIn or Image plane)
- [ ] Add Right Branding Plate input
- [ ] Position and size the two plates correctly (reference the legacy layouts or Visual Spec)
- [ ] Add Text+ node for Top Row (white, bold, uppercase)
- [ ] Add Text+ node for Bottom Row (black on white plate)
- [ ] Create the white background plate for the bottom row
- [ ] Get text fitting and positioning close using the style_parameters.json values
- [ ] Group everything so far into a clean macro or group

## Phase 2 — 1cam Mode Toggle

- [ ] Add a Checkbox control called "1cam Framed Mode"
- [ ] When enabled:
  - Crop or mask the main bar into the smaller framed area
  - Draw a white border around it
- [ ] Make border thickness and color exposed controls
- [ ] Test that toggling the checkbox looks clean

## Phase 3 — Animation Layer

- [ ] Add an overall "Animation Progress" slider (0–1) as the master driver
- [ ] Build **Entry** animation using the progress value
- [ ] Build **Exit** animation (usually the reverse)
- [ ] Start with one animation style (recommend **Wipe** or **Slide Up** first)
- [ ] Add Easing controls if possible

## Phase 4 — Exposed Controls (User-Facing)

Create a clean set of published controls:

**Text**
- Top Text
- Bottom Text

**Branding**
- Show Left Plate (checkbox)
- Show Right Plate (checkbox)

**Animation**
- Animation In Type
- Animation Out Type
- Animation Duration In (frames)
- Animation Duration Out (frames)

**Mode**
- 1cam Framed Mode (checkbox)

## Phase 5 — Testing

- [ ] Drop the composition on a real timeline as a Fusion Title
- [ ] Test with real interview footage
- [ ] Test switching between 1cam mode and normal mode
- [ ] Test entry + exit animations
- [ ] Adjust timing and easing until it feels smooth

---

**Tip:** Build in this order — static layout first, then the 1cam toggle, then animation on top. Adding animation too early makes layout work painful.

When you're ready to start building, begin with Phase 1. Let me know when you hit any specific node or control and want detailed guidance on how to set it up.