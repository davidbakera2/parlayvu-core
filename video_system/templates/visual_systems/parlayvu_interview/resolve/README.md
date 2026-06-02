# parlayvu_interview — Resolve Native Template (v2)

This is the official location for the DaVinci Resolve template for the reusable ParlayVU interview visual system.

## Purpose

We are building a proper Resolve-native implementation (Text+, Fusion compositions, timeline architecture, Deliver presets) that matches the visual language originally developed for this style.

This template is designed to be:
- Reusable across multiple clients
- Support light customization via `client_overrides/`
- Scriptable by the future timeline builder

## Structure

- `master_project/` — The actual Resolve project template (to be populated)
- `fusion/` — Exported Fusion compositions for lower thirds, cards, etc.
- `render_presets/` — Exported Deliver page render settings

## See Also

- [../../docs/RESOLVE_PROJECT_TEMPLATE_DESIGN.md](../../docs/RESOLVE_PROJECT_TEMPLATE_DESIGN.md)
- [../../docs/VISUAL_SYSTEMS_AND_CLIENT_CUSTOMIZATION.md](../../docs/VISUAL_SYSTEMS_AND_CLIENT_CUSTOMIZATION.md)
- [../README.md](../README.md) (parent visual system)