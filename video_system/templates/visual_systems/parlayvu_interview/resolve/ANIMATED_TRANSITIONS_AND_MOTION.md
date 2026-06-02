# Animated Transitions & Lower Third Motion

**Date:** 2026-05-29
**Status:** Design Direction

## Core Philosophy (Updated)

We are shifting from the original static, hard-cut visual language toward something **simpler and smoother**:

- Scene changes use **motion and morphing** instead of hard cuts.
- Lower thirds have **purposeful entry and exit animation**.
- The system should feel polished and modern without becoming overly complex.

This aligns with investing early in **Fusion compositions**.

## Scene Transitions (Box Morphing)

Instead of cutting between different camera layouts (1cam → 2cam → 2cam_broll, etc.), we want the video boxes themselves to **move and transform** from one configuration to the next.

### Goals
- The transition feels intentional and designed.
- Video boxes resize, reposition, and crossfade in a coordinated way.
- It feels like a single evolving composition rather than discrete scenes.

### Recommended Approach in Resolve

Use **Compound Clips + Fusion** for the most powerful results:

1. Each "scene" (1cam, 2cam, 2cam_broll, etc.) is built as a **Compound Clip**.
2. Transitions between scenes are created by:
   - Keyframing the position, scale, and crop of the video boxes inside Fusion.
   - Using Fusion's **Merge** tool + **Transform** nodes for smooth morphing.
   - Optional: Add subtle easing curves for more organic movement.

Alternative (lighter) approach:
- Use timeline-level keyframing on video tracks + opacity.
- Combine with Fusion FX on the track (e.g., "Transform" or custom Fusion clip).

**Recommendation:** Start with Compound Clip + Fusion for the core layouts. This gives the most control and reusability.

### Common Morph Patterns
- 1cam full-frame → 2cam split (one box shrinks and moves left, second box enters from right)
- 2cam → 2cam_broll (one camera box shrinks and moves to corner while b-roll box expands)
- B-roll heavy layouts where the b-roll box "grows" from a small inset to dominant

We should design 4–6 reusable transition "recipes" that can be applied between common layout pairs.

## Lower Third Animation

Text should **not** just pop on and off.

### Entry Animation Ideas (Choose 1–2 standards)
- Wipe from left (text reveals as bar wipes in)
- Slide up from bottom with the bar
- Fade + slight scale up (subtle pop)
- Text types on while the bar animates in

### Exit Animation Ideas
- Reverse of entry (preferred for consistency)
- Wipe off to the right
- Fade out while bar collapses

**Best Practice:** Build entry and exit as **separate Fusion animations** inside the lower third composition so they can be triggered cleanly on the timeline (using clip handles or keyframes on the Fusion clip).

### Timing Recommendations
- Entry: 12–18 frames
- Exit: 12–18 frames
- Hold time in middle should feel generous

## Implementation Priority

Because we are going Fusion-first:

1. **Lower Third Compositions** (highest priority)
   - Full lower third (bar + two text rows + branding plates) as a reusable Fusion title
   - Built-in entry and exit animations
   - Controls exposed: Top Text, Bottom Text, Trigger Entry, Trigger Exit

2. **Layout Morph Transitions**
   - Start with the most common transitions (1cam ↔ 2cam, 2cam ↔ 2cam_broll)
   - Build as reusable Fusion FX or Compound Clip templates

3. **B-roll Cards & Name Cards**
   - These can start simpler (Text+ with basic fade or slide) and be upgraded to Fusion later if needed.

## Design Constraints (Keep It Smooth)

- Avoid overly flashy or trendy motion that will date quickly.
- Motion should feel confident and intentional, not busy.
- Prioritize **readability** — text must remain legible during movement.
- Keep the number of different transition styles limited (consistency > variety).

---

This document should evolve as we prototype the first animations inside Fusion. Once we have working examples, we can lock in the standard motion language for the system.