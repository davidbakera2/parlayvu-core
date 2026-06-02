# ramair_interview — DEPRECATED LOCATION

**This folder has been migrated.**

The content that lived here has been reorganized into a more scalable structure for multiple clients.

## New Canonical Location

All future work for this visual system lives at:

```
templates/visual_systems/parlayvu_interview/
```

This includes:
- `legacy/` (moved from the old `layouts/` and `styles/`)
- `resolve/` (the new DaVinci Resolve template work)
- Documentation and configuration

## Why We Moved

- The visual system is designed to be reusable across clients (with light customization).
- Naming the top-level folder after one specific client (`ramair_interview`) was not sustainable.
- We adopted a cleaner architecture: `visual_systems/` + `client_overrides/`

## Migration Complete

- Legacy assets moved to `visual_systems/parlayvu_interview/legacy/`
- Resolve template work moved to `visual_systems/parlayvu_interview/resolve/`

## References

See these documents for the new model:
- `docs/VISUAL_SYSTEMS_AND_CLIENT_CUSTOMIZATION.md`
- `templates/visual_systems/parlayvu_interview/README.md`

**Do not add new files here.** This folder is now only a historical pointer.