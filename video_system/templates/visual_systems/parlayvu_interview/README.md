# parlayvu_interview — Visual System

This is the canonical, reusable visual system for ParlayVU interview/podcast-style productions.

It is the evolution of what was previously called `ramair_interview`.

## Purpose

This folder defines a complete, reusable **visual language** that multiple clients can adopt.

It includes:
- Legacy reference assets (for the old FFmpeg renderer)
- The modern Resolve-native template (the future)
- Style definitions
- Documentation

## Relationship to Clients

- **Core visual system** (this folder): Generic and reusable.
- **Client-specific customizations**: Live in `templates/client_overrides/<client>/` (light overrides only).
- **Individual projects**: Live in `projects/<Client>/<Show>/` and reference this visual system.

## Current Status (2026-05)

- Legacy v1 renderer components still live here (for backward compatibility during transition).
- The new Resolve-native template is under active development in the `resolve/` subfolder.
- This visual system is intended to be used by RamAir and future clients who want this aesthetic.

## Structure

```
parlayvu_interview/
├── legacy/           # Old layouts, styles, etc. (v1 reference)
├── resolve/          # Modern DaVinci Resolve template + assets
├── README.md
└── (future: visual_spec.json, etc.)
```

## For New Clients

Most new clients should start by using this visual system (with light customizations if needed) rather than creating a brand new one.

See: `docs/VISUAL_SYSTEMS_AND_CLIENT_CUSTOMIZATION.md`

## Naming Note

This folder was previously named `ramair_interview`. It has been reframed as a reusable ParlayVU asset because the visual language is not inherently tied to one client.