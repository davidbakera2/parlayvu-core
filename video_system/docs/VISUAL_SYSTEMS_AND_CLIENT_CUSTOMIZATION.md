# Visual Systems and Client Customization

**Date:** 2026-05-29
**Status:** Design Decision

## Overview

ParlayVU video production supports multiple clients with potentially different visual needs. We separate concerns into two layers:

1. **Visual Systems** — Reusable, named looks/styles (e.g., `parlayvu_interview`)
2. **Client Customizations** — Light, per-client overrides on top of a visual system

## Visual Systems

A visual system is a complete, self-contained aesthetic package:

- Lower third design language
- Color palette and typography
- B-roll card / name card treatments
- Layout philosophies (1cam, 2cam, b-roll integration, etc.)
- Branding plate behavior
- Overall "feel"

**Location:** `templates/visual_systems/<system_name>/`

Examples we expect over time:
- `parlayvu_interview` (current system, originally developed for RamAir)
- `corporate_talks`
- `documentary_minimal`
- `high_energy_tech`

Each visual system can have its own Resolve template, legacy renderer support, and documentation.

## Client Customization Model

We support **three levels** of customization, in increasing order of effort:

### Level 1: Pure Adoption (Recommended for most clients)
- Client uses a visual system exactly as-is.
- Only asset swaps: `show_image.png`, `logo_square.png`, `show_image_lower_third.png`, intro video, music, etc.
- No code or style changes.
- Fastest to onboard.

### Level 2: Light Customization (Expected for many clients)
- Client uses a visual system as the base.
- Small, targeted overrides are allowed:
  - Accent color changes
  - Slight font size or positioning tweaks
  - Different lower third text hierarchy in some cases
  - Custom name card variations
  - Specific b-roll card styling
- These live in `templates/client_overrides/<client_slug>/`
- The timeline builder / renderer can merge base + overrides.

### Level 3: Full Custom Visual System
- Client needs a genuinely different look (different lower third architecture, completely different card system, different layout philosophy, etc.).
- A new folder is created under `templates/visual_systems/`.
- Higher cost. Should be rare.

## Folder Architecture

```
templates/
├── visual_systems/
│   ├── parlayvu_interview/           # Reusable core system
│   │   ├── resolve/
│   │   ├── legacy/
│   │   └── ...
│   └── another_system/
│
└── client_overrides/
    ├── ramair/                       # Light RamAir-specific tweaks (if any)
    ├── newclient/
    │   ├── colors.json
    │   ├── lower_third_overrides.json
    │   └── assets/                   # Client-specific branding plates, etc.
    └── ...
```

## How Projects Declare Their Visual System

In `projects/<Client>/<Show>/planning/video_plan.json` (or the spreadsheet), we will add:

```json
{
  "visual_system": "parlayvu_interview",
  "client_override": "newclient"     // optional
}
```

The tools (future Resolve timeline builder, v1 renderer, etc.) will resolve the effective styles by merging:

`base visual system` + `client override` (if present)

## Light Customization Examples

Allowed in Level 2:
- Change the navy accent color from `#062442` to the client's brand navy.
- Adjust the bottom row font size by ±4pt for better readability with their logo.
- Provide a different `show_image_lower_third.png` treatment.
- Add one extra b-roll card variant.

Not allowed in Level 2 (requires new visual system):
- Completely different lower third layout geometry (e.g., side-mounted instead of bottom bar).
- New card shapes or animation philosophy.
- Different number of camera boxes in layouts.

## Benefits of This Model

- Most clients get high-quality results quickly using the proven `parlayvu_interview` system.
- We avoid creating dozens of near-identical visual systems.
- The core visual system improves over time and benefits all clients.
- Truly unique client needs are still supported without polluting the main system.
- Clear ownership: Visual System = ParlayVU brand standards. Client Override = specific client needs.

## Next Steps

- Update all documentation to use `visual_systems/` language.
- Evolve `template_config.json` to support the override model.
- When building the Resolve template for `parlayvu_interview`, design it with light theming/override points in mind (e.g., configurable accent colors via a small JSON or project settings).
- Create a small example in `client_overrides/_example/`.

---

This model directly supports the Podcast Parlay vision of scaling across many clients while maintaining quality and brand consistency.