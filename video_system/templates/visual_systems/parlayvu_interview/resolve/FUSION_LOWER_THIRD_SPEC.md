# Fusion Lower Third Composition — Spec

**Visual System:** parlayvu_interview
**Date:** 2026-05-29
**Status:** Draft for Implementation

## Goals

- Build the lower third as a proper **Fusion composition** from the start.
- Support smooth **entry and exit animations**.
- Keep the overall system **simpler and smoother** than the old static version.
- Make it easy to use on the timeline with minimal manual keyframing.
- Allow a clean default look, with an optional 1cam framed treatment.
- Support the two branding plates (left show image + right logo).

## High-Level Structure

The lower third will be delivered as a **Fusion Title** (or a saved Fusion composition that can be used as a generator).

It should be self-contained so an editor can drop it on V2, set the text, choose animation in/out, and move on.

### Core Layers (from bottom to top in Fusion)

1. **Background Bar** (the dark navy strip)
2. **Left Branding Plate** (show_image_lower_third.png)
3. **Right Branding Plate** (logo_square.png)
4. **Top Text Row** (white, bold, speaker/title)
5. **Bottom Text Row** (black on white plate, topic)
6. **Optional 1cam Frame** (white border treatment — switchable)
7. **Animation Layer** (controls entry/exit motion for the whole group)

## Recommended Fusion Node Tree (Starting Point)

```
MediaIn (optional - for live preview inside Fusion)
          |
Background (solid color or gradient for the bar)
          |
Transform (for the main bar - position/scale/animation)
          |
Merge (brings in left plate)
          |
Merge (brings in right plate)
          |
Text+ (Top Row)
          |
Text+ (Bottom Row)   ← with its own white background plate
          |
Merge nodes to combine everything
          |
Transform / Custom Tool (for overall entry/exit animation)
          |
1cam Border (optional path - white rectangle + mask)
          |
Output
```

### Key Controls to Expose (on the Fusion Title)

**Text Controls**
- `Top Text` (string)
- `Bottom Text` (string)
- `Top Text Size` (slider, with good defaults)
- `Bottom Text Size` (slider)

**Branding Controls**
- `Show Left Plate` (checkbox)
- `Show Right Plate` (checkbox)
- `Left Plate Opacity`
- `Right Plate Opacity`

**Animation Controls** (these are the important ones)
- `Animation In` (dropdown or buttons): None / Wipe Left / Slide Up / Fade + Scale / Custom
- `Animation Out` (dropdown): Mirror of above or "Reverse In"
- `Animation In Duration` (frames)
- `Animation Out Duration` (frames)
- `Animation Easing` (Linear / Ease In-Out / etc.)

**Mode Controls**
- `1cam Framed Mode` (checkbox) — enables the smaller framed treatment + border
- `1cam Border Thickness`
- `1cam Border Color` (usually white)

**Styling Overrides** (for light customization later)
- `Bar Color` (color picker)
- `Top Text Color`
- `Bottom Text Color`
- `Bottom Plate Color`

## Animation Ideas (Entry / Exit)

We should prototype these in Fusion:

**Entry Options (pick 2-3 favorites first)**
1. **Wipe Left-to-Right** — The whole lower third bar wipes in from left, text follows or reveals with it.
2. **Slide Up** — Bar and text slide up from below the frame together.
3. **Fade + Subtle Pop** — Fades in while scaling slightly from 95% → 100%.
4. **Text First, Bar Second** — Text animates in, then the bar "grows" behind it.

**Exit Options**
- Reverse of the entry (strongly preferred for consistency).
- Wipe off to the right.
- Slide down.

**Timing Targets (at 24 fps)**
- Entry: 14–18 frames
- Exit: 14–18 frames
- Hold time in middle: generous

## 1cam Framed Treatment

Because we want to keep this flexible:

- When "1cam Framed Mode" is off → standard full-width lower third.
- When turned on → the composition crops/repositions the bar into a smaller framed area and draws the white border.
- This should be a clean toggle so the same composition works for both 1cam and multi-cam scenes.

We will prototype the bordered version after the clean version is working.

## Usage on Timeline

- Drop the Fusion Title on V2 (Lower Thirds track).
- Set duration of the clip for how long the lower third should be visible.
- Use clip handles or the Animation In/Out controls to trigger the motion.
- For precise timing, the editor can keyframe the "Animation Progress" slider if needed.

## File Organization

Once built, we should save:
- The full Fusion composition as a `.comp` or as a **Fusion Title Macro** in the Effects Library.
- A versioned copy in `resolve/fusion/Lower_Thirds/ParlayVU_LowerThird_v1.comp`

## Next Steps (Immediate)

1. Build the base static version first (no animation) to get the layout and text fitting right.
2. Add the branding plate inputs and positioning.
3. Add the 1cam toggle.
4. Layer in the first animation (recommend starting with **Wipe** or **Slide Up**).
5. Test on real footage.
6. Iterate on motion.

---

**Status:** Ready to start building inside Resolve.

When you open Resolve and begin the Fusion composition, work through this spec in order. Let me know when you want to prototype specific animations or need node-by-node guidance.