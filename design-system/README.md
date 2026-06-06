# ParlayVU Design System

Canonical reference designs for the approved homepage sections Dylan can compose onto
client sites.

## How it's used

`sections/*.astro` are the **source of truth** for each approved section's structure,
Tailwind classes, and layout. When Nathan invokes the `compose_section_edit` tool,
`app/services/dylan_edit_service.py::_generate_section_html` loads the matching
`sections/<SectionName>.astro` file and feeds its markup to the LLM as grounding, so the
generated HTML matches the approved look instead of being freestyled.

- File name must match the `section_name` exactly (e.g. `TeamGrid` → `sections/TeamGrid.astro`).
- Approved sections (v1): `Hero`, `Features3Col`, `TeamGrid`, `TestimonialGrid`,
  `ContentWithImage`, `LogoCloud`, `FAQ`, `CTA`.
- Sections without a reference file fall back to a freestyle prompt. To make a section
  canonical, add its `.astro` file here — no code change required.

## Adding or editing a section

1. Add/edit `sections/<SectionName>.astro` using Astro props + Tailwind.
2. Keep markup self-contained (one `<section>`), responsive, and accessible.
3. If it's a new section, add its name to the `allowed_sections` set in
   `app/services/dylan_edit_service.py`.
