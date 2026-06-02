# Client Override Example

This folder demonstrates how **light per-client customization** works on top of a visual system (e.g. `parlayvu_interview`).

## Philosophy

Most clients should use the base visual system with only minimal, targeted changes rather than forking the entire look.

## What Belongs Here (Light Customization)

- Small color overrides (accent colors, etc.)
- Minor positioning or sizing tweaks to lower thirds / cards
- Client-specific asset references (logos, show images, lower third plates)
- Limited style variations (e.g. a special name card for executives)

## What Does NOT Belong Here

- Completely new lower third layouts
- New card shapes or animation systems
- Major changes to camera layout philosophy

Those require a new entry under `visual_systems/`.

## Example Structure

```
client_overrides/
└── acme_corp/
    ├── override.json          # Main customization manifest
    ├── assets/
    │   ├── logo_square.png
    │   └── show_image_lower_third.png
    └── styles/
        └── accent_color.json
```

## How Tools Will Use This (Future)

The timeline builder and render tools will:
1. Load the base visual system (`parlayvu_interview`)
2. Merge any overrides from `client_overrides/<client>/`
3. Apply the combined result to the Resolve timeline or render

## Current Status

This is a placeholder/example. Real client override folders will be created when needed.