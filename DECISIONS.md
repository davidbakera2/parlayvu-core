# Architecture Decisions

> The "why" behind key calls so future-us doesn't re-litigate them. Each entry: what we chose, what we explicitly didn't, why, and what would make us revisit.

**See also:** [ARCHITECTURE.md](./ARCHITECTURE.md) for current state, [ROADMAP.md](./ROADMAP.md) for what's next.

---

## 1. Tavus over HeyGen for avatar

**Chosen:** Tavus CVI with Phoenix-3 model. Persona points at our custom LLM endpoint.

**Considered and rejected:** HeyGen Streaming Avatar API.

**Why Tavus:**
- Tavus's CVI is a complete conversation pipeline (STT + turn-taking + barge-in + TTS + avatar). HeyGen Streaming Avatar is just a video stream — you build conversation logic yourself. That's 4-6 weeks of integration to match what Tavus gives us out of the box.
- ~1-second response latency vs. 2-4 seconds for a custom HeyGen pipeline. Latency is the single biggest "is this a real person?" UX delta.
- The custom_llm hook lets us plug in Claude Opus 4.7 + tools as Nathan's brain.
- Visual fidelity tradeoff: HeyGen is slightly better in close-up shots. Doesn't matter when Nathan is one tile of many in a Teams call.

**What would make us reconsider:**
- Tavus pricing changes that make it >$500/mo for active client work
- Tavus's turn-taking falls apart in noisy multi-person Teams calls (we'd end up wrapping their stream anyway, at which point HeyGen's flexibility wins)
- A specific need for voice cloning quality that exceeds Tavus's options

**Migration cost if we change our mind:** ~1 week of work to swap the avatar provider abstraction at `app/avatar/`.

---

## 2. Document-dumping over RAG for client memory (today)

**Chosen:** `get_project_context(client_id)` reads the top 3 markdown files from each standard folder in `client_artifacts/<client>/`, caps each at 6K chars, dumps the whole blob into Nathan's context.

**Considered and rejected (for now):** Proper RAG with embeddings, vector store, chunked retrieval, citations.

**Why document-dumping today:**
- One real client (RamAir) with ~20 markdown files total. Token budget is comfortable.
- Building RAG infrastructure first means delaying everything else.
- The infrastructure-vs-Claude tradeoff: Claude is already extremely good at scanning a 20K-character context and finding the relevant parts. The marginal value of retrieval over dumping is small at this scale.
- Shipping is more valuable than scaling for a problem we don't yet have.

**What would make us reconsider (any of these):**
- Any client has >30 markdown files
- We accumulate >10 saved meeting notes per client (those grow quickly with regular cadence)
- Nathan needs to answer specific historical questions ("what did we decide about subject lines in March?") and starts getting them wrong
- Token costs per Tavus turn start mattering

**When we build it:** pgvector in Neon (already a Postgres user, no new infra), Voyage-3-lite embeddings (Anthropic-recommended), hybrid retrieval (vector + Postgres full-text search). Two complementary tools: keep `get_project_context` for the always-cheap summary, add `search_project_memory(client_id, query, k=5)` for targeted lookup.

**Cost when we build it:** ~1 day of focused work.

---

## 3. One Nathan brain across every surface

**Chosen:** All conversational surfaces for Nathan (Tavus avatar, Teams chat, Slack later, SMS later, email later) route through the same `/v1/chat/completions` endpoint. Each surface is a thin adapter that translates its native format into OpenAI Chat Completions messages.

**Considered and rejected:** Separate Nathan logic per surface (which is actually what we have *today* — Tavus uses `/v1/chat/completions`, Teams uses the older agent graph).

**Why one brain:**
- Prompt updates apply everywhere. Add a tool, every surface gets it.
- New surfaces become trivial — write a Bot Framework / Slack / SMS adapter once, done.
- The cost of N brains is N system prompts to maintain, N tool registries, N anti-hallucination rule sets that can drift.
- All Nathan's intelligence is in one place (`app/nathan_llm.py` + tools). Surface adapters are dumb plumbing.

**What we deliberately accept:**
- The OpenAI Chat Completions format isn't a perfect fit for every channel (Teams has adaptive cards, Slack has blocks). Surface adapters do the translation; Nathan's responses are plain prose by design.
- The single endpoint is now a critical dependency. We mitigate with the `/readiness` check and Container Apps's scaling (min 1, max 3 replicas).

**When this might break down:** If a surface needs fundamentally different conversation patterns (e.g., async email threads spanning days). Then we'd consider a sister endpoint with different memory semantics, not a fork of Nathan.

---

## 4. `client_artifacts/` is the source of truth for client knowledge (with per-client config + Teams-first templates)

**Chosen:** Each client gets a folder `client_artifacts/<client_id>/` with a standard 6-folder structure (00_Client_Brief, 01_Source_Material, 02_Planning, 03_Deliverables, 04_Approvals, 05_Performance) **plus `06_Templates/`** for Word/DOCX templates. The folder ships in the Docker image. Postgres `project_memory` holds metadata + audit trail but defers to flat files for content.

**Per-client config lives at `client_artifacts/<client_id>/config.yaml`** — Teams team_id, channel_id, meeting-notes folder, template path (defaults to `06_Templates/Meeting_Notes_Template.docx`), and prompt-time preferences (pronunciation, tone, authorized contacts). This replaced the singleton `M365_FILES_TEAM_ID` / `M365_FILES_CHANNEL_ID` env vars that previously blocked us from serving more than one client at a time. See `app/client_config.py`.

**Templates are Teams-first.** Clients open `06_Templates/Meeting_Notes_Template.docx` in Word directly from their Teams channel, edit it, and save back. The repo copy at `client_artifacts/<client_id>/06_Templates/Meeting_Notes_Template.docx` is a starter (uploaded to Teams once at onboarding) and a cold-start fallback if Teams is unreachable. This inverts the original local-first design once we had real clients who needed to own their templates.

**Considered and rejected:**
- Postgres-as-truth (with files as derived artifacts) — clients can't see/edit, harder to grep, requires sync logic
- Teams files / SharePoint as truth (with code reading via Graph) — adds Graph latency to every read, can't ship templates in the image, harder to test locally
- Hybrid as peers (what we had at the start) — drift between sources, confusing

**Why files in repo:**
- Templates are version-controlled with the code that uses them. Update template, push, CI deploys both.
- Local testing works without M365 access.
- `grep` works. Diffing works.
- Clients can see their content rendered (we already publish back to Teams via `save_meeting_notes`).

**What we deliberately accept:**
- `client_artifacts/` is checked into git. Fine for non-confidential demos and the RamAir engagement. Becomes a problem the moment a client requires NDA-grade isolation.
- Migration path when it matters: a `client_artifacts_private/` tree git-ignored locally and synced from a separate private repo or S3 bucket per client. Same code path; just a different mount.

**When this might break down:** Confidential clients, very large source material (videos, datasets), or any content that shouldn't sit in a public Docker image.

---

## 5. Lean tools over building infrastructure (the May 25 lesson)

**Chosen:** When adding a new Nathan capability, default to "give Claude one small tool and update the prompt" before reaching for "build a system."

**Considered and rejected** (mostly by me, claude, after David rightly called me out): proposing 2-3 day builds for things Claude can already do with one extra tool.

**Why:**
- Claude is genuinely good at design, writing, reasoning. The "skill" is access, not infrastructure.
- Concrete examples:
  - "Real web design skills for Dylan" → 2-3 hour `write_site_file` tool + prompt update, NOT 2-3 day analyzer + template library + image pipeline
  - "Smart meeting notes" → 10-field structured tool + good prompt, NOT a NLP pipeline
  - "Client preferences" → YAML file per client + auto-inject in prompt, NOT a preferences microservice
- Big infrastructure is hard to change later. Small tools are easy to replace.
- Shipping a thing that's working in 3 hours beats a "real system" in 3 days, especially when we don't yet know what the final shape needs to be.

**The bar for building infrastructure:** Only when (a) we've shipped the lean version, (b) it's hitting a wall, and (c) the wall is structural (data model, scale, integration) rather than "could use polish."

**What this means in practice:**
- Default to adding tools to Nathan, not new services or pipelines
- Per-client config = file, not a microservice
- Templates = repo files, not a CMS
- Memory = document-dumping until clients actually need RAG
- We can always refactor up. We can rarely refactor down.

---

## 6. ParlayVU tenant migration (Baker Strategy → ParlayVU's own M365 + Azure)

**Chosen:** Rebuild all infrastructure in ParlayVU's own Entra tenant and Azure subscription. Decommission Baker Strategy resources after stable operation.

**Considered and rejected:** Cross-tenant access (multi-tenant app registration in Baker Strategy with consent in ParlayVU). Azure subscription transfer.

**Why rebuild over migrate:**
- Tiny surface area (one Container App, one ACR, one resource group). Rebuild = ~3 hours.
- Subscription transfers are operationally complex and have weird permission edge cases.
- All persistent state is external — Neon DB stays where it is, Teams files stay where they are, Tavus persona stays where it is. We're only rebuilding stateless infra.
- Cleaner audit story: ParlayVU's resources live in ParlayVU's tenant, owned by ParlayVU's accounts. No "this lives in our former parent's tenant" confusion.

**What we built to make this fast:**
- Four idempotent PowerShell scripts in `scripts/` that re-create the full Azure + Entra setup. Safe to re-run. Future tenant migrations (if we ever spin up a separate tenant for a big client) are templated.

**What we deliberately accept:**
- The migration revealed our env vars had ~20 orphaned values from previous experiments (`HEYGEN_*`, `M365_*` duplicates, `TEAMS_BOT_*` duplicates). Cleanup is a follow-up task. Doesn't break anything; just noise.
- Nathan's mailbox is currently also Global Admin (see ROADMAP.md "Identity hygiene"). Pragmatic but worth cleaning up.

**What we would do differently next time:**
- Set up the SP elevation + role-grant + re-login sequence as a single script upfront. We hit "AuthorizationFailed" three times because of token caching after role grant.
- Test the JSON-quoting workaround for `az ad app federated-credential create` first. PowerShell + `az.cmd` quoting bit us.
- Verify Bot Framework messaging endpoint and Tavus persona base_url get updated BEFORE decommissioning old infra. (We caught both; just risky.)
- Azure Bot Service itself was a Phase 1-5 gap (Bot Framework messaging needs a Bot Service resource, not just an Entra app reg + Container App). Caught + closed in Phase 7.5 (`scripts/Setup-ParlayvuBot.ps1`).

---

## 7. One Nathan brain, parameterized by surface (Tavus voice vs Teams markdown)

**Chosen:** A single `run_nathan_conversation(messages, *, client_id, surface)` function in `app/nathan_llm.py` runs the Anthropic tool-loop with the same role, the same tools, the same anti-hallucination rules — and a `surface: Literal["tavus", "teams_chat"]` parameter swaps only the response-style block of the system prompt.

The system prompt is assembled from three pieces:
- `NATHAN_BASE_SYSTEM` — role, team, tools, anti-hallucination, never-promise-writes-you-can't-do rules (identical everywhere)
- `NATHAN_TAVUS_SURFACE_RULES` — voice rules (2-4 sentence responses, no markdown, narrate while tools run)
- `NATHAN_TEAMS_CHAT_SURFACE_RULES` — async chat rules (markdown OK, bullets/headers/code-blocks fine, no live-meeting framing)

`/v1/chat/completions` (Tavus) passes `surface="tavus"`. `/teams/messages` (Bot Framework) passes `surface="teams_chat"`. Default is `"tavus"` for backwards compat.

**Considered and rejected:**
- Separate Nathan implementations per surface — would have drifted within a sprint
- One blob prompt that says "if voice then X, if chat then Y" — Claude weighs both rules even when one shouldn't apply; cleaner to physically include only the active block
- Per-surface tool registries — no real reason to hide tools by surface; the same client questions come up in both places

**Why this is the right shape:**
- Adding a new surface (Slack, SMS, email) = write an inbound adapter + add one constant string to `nathan_llm.py`. Zero changes to the tool loop.
- Prompt bug fixes apply everywhere automatically.
- Tests pin both surface strings independently so neither can silently bleed into the other.

**What this enabled in practice (Track 4, May 26):** Nathan-on-Teams now answers project questions, calls `web_search`, reads ingested reports, and saves meeting notes — the same brain that runs on Tavus calls. Before this, Teams chat went through the older LangGraph wrapper that could *route* to a specialist but couldn't directly answer.

**When we'd revisit:** If a surface genuinely needs different memory semantics (async email threads spanning days, say), the right move is a sister entry-point with its own memory layer, not a fork of Nathan.

---

## 8. Pre-ingested markdown summaries beat on-demand RAG (for now)

**Chosen:** When a client drops a PDF or .docx into their Teams channel, the `client_file_ingester` service pulls it through Sonnet 4.6 once and writes a structured markdown summary into `client_artifacts/<client>/01_Source_Material/reports/`. From then on, `get_project_context` includes the summary in Nathan's context at conversation start — zero retrieval latency.

For files Nathan *hasn't* pre-ingested (or when he needs the verbatim text), he has two fallback tools: `list_client_files(client_id)` and `read_client_file(client_id, path)`, both routed through `app/tools/text_extractors.py` (pypdf + python-docx).

**Considered and rejected (for today's scale):**
- pgvector + embeddings + chunk retrieval on every turn — real engineering, real ops surface, and we have ~5 files per client
- Tavus's built-in "30ms RAG" — Tavus-only; our Teams-chat Nathan would be blind to it
- Read-on-every-call from Graph — Graph latency (300-800ms) on the hot path for every conversation

**Why pre-ingest + markdown summaries:**
- The summarization happens **once**, not every turn. At call time, reading the summary is sub-ms file I/O.
- Summaries are version-controlled. `git diff` shows when Nathan's understanding of a report changed.
- Cross-surface: Tavus Nathan and Teams Nathan read the same `.md` files. Tavus's KB only works on Tavus.
- The on-demand tools cover the long tail without forcing us to ingest everything.
- Sonnet 4.6 produces *better* structured summaries than naive chunking — it preserves decision context, not just text proximity.

**When we'd reconsider (add real RAG on top, not replace this):**
- Any client crosses ~30 markdown files
- We accumulate >10 saved meeting notes per client
- Nathan needs to answer specific historical questions ("what did we decide about subject lines in March?") and starts getting them wrong
- See Decision #2 (document-dumping) for the build trigger and approach

**What this means for the Tavus comparison:** We deliberately don't adopt Tavus's KB or cross-session memory features. See ROADMAP.md "Why we're NOT adopting…" for the full reasoning. Short version: our knowledge layer needs to work across Tavus + Teams + future surfaces, and Tavus's features are Tavus-only.

---

## 9. Setup scripts must fail-fast on identity drift, not silently misconfigure

**Chosen:** Any script that wires an Azure resource to an Entra app registration MUST verify the appId exists in the current tenant before proceeding. If it doesn't, fail loudly with a remediation hint, never with a default.

**Considered and rejected:** Hardcoded sensible defaults (what `scripts/Setup-ParlayvuBot.ps1` originally had — `$TeamsAppId = "2dc8aa66-..."` as a parameter default).

**Why this matters (the 2026-05-26 outage):**
- We migrated tenants (Baker Strategy → ParlayVU) earlier in the week. The migration plan rebuilt the Container App + ACR + GitHub Actions but did not recreate the bot's app registration in the new tenant.
- The orphaned `TEAMS_APP_ID=2dc8aa66-...` env var pointed at an app reg that existed in Baker Strategy but not ParlayVU.
- `Setup-ParlayvuBot.ps1` accepted that orphaned appId as its hardcoded default and created the Azure Bot Service with it.
- Azure Bot Service doesn't validate that msaAppId references a real app reg — it just stores the GUID.
- Result: Bot looked configured. `/teams/status` returned `configured: true`. Tests passed. But every Bot Framework reply silently 400'd at `login.microsoftonline.com/.../oauth2/v2.0/token` because the appId didn't authenticate against anything in this tenant.
- We didn't notice for ~24h because Track 4's "verify in real Teams" step was deferred and never actually run.

**What we changed:**
- `Setup-ParlayvuBot.ps1` now requires `-TeamsAppId` (no default) AND runs `az ad app show --id $TeamsAppId` before doing anything. If that 404s, the script throws with the remediation command (`az ad app create ...`).
- Added an `infra/teams-app/README.md` troubleshooting row for the OAuth-400 symptom and the duplicate-catalog-entry symptom.

**General principle:** Any operation that crosses an identity boundary (tenant, subscription, app reg, service principal, managed identity) needs a precondition check at the top of the script. Migrations leak orphaned identifiers more often than they leak data — and orphaned identifiers silently misroute calls instead of erroring on use.

**What else would benefit from the same treatment:**
- `Setup-ParlayvuAppRegistration.ps1` — could verify the Graph app permissions are admin-consented before exiting "success"
- `Setup-ParlayvuGitHubActions.ps1` — could verify the federated credential subject matches the repo's actual `repository_owner/repository_name`
- Any future cross-tenant or cross-subscription script

**Migration cost when we don't do this:** ~24h of bot silence that nobody noticed until the user tried to actually use it.

---

## 10. Teams app `manifest.id` is the catalog identity — never change it

**Chosen:** The Teams app manifest has two distinct identifiers; treat them as orthogonal:
- `manifest.id` — the catalog identity. **Stable for the life of the app.** Changing it means Teams treats your upload as a brand-new app, and your existing team installations are orphaned.
- `bots[0].botId` — the Bot Framework appId. Can change whenever the underlying bot's app reg changes.

**Considered and rejected (the bug):** Doing a find-and-replace on the manifest to swap the old bot appId for the new one — without realizing both fields had been set to the same GUID at scaffold time and the find-and-replace would change both.

**Why this matters (also from the 2026-05-26 outage):**
- Original `manifest.json` had `id = botId = 2dc8aa66-...`. Common shortcut at scaffold time — reuse the bot's appId as the manifest id since you need a GUID anyway.
- When we fixed the bot, a naive find-and-replace changed both → uploaded zip had `id = botId = ea0775e7-...`.
- Teams Admin Center saw a new manifest.id and treated it as a brand-new app. Created a duplicate catalog entry. Existing team installs still pointed at the dead bot in the old entry. Bot stayed silent.
- Fix: restored `manifest.id` to the original GUID, kept `botId` at the new one, bumped version `1.0.0 → 1.0.1` (Teams refuses to apply an Update if the version hasn't bumped).

**What we changed:**
- `infra/teams-app/README.md` now documents the two-id distinction prominently and warns against reusing the bot appId as the manifest id when scaffolding a new bot.
- `manifest.json` has comments... actually JSON doesn't allow comments. The README is the comment.

**General principle:** When scaffolding a Teams app, generate a fresh independent GUID for `manifest.id` (`uuidgen` / `[guid]::NewGuid()`) and never reuse another identifier for it.

---

## 11. Workflow Packages for parlayvu.ai (modeled on viktor.com) — spec-driven, not LangGraph Studio / heavy graphs

**Chosen:** "Different packages of workflows" are first-class, versioned, human-editable artifacts:
- Living Markdown spec (Mermaid + phase tables + "how to develop/modify" section, exactly like `video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md`).
- Associated prompt additions, tool bindings, optional state/FSM, config schema, UI templates.
- Activated per-client (via `client_artifacts/<id>/config.yaml` `active_workflows` or conversational "@Nathan activate the Podcast Parlay package").
- Nathan (single brain) loads the active packages' specs/prompts/tools at runtime and orchestrates (with approvals, memory, specialists like Alex/Dylan).
- Example packages: `podcast-parlay` (video prod), `meeting-notes`, `client-site` (Dylan/Astro deploys), future ad-audits, content-repurpose, etc.
- Platform (parlayvu.ai) provides catalog, install/activate UI, per-package dashboards — like viktor.com's capabilities but verticalized for agency/marketing/video workflows + deep MS365/Teams + Resolve integration.

**LangGraph / Studio policy:**
- Use LangGraph *lightly and internally only*: thin router (`app/graph.py` Nathan → specialist), small sub-graphs for specialist coordination (e.g. `meeting_strategy.py`).
- Never use LangGraph Studio (or authoring heavy graphs) as the surface for defining or "packaging" customer workflows.
- Rationale (proven on the first package + explicit in PODCAST_PARLAY... and history):
  - viktor.com itself: "No workflow builder. No graph editor. The workflow is the prompt." Conversational activation + execution is the product strength.
  - Editability: Users edit MD in any editor, git diff, PR, A/B per client by branching the spec. "The workflow doc itself is designed to be upgraded after every real episode."
  - Our primitives already solve the hard parts (approvals as durable gates/iteration, parlay_state FSM + disk mirrors, project memory, Teams cards, one Nathan brain parameterized by surface).
  - Past experience: LangGraph Studio felt "riddled with errors" for small edits; hid state; not portable/version-friendly for non-dev package authors.
  - Scaling packages: MD + Python + existing approvals is dramatically easier/faster to manage, test (chat with Nathan in internal channel), and upgrade than rebuilding orchestration on graphs + Studio + Cloud.
- If a future package needs complex branching state, implement the *internal* logic as a small encapsulated LangGraph (exposed only via tools), while the package spec + user interface remains prompt/spec-driven.

**Why this matches the viktor.com goal:**
- Users describe or select a package ("run the Podcast Parlay for Ep05", "activate ad audit package").
- It does the real work (tools, deploys, renders via Resolve fallback or API, files, approvals).
- Proactive/scheduled/heartbeat possible via existing infra.
- Team context via client_artifacts + memory.
- "Packages" are the catalog of repeatable, high-value workflows (not one-off prompts).
- parlayvu.ai becomes the "hire the AI + choose your packages" platform, with Nathan as the coworker.

**Status as built (2026-06-03) — be precise about what actually exists:**
- ✅ `app/workflow_packages/__init__.py` holds the whole foundation today: a `WorkflowPackage` dataclass, a `KNOWN_PACKAGES` registry dict, `register_package`/`get_active_packages`/`get_package`/`load_spec`, and `inject_package_context`. **There is no separate `registry.py` or `base.py`** — earlier drafts of this entry and `docs/workflow-packages-design.md` named those files, but the logic was inlined into `__init__.py`. There are **no per-package directories** (`podcast_parlay/tools.py`, `state.py`, `config.schema.json`, `ui/`) yet.
- ✅ Per-client activation config: `client_artifacts/<id>/config.yaml` `active_workflows` is parsed into `ClientConfig` (`app/client_config.py`).
- ✅ Nathan prompt construction calls `inject_package_context` (`app/nathan_llm.py`).
- ⚠️ **Prompt injection is currently unconditional and surface-agnostic** — the Podcast-Parlay prompt block is also hardcoded into `NATHAN_BASE_SYSTEM`, so it fires for every client and on the Tavus voice surface too. This contradicts Decisions #3 and #7 and needs fixing.
- ❌ **Tool registration is NOT yet conditional on active packages** — the video tools are added to the global `NATHAN_TOOLS` list unconditionally; a package's `tool_names` is inert metadata that nothing consumes.
- ❌ No `/workflows/*` platform endpoints or activation UI yet.

**Planned (not yet built):** per-package dirs, conditional tool gating driven by `active_workflows`, surface-aware prompt injection, platform endpoints + activation UI. All packages should go through the same approvals + memory + audit.

**What we deliberately rejected:**
- Rebuilding the orchestration layer on LangGraph graphs + Studio as the primary authoring tool for packages.
- Treating each "package" as a deployable LangGraph that customers configure in a canvas.
- Heavy dependence on LangGraph Platform/Cloud for execution (our FastAPI + direct LLM loops + custom state already work and are simpler to operate/audit).

**When we'd revisit:**
- A package's internal logic demonstrably benefits from visual graph debugging in Studio *and* the package authors are comfortable with it (rare for our target users).
- LangGraph adds unique multi-tenant persistence/scaling/observability we can't achieve otherwise.
- Customer demand for a no-code canvas for *their own* custom workflows (then offer it as an advanced/power-user feature, not the default for core packages).

**Migration cost if we change mind:** High for the platform (would require re-expressing all specs as graphs, new UI, new deployment story). Low for internal sub-logic (we already use small graphs).

**Cost to implement the chosen path:** Low incremental in principle (registry + prompt injection + a couple more packages). **Caveat (2026-06-03):** the Podcast Parlay package is currently a scaffold, not a working proof — its tools don't yet close the loop (stage vocabulary is inconsistent across `parlay_state.py` / `video_parlay_tools.py` / `nathan_llm.py`, and client approvals never call `record_parlay_decision`, so the state machine never advances). The *model* (spec + prompt + tools + approvals) is sound; this specific package needs the wiring finished before it proves anything.

