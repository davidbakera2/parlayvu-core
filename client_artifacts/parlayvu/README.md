# ParlayVU (internal tenant)

Nathan-as-Chief-of-Staff for ParlayVU itself. Used in the **ParlayVU** Teams team's channels so David can ask Nathan strategic product questions ("what's next after Track 5?", "why didn't we adopt Tavus's RAG?", "where does meeting-note publishing live?") and get answers grounded in the actual repo docs, not training-data guesses.

- `client_id`: `parlayvu`
- Tavus persona: **none** (this tenant is Teams-chat-only — there's no client video call for ParlayVU itself, so no Tavus persona is needed. If we ever want avatar-Nathan for internal use, clone replica `ra534cde00e5` into a new persona with `X-Parlayvu-Client-Id: parlayvu`.)
- Teams team binding: see `config.yaml`
- Meeting notes template: `06_Templates/Meeting_Notes_Template.docx` (canonical filename, same as every other client)

## Source material

`00_Client_Brief/` holds **synced copies** of the repo's canonical product docs:

- `ARCHITECTURE.md` — current system state
- `ROADMAP.md` — what's next
- `DECISIONS.md` — why behind key calls
- `MIGRATION-PLAN.md` — tenant migration history

These are **not** edited in-place here — they are kept fresh by `scripts/Sync-ParlayvuClientArtifacts.ps1`. Edit the originals at the repo root; rerun the sync script to push changes into Nathan's context.

Other folders (`01_Source_Material/` through `05_Performance/`) are available for internal planning artifacts, retros, performance metrics, etc.

## Why this tenant exists

ParlayVU the *product company* needs the same coordination surface ParlayVU the *platform* gives every client. By treating ourselves as a tenant we get:

- One Nathan brain answering strategic product questions in the team chat
- A version-controlled artifact tree for internal product planning
- The same per-client config plumbing (no special case)

## Onboarding TODO

- [x] Folder scaffold + config.yaml + template
- [x] Sync script copying the four canonical docs into 00_Client_Brief
- [ ] Install ParlayVU bot in the ParlayVU Teams team (David — via Teams UI)
- [ ] Run `@ParlayVU bind this channel to ParlayVU` in the General channel
