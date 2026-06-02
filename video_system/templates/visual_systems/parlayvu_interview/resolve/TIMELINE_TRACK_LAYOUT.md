# Timeline Track Layout — parlayvu_interview

This document defines the standard timeline track architecture for the ParlayVU interview visual system.

Use this as the reference when creating new timelines (manually or via scripting).

## Recommended Track Layout

### Video Tracks

| Track | Name                  | Purpose                                      | Typical Content                          | Notes |
|-------|-----------------------|----------------------------------------------|------------------------------------------|-------|
| V1    | Program               | Main interview footage + b-roll inserts      | Host, Guest, B-roll                      | Primary video layer |
| V2    | Lower_Thirds          | Speaker name/title + topic text              | Text+ or Fusion lower thirds             | Core branding element |
| V3    | Graphics_Cards        | Name cards, b-roll cards, callouts           | Text+ / Fusion cards                     | Stacking behavior important |
| V4    | Additional_Graphics   | Extra overlays, logos, picture-in-picture    | Occasional use                           | Keep minimal |
| V5+   | Reserved              | Future complex effects                       | —                                        | Do not use lightly |

### Audio Tracks

| Track | Name               | Purpose                              | Typical Content                     |
|-------|--------------------|--------------------------------------|-------------------------------------|
| A1    | Host               | Primary host voice                   | Host camera audio                   |
| A2    | Guest              | Guest voices                         | Guest camera audio                  |
| A3    | Broll_Nat          | Natural sound from b-roll            | B-roll camera audio                 |
| A4    | Music_Bed          | Background music and stingers        | Music.wav + sound design cues       |
| A5    | Sound_Design       | Additional effects and sweeteners    | Optional                            |

### Subtitle Track

| Track | Name     | Purpose                  |
|-------|----------|--------------------------|
| S1    | Captions | Burned-in or exportable subtitles |

## Track Naming Conventions

- Use **CamelCase** or **snake_case** consistently (recommend CamelCase for readability in Resolve).
- Prefix video tracks with `V` and audio with `A` where helpful for scripting.
- Keep names stable so the future timeline builder can target them reliably.

## Visual Organization Tips

- Color-code tracks in Resolve for quick visual scanning:
  - V1 (Program): Blue
  - V2 (Lower Thirds): Orange
  - V3 (Cards/Graphics): Green
  - Audio tracks: Default or logical grouping colors

- Lock tracks you are not actively editing when doing detailed graphics work.

## Scripting Considerations (Future)

The timeline builder should be able to:
- Create this exact track structure automatically
- Name tracks consistently
- Apply default track colors
- Add a "Template_Timeline" version with example content and markers

---

**Last updated:** 2026-05-29 (initial version)