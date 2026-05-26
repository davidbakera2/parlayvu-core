# ULC Ann Arbor

ParlayVU client folder. Folder structure mirrors RamAir and Christ's Hope; see [client_artifacts/ramair/README.md](../ramair/README.md) for the canonical layout reference.

- `client_id`: `ulcannarbor`
- Engagement focus: homepage redesign — Dylan drafts variations from reference URLs + brand notes, iterates from client feedback.
- Primary contact: Matt at ULC (full email + role TBD — fill into `00_Client_Brief/client-brief.md`).

## Status: NOT YET ACTIVE

This client is scaffolded but not active. `config.yaml.template` is in place; rename it to `config.yaml` and fill in the Teams `team_id` and `channel_id` to activate. Until then, `load_client_config("ulcannarbor")` will fail.

## Onboarding TODO

- [ ] **Teams channel binding**: get the team_id + channel_id from the ULC Teams channel link (paste the link, the IDs are in the URL — same pattern as Christ's Hope), then rename `config.yaml.template` → `config.yaml` and fill them in.
- [ ] **Tavus persona**: create a "Nathan Ellis for ULC Ann Arbor" persona in the Tavus UI (clone the structure of `p7017121a743` (CH) — same replica `ra534cde00e5`, write a ULC-specific system_prompt). Then run:
  ```powershell
  .\services\teams-media-bot\scripts\Update-NathanPersonaLLM.ps1 `
      -TavusApiKey $env:TAVUS_API_KEY `
      -PersonaId <new-ulc-persona-id> `
      -ClientId ulcannarbor `
      -ParlayVuApiUrl https://parlayvu-api.thankfulriver-96fed9c6.eastus.azurecontainerapps.io `
      -NathanLlmApiKey $env:NATHAN_LLM_API_KEY
  ```
- [ ] **Upload meeting-notes template to Teams**: drag `06_Templates/Meeting_Notes_Template.docx` into the ULC Teams channel's `06_Templates/` folder so the client can edit it directly in Word.
- [ ] **Fill in starter docs**:
  - `00_Client_Brief/client-brief.md` — replace the TBD blocks with real engagement info, contact emails, brand voice.
  - `01_Source_Material/reference-sites.md` — add the URLs ULC wants the team to study, with one-line notes per site.
  - `01_Source_Material/design-notes.md` — capture brand preferences (color, typography, things to avoid).
  - `02_Planning/project-plan.md` — first milestone is producing N homepage variations for review.

## ⚠️ Dylan v2 status

The "Nathan asks Dylan to draft homepage variations for ULC" flow depends on [Track 3 in ROADMAP.md](../../ROADMAP.md) — the `write_site_file` tool that lets Dylan produce HTML/Tailwind variations into `03_Deliverables/sites/<variation>/`. That tool is **not built yet** (~3–4 hours of work; ULC is the forcing function).

Until Track 3 ships:
- You can drop reference URLs and notes into this folder; Nathan can already reference them in any meeting with ULC.
- Dylan can generate Astro sites via the existing `/dylan/generate-site` HTTP endpoint, but it's not driven by a conversation with Nathan — you'd POST to it directly with a prompt.
