# ParlayVU Roadmap

> What's next, in plain language. Updated when we ship or commit to new work.

**Last updated:** 2026-05-27 (post-midnight wrap — bot auth fix verified end-to-end via Nathan sideload)
**See also:** [ARCHITECTURE.md](./ARCHITECTURE.md) for current state, [DECISIONS.md](./DECISIONS.md) for the why.

---

## ✅ Bot Framework auth fix — resolved end-to-end

The 2026-05-26 outage (Azure Bot Service pointing at the phantom `2dc8aa66-...` appId from the Baker Strategy migration) is functionally resolved. Server side was fixed first (new app reg `ea0775e7-...`, recreated Bot Service, env vars updated → revision `parlayvu-api--0000019`). Verification took a second pass because the **Microsoft 365 Admin Center "Update" flow on the existing `ParlayVU` catalog entry doesn't reliably bust the cache** — even after the update + uninstall/reinstall at the team level, Teams clients kept routing @-mentions to the dead old botId (zero POSTs reaching `/teams/messages`).

**What actually unblocked it:** sideloading a parallel manifest with a **fresh `id`** but the **same `botId` (`ea0775e7-...`)** under the name "Nathan". Within minutes of the Nathan install, real Bot Framework traffic appeared in the Container App logs. Bound all 5 channels (`@Nathan bind this channel to <client>`) and smoke-tested the 3 real client tenants (christshope, ramair, ulcannarbor) — Nathan answers from the correctly bound client's content in each.

Persisted artifacts from the diagnostic: [`infra/teams-app/manifest-nathan.json`](infra/teams-app/manifest-nathan.json) (the source of truth for the Nathan catalog id; rebuild the zip with the same id by re-zipping this manifest + icons).

Operational lesson saved to memory: `teams_app_manifest_update_gotcha.md` — for any future botId change, skip the "uninstall/reinstall to bust cache" step and jump straight to a fresh-id sideload to isolate the bot from the catalog.

### Still open — non-urgent forward-path decisions

- **The original ParlayVU catalog entry is still broken.** It's installed in all 5 teams but routes to the dead old botId. Three options, pick later:
  1. **Adopt Nathan as canonical** — polish the Nathan manifest (proper `name.full`, branded description/icons), install in all 5 teams, delete the broken ParlayVU entry. Brand shifts from `@ParlayVU` to `@Nathan` — arguably more on-brand for the persona.
  2. **Delete + recreate ParlayVU as a fresh upload** (not Update). Keeps the `@ParlayVU` brand; existing per-channel bindings in our DB are keyed by Teams channel id so they should survive.
  3. **Keep both for now.** Nathan works; ParlayVU entry stays dead.
- **`TEAMS_APP_PASSWORD` is plaintext on the Container App revision env** — should rotate the secret and re-deploy with `secretRef` instead of inline value. ~30 min when convenient.
- **Bake Nathan's diagnostic build into `infra/teams-app/build_app_package.py`** if Nathan stays as a real install (would make rebuilding `nathan-teams-app.zip` reproducible — today it was built ad-hoc in PowerShell). Skip this work if option (2) above is chosen.

---

## Recently shipped

**This session (2026-05-25 / 26) — major:**

- ✅ **Multi-client foundation (Track 2)** — per-client config at `client_artifacts/<client_id>/config.yaml` replaces singleton `M365_FILES_TEAM_ID`/`CHANNEL_ID` env vars. Tavus `/v1/chat/completions` reads `X-Parlayvu-Client-Id` header per persona; per-client pronunciation/tone injected into Nathan's system prompt.
- ✅ **Three live clients** — RamAir (`p02372056aec`), Christ's Hope (`p7017121a743`), ULC Ann Arbor (`p577962cd534`). All have separate Tavus personas, bound Teams channels, scaffolded `client_artifacts/`.
- ✅ **Dylan v2 (Track 3)** — `POST /dylan/generate-variations` produces N visually-distinct single-file HTML+Tailwind homepage drafts from a client's reference sites + brand notes; auto-deploys to `<client>-previews.pages.dev`. Five predefined design theses keep variations genuinely distinct.
- ✅ **Teams chat unification (Track 4)** — `/teams/messages` routes through the same Nathan tool-loop as Tavus. New `surface` param ("tavus"|"teams_chat") parameterizes the response style (voice rules vs markdown rules). 1:1 DM authorized-contacts gate (fail-closed). Attachment download + save to client uploads/ + path injection into Nathan's context.
- ✅ **File ingestion pipeline** — `POST /clients/{id}/ingest-files` or `python -m app.services.client_file_ingester <client>` pulls PDFs/.docx from a client's Teams channel, summarizes with Sonnet 4.6 into structured markdown under `01_Source_Material/reports/`. Pre-ingested reports flow into `get_project_context` with zero latency at call time.
- ✅ **On-demand file reading** — `list_client_files` + `read_client_file` tools as the fallback path for files Nathan hasn't pre-ingested. Shared text extractors (`app/tools/text_extractors.py`) handle PDF/.docx/markdown.
- ✅ **Teams-first templates** — `06_Templates/Meeting_Notes_Template.docx` (standardized filename) in each client's Teams channel is the canonical, client-editable source. Repo copy is starter/fallback.
- ✅ **Pronunciation fix (Track 1)** — bundled into `preferences.pronunciation` in config.yaml ("RamAir" → "Ram-Air").

**This session — infra + setup:**

- ✅ **Azure Bot Service created** in ParlayVU tenant (gap left over from migration). Codified in `scripts/Setup-ParlayvuBot.ps1`; MIGRATION-PLAN.md Phase 7.5 documents it. **Bot Framework auth bug** discovered + fixed late in session — see Active blocker section above. Setup script now mandates a real app reg (fail-fast) so the bug can't recur.
- ✅ **Two internal Nathan tenants** scaffolded: `client_artifacts/parlayvu/` (Nathan-as-Chief-of-Staff for the product company; reads synced repo docs from `00_Client_Brief/`) and `client_artifacts/bakerstrategy/` (holding-company tenant). `scripts/Sync-ParlayvuClientArtifacts.ps1` keeps the synced product docs fresh.
- ✅ **Teams app package** at `infra/teams-app/` — manifest + build script, installed in RamAir team and discoverable via `@ParlayVU` mention. CH + ULC team installs pending.
- ✅ **Bind command extended** — `@ParlayVU bind this channel to <client>` now recognizes any active client (reads from `list_clients()` + `load_client_config()`), not just RamAir.
- ✅ **Tavus persona registry** in [ARCHITECTURE.md §6](./ARCHITECTURE.md).
- ✅ **Native Teams video scoping doc** at [docs/scoping/native-teams-video-and-screen-share.md](./docs/scoping/native-teams-video-and-screen-share.md) (4–5 week build; deferred until forcing function).

**Previous (last week):**

- ✅ **Tenant migration** — all infra moved from Baker Strategy Group Azure/Entra to ParlayVU's own subscription + tenant.
- ✅ **`save_meeting_notes` tool** with 10-field structured records + DOCX template renderer (bullet-list + table-row duplication, multiple placeholder aliases).
- ✅ **Streaming with mid-tool narration** so Nathan doesn't go silent during long-running tool calls.
- ✅ **Date awareness in prompt** — relative date references resolve to specific calendar dates.
- ✅ **Idempotent setup scripts** — full re-bootstrap of Azure + Entra + GitHub Actions.

---

## Next up

Three short items committed for the next session — the first is small and unblocks proper Nathan behavior in the new internal tenants:

### Track 4.5: Default to bound client_id in Nathan's tool calls (~30 min)

**Goal:** When Nathan is invoked in a Teams channel bound to client X, his `get_project_context` / `read_client_file` calls default to client X without him having to extract the client name from the user's message.

**Problem (observed in diagnostics):** Even though `_build_client_preferences_context("parlayvu")` injects the active client into the system prompt, Nathan still tried to extract "RamAir" from text and called `get_project_context(client_id="ramair")`. He answered as if reading RamAir docs even when he should be reading ParlayVU's.

**Approach:** Strengthen the surface-rules system prompt to say *"You are operating in the context of client_id={X}. Use this client_id for every tool call unless the user EXPLICITLY names a different client by full name."* Move the per-client banner from a soft preference to the top of `NATHAN_TAVUS_SURFACE_RULES` / `NATHAN_TEAMS_CHAT_SURFACE_RULES`. Add a test that asserts Nathan called the tool with the bound client_id.

**Status:** Appears to be working in practice — 2026-05-27 smoke test in 3 real client channels (christshope/ramair/ulcannarbor) had Nathan correctly answering from the bound client's content. **But** none of those prompts cross-named another client, so the original failure mode isn't fully retested. Still worth adding the explicit cross-naming test (e.g. "@Nathan tell me about RamAir" in the Christ's Hope channel — should Nathan stay on christshope or follow the explicit name?) and pinning the bound client more firmly in the surface rules. Downgraded from blocker to follow-up.

### Track 5: Cross-session memory (Phase A = Teams only, ~2 hr)

**Goal:** Nathan remembers prior conversations within a Teams channel thread. Today he's stateless per call — when David answers a question Nathan asked, Nathan has no memory he asked it. (Tavus has the same problem but the integration is subtler — its OpenAI chat-completions protocol means the caller already sends per-call history; deciding how to dedupe vs storing cross-session-only is a separate design call. Deferring Tavus to Phase B.)

**Phase A schema** — new table in [models.py](./app/models.py) mirroring the [`AgentEvent`](./app/models.py) pattern:

| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `client_id` | str(64) indexed | |
| `conversation_id` | str(256) indexed | Bot Framework conv id; stable per Teams channel/thread |
| `surface` | str(32) | `"teams_chat"` for Phase A; `"tavus"` for Phase B |
| `role` | str(16) | `"user"` or `"assistant"` |
| `content` | Text | final text only — skip tool calls; the assistant's text already captures the gist |
| `created_at` / `updated_at` | via TimestampMixin | |

Composite index on `(client_id, conversation_id, created_at)`. Schema bootstraps via `Base.metadata.create_all()` in `initialize_database()`; no Alembic yet (per `app/database.py`).

**Phase A integration points:**
- New module `app/conversation_memory.py` with `load_recent_turns(client_id, conversation_id, limit=20, ttl_days=7)` + `append_turn(client_id, conversation_id, surface, role, content)`. Lazy TTL via `created_at >= now() - interval '7 days'` in the load query; periodic delete job later.
- Wire into `_handle_teams_message` (around `app/main.py:739`): load → prepend to the user-only message list → call `run_nathan_conversation` → append both user and assistant turns to the store.
- Test in `tests/test_teams_chat_nathan.py`: mock `load_recent_turns`, assert turns appear in the Nathan message array before the current text.

**Phase B (Tavus, separate PR):** decide cross-session-only vs dedupe-with-per-call; resolve Tavus session/conversation id semantics. Defer until after Phase A is in use.

**Status:** Phase A planned, not started. Estimate ~2 hr.

### Track 6: Phoenix-4 upgrade (~30 min when GA)

**Goal:** Better avatar fidelity. Phoenix-3 is fine; Phoenix-4 is meaningfully better at lip sync and micro-expressions.

**Approach:**
- Replace `default_replica_id` on all three personas (`p02372056aec`, `p7017121a743`, `p577962cd534`) from `ra534cde00e5` to the Phoenix-4 equivalent.
- One-line patch via `Update-NathanPersonaLLM.ps1` (need to confirm whether replica swap requires a new script or can ride on the existing one).

**Status:** Blocked on Phoenix-4 GA availability for our Tavus account. Check Tavus dashboard / docs.

---

## Why we're NOT adopting Tavus's built-in knowledge base or cross-session memory

Tavus markets RAG ("30ms retrieval") and cross-session memory as built-in features. We deliberately implement our own equivalents because:

- **Cross-surface knowledge** — our `.md` files in `client_artifacts/` are read by both Tavus Nathan AND Teams-chat Nathan. Tavus's KB only works on Tavus.
- **Auditable + version-controlled** — every `.md` is in git; you can `cat` what Nathan knows, `git diff` what changed, rollback bad summaries. Tavus's KB is a black box.
- **No vendor lock-in for client knowledge** — swap avatar providers tomorrow and our knowledge is intact.
- **One LLM provider** (Anthropic) for ingestion + answers — simpler debugging.
- **Speed parity in practice** — `get_project_context` is a file system read (sub-ms), faster than Tavus's "30ms retrieval" claim for the pre-ingested path.

See [DECISIONS.md](./DECISIONS.md) for the full reasoning.

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
