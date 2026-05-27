# ParlayVU Roadmap

> What's next, in plain language. Updated when we ship or commit to new work.

**Last updated:** 2026-05-26 (late-night refresh — bot auth fix in flight)
**See also:** [ARCHITECTURE.md](./ARCHITECTURE.md) for current state, [DECISIONS.md](./DECISIONS.md) for the why.

---

## ⚠️ Active blocker — finish before anything else

**Teams bot Bot Framework auth fix — server side DONE, Teams Admin Center upload PENDING.**

The Azure Bot Service was created with `msaAppId = 2dc8aa66-...` carried over from the Baker Strategy tenant migration. That appId doesn't exist in the ParlayVU tenant, so every Bot Framework reply hit OAuth 400 at the token endpoint and returned 502 to Microsoft. Bot was silent in all 5 teams. (Track 4's "verify in real Teams" step was deferred and never actually ran, so this was never caught.)

What's already done (this session):
- ✅ New app registration `parlayvu-bot` (appId `ea0775e7-a6ae-4f70-9f4b-3409a06a29a5`) created in ParlayVU tenant with 2-year secret
- ✅ Azure Bot Service deleted + recreated pointing at the new appId; MSTeams channel enabled
- ✅ Container App env vars `TEAMS_APP_ID` + `TEAMS_APP_PASSWORD` updated → revision `parlayvu-api--0000019` active
- ✅ Direct OAuth test confirmed: `client_credentials` grant returns valid Bot Framework token (3599s expiry)
- ✅ `infra/teams-app/manifest.json` updated: kept `manifest.id` stable (`2dc8aa66-...`, the catalog identity) but changed `bots[0].botId` to `ea0775e7-...`. Bumped `version` to `1.0.1`. Zip rebuilt at `infra/teams-app/parlayvu-teams-app.zip`.
- ✅ `scripts/Setup-ParlayvuBot.ps1` now requires `-TeamsAppId` (no hardcoded default) and refuses to run if the appId doesn't exist in the current tenant
- ✅ `deploy-api.yml` triggers on `client_artifacts/**` so parlayvu/bakerstrategy scaffold actually deploys
- ✅ Commits pushed: `8e190c8` (auth fix), `3fba08c` (restore stable manifest.id), `3b1d16c` (version bump)

What David needs to do to finish the fix (~5 min):
1. Open https://admin.teams.microsoft.com → **Teams apps** → **Manage apps**, search `ParlayVU`
2. There should be **two** entries: the orphan from the first wrong upload (id `ea0775e7-...`, 0 installs) and the original (id `2dc8aa66-...`, 5 installs). **Delete the orphan first.**
3. Click the original entry → **Update** → upload the rebuilt `infra/teams-app/parlayvu-teams-app.zip` (version 1.0.1)
4. Wait 3-5 min for Microsoft to propagate the new manifest to the 5 existing team installs
5. Test in any team channel: `@ParlayVU bind this channel to <client>`. Expected: bot replies *"This channel is now bound to ..."*.
6. If still silent after 10 min: uninstall + reinstall the bot in one team (e.g., RamAir) to force-bust Teams' local manifest cache, then retry.

Once verified, also worth a smoke test:
- `@ParlayVU what's on the roadmap?` in the new ParlayVU team's General → expected: Nathan answers from synced repo docs in `client_artifacts/parlayvu/00_Client_Brief/`

If Nathan answers but reads RamAir docs instead of ParlayVU docs (we saw this in diagnostic), it's the secondary tuning issue noted under **Next up**.

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

**Status:** Not started. Small enough to bundle into the Teams-bot verification session.

### Track 5: Cross-session memory (~4–6 hours)

**Goal:** Nathan remembers prior conversations across Tavus sessions and Teams chat threads. Today he's stateless per call — the only persistent memory is filed meeting notes + ingested reports.

**Approach (lean — own the data, not vendor lock):**
- New `conversation_turns` table in Neon Postgres keyed by `(client_id, conversation_id)`, storing last ~20 turns with TTL (~7 days).
- On every Tavus + Teams call, load prior turns and prepend to the message list before calling Nathan.
- After the response, append the new turn.
- Works on **both** surfaces (Tavus + Teams) — that's why we own this instead of using Tavus's built-in cross-session memory feature (which only works on Tavus).

**Status:** Not started. ~4–6 hr including schema migration + tests.

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
