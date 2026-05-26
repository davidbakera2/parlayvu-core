# ParlayVU Roadmap

> What's next, in plain language. Updated when we ship or commit to new work.

**Last updated:** 2026-05-26
**See also:** [ARCHITECTURE.md](./ARCHITECTURE.md) for current state, [DECISIONS.md](./DECISIONS.md) for the why.

---

## Recently shipped

**This session (2026-05-25 / 26):**

- ✅ **Multi-client foundation** — per-client config at `client_artifacts/<client_id>/config.yaml` replaces singleton `M365_FILES_TEAM_ID`/`CHANNEL_ID` env vars. Tavus `/v1/chat/completions` reads `X-Parlayvu-Client-Id` header per persona; Nathan's system prompt gets per-client preferences (pronunciation, tone) injected at conversation start. (Track 2)
- ✅ **Christ's Hope onboarded** as second live client (`p7017121a743` Tavus persona, full client_artifacts folder).
- ✅ **ULC Ann Arbor onboarded** as third live client (`p577962cd534` Tavus persona, reference-sites + design notes already captured from visioning session).
- ✅ **Teams-first templates** — `06_Templates/Meeting_Notes_Template.docx` in each client's Teams channel is the canonical, client-editable source. Repo copy is starter/fallback.
- ✅ **Standardized template filename** — `Meeting_Notes_Template.docx` is the same path for every client; only docx content varies.
- ✅ **Pronunciation fix bundled into config.yaml** — RamAir → "Ram-Air" lives in `preferences.pronunciation` rather than a one-off prompt edit. (Track 1)
- ✅ **Tavus persona registry** documented in ARCHITECTURE.md §6 with onboarding steps for client N.

**Previous (last week):**

- ✅ **Tenant migration complete** — all infra moved from Baker Strategy Group Azure/Entra to ParlayVU's own subscription + tenant
- ✅ **`save_meeting_notes` tool** — Nathan files notes himself at end of meeting, no human in the loop
- ✅ **10-field structured meeting notes** — title, date+time, project, attendees, summary, decisions, action items table, questions, next steps, source material
- ✅ **DOCX template renderer with structural duplication** — bulleted-list paragraphs duplicate per item, action items table duplicates rows per action
- ✅ **Multiple placeholder aliases** in action items table — `{{ACTION_DATE}}`, `{{DUE_DATE}}`, `{{ACTION_DUE}}` all work
- ✅ **Streaming with mid-tool narration** — Nathan talks during long-running tool calls instead of going silent
- ✅ **Date awareness in prompt** — Nathan resolves "tomorrow"/"Friday"/"next week" to specific dates
- ✅ **Idempotent setup scripts** — full re-bootstrap of Azure + Entra + GitHub Actions in 4 PowerShell scripts

---

## Next up

Two main tracks remaining from the original four. Order is driven by real-world deadlines (when do clients need these), not by code dependency. Some can ship in parallel.

### Track 3: Dylan v2 web design (~3-4 hours)

**Goal:** Dylan can build 5-7 sample homepage variations for ULC Ann Arbor based on reference URLs + brand notes. Iterate based on client feedback.

**Approach (deliberately lean — see DECISIONS.md on "use Claude, don't build SaaS"):**
- One new tool for Dylan: `write_site_file(client_id, relative_path, content)` — writes HTML/CSS/JSX into `client_artifacts/<client>/03_Deliverables/sites/<variation>/`
- Update Dylan's system prompt: *"For design work, generate complete HTML/Tailwind pages and write them. For multiple variations, produce N visually distinct treatments of the same content. Fetch reference URLs first to understand the client's taste."*
- Reuse existing `deploy_to_cloudflare` for multi-preview URLs
- ULC Ann Arbor is the forcing function — reference sites and visioning notes already captured at `client_artifacts/ulcannarbor/01_Source_Material/reference-sites.md`.

**Status:** Not started. ~3-4 hrs including iteration on prompt. ULC fully scaffolded and ready to consume the output.

**Open questions:**
- Image sourcing: Unsplash API, AI-generated, or just placeholder boxes for v1?
- Does Dylan need to read existing site files (edit mode), or always generate fresh? (Answer: both, once Track 4 lands — Matt-at-ULC wants edits.)

---

### Track 4: Teams chat with tools — one Nathan, multiple surfaces (~1 day)

**Goal:** Clients (Matt at ULC, contacts at Christ's Hope, etc.) chat with Nathan in MS Teams; Nathan can do real work — answer questions, ask Dylan to edit the site, file notes — same brain as Tavus Nathan.

**Why this matters:** Today Teams Nathan and Tavus Nathan are different brains. Tavus uses `/v1/chat/completions` with tools. Teams uses an older agent-graph path with no tools. Unifying them = one Nathan that's smart everywhere.

**Approach:**
1. **Verify Teams bot end-to-end** in new ParlayVU tenant (Bot Framework messaging endpoint may still point at old Baker Strategy URL) — 30 min
2. **Route `/teams/messages` through `/v1/chat/completions`** — Teams Nathan becomes a thin Bot Framework ↔ OpenAI Chat Completions adapter, full tool access — 2 hrs
3. **Attachment handling** — when client attaches a photo/file, download via Bot Framework, save to `client_artifacts/<client>/01_Source_Material/uploads/`, include path in Nathan's context — 1-2 hrs
4. **Add Dylan's `read_site_file` / `write_site_file` / `deploy_site` tools** (overlaps with Track 3) — 2 hrs
5. **End-to-end test** with Matt-at-ULC: *"Can we make the buttons blue?"* → Nathan delegates to Dylan → preview URL replied in chat — 1-2 hrs

**Total: ~one focused day** once Track 2 (multi-client) is in place.

**Open architectural questions:**
- **Who's authorized to talk to Nathan?** Channel posts: anyone in the bound channel. 1:1 DMs: needs allowlist per client (`authorized_contacts: [matt@ulcannarbor.org, ...]` in `config.yaml`). Anyone else gets a polite "I can only help you if you're on the authorized contacts list for one of our clients."
- **What's auto vs gated?** Style tweaks (button color, font size) → auto-deploy to preview, ping client with URL. Content/copy changes → existing approvals system kicks in. Where exactly the line is needs explicit per-client setting.
- **Sync vs async conversation?** When Nathan delegates a 90-second job to Dylan, does he reply immediately ("On it, will ping you in ~2 min") and follow up, or hold? Default: reply immediately + follow up. Feels more responsive.

---

## Deferred — with explicit trigger conditions

These are deliberate "not now" calls. Each lists what would make us revisit.

### RAG over client knowledge
- **Trigger:** Any client has >30 markdown files, OR we accumulate >10 saved meeting notes per client, OR Nathan needs to answer specific historical questions ("what did we decide about subject lines in March?")
- **Approach:** pgvector in Neon (already a Postgres user), Voyage-3-lite embeddings, hybrid retrieval (vector + Postgres full-text), new `search_project_memory` tool alongside existing `get_project_context`
- **Estimate:** ~1 day when we build
- See [DECISIONS.md](./DECISIONS.md) for why document-dumping is fine today

### Native Teams video (Nathan as a real Teams call participant) + screen sharing
- **Trigger:** David asked to re-explore this for the screen-sharing UX unlock (Nathan presenting websites / PDFs / images relevant to the discussion in-meeting).
- **Approach:** Windows VM + Graph Communications Media SDK (scaffolded in `services/teams-media-bot-media-worker/`) + headless-browser content rendering for the screen-share track.
- **Estimate:** 4–5 weeks of focused work for participant join + screen share combined.
- **Scoping doc:** [docs/scoping/native-teams-video-and-screen-share.md](./docs/scoping/native-teams-video-and-screen-share.md) — what's already scaffolded, what's missing, alternatives (Recall.ai vendor path, in-meeting Teams app, smart Tavus-window content automation), and recommendation. Read before committing.

### Per-agent Tavus avatars
- **Trigger:** Concrete need to put Alex, Ava, Dylan, etc. on video calls — not hypothetical
- **Approach:** New Tavus persona per agent, agent registry maps name → persona_id, avatar provider abstraction already exists
- **Estimate:** ~half day per agent

### Action items → real work pipeline (Nathan's notes auto-dispatched to specialists)
- **Trigger:** Track 4 is solid AND client preferences foundation exists
- **Approach:** Saved meeting notes get parsed, action items become job records, dispatched to the right specialist, status reported back to the client via Teams
- **Estimate:** ~3-5 days

### Microsoft Planner integration
- **Trigger:** A client asks for Planner tasks created from meeting action items
- **Approach:** Application permissions for Planner (currently `Tasks.ReadWrite.All` may not be enough for app-only — needs verification), new `create_planner_tasks` tool, per-client Plan ID stored in `config.yaml`
- **Estimate:** ~half day

### Client self-service ("Nathan, remember from now on…")
- **Trigger:** After client preferences foundation lands; David coaches Nathan in a real call
- **Approach:** New `remember_client_preference(client_id, category, value, set_by)` tool; preferences auto-injected at conversation start
- **Estimate:** Folded into Track 2 multi-client work

### Teams Media Bot (.NET Bot Framework service)
- **Trigger:** Track 4 hits limitations of the FastAPI Python `/teams/messages` adapter that the .NET Bot Builder SDK would solve
- **Current state:** Scaffolded, `.NET 10 preview` build is failing. Not deployed.
- **Estimate:** Investigate when needed. May get deleted entirely if Track 4's Python adapter is sufficient.

---

## Identity hygiene follow-up

Currently `nathan@parlayvu.ai` (an AI agent's mailbox) is Global Admin in the ParlayVU tenant. That's awkward long-term: AI identity and human owner share the same Azure principal, so audit logs can't distinguish.

**When to fix:** When we want clean audit trails or before the first real security review.

**Approach:** Create `david@parlayvu.ai` (or similar human-owned account), grant Global Admin, then either downgrade Nathan's mailbox to a regular user or leave it as a redundant admin. Move all script ownership / role assignments to the human account.

**Estimate:** ~1 hour.
