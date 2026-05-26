# ParlayVU System Overview

> A senior digital marketing agency, run by 13 AI agents, that joins client meetings and does the work in between.

**Last updated:** 2026-05-25 (commit `9b53ee5`)
**Maintained by:** the team. When something material changes, update this file in the same PR.

> See also: [ROADMAP.md](./ROADMAP.md) for what's next, [DECISIONS.md](./DECISIONS.md) for the why behind key architectural calls.

---

## 1. The 30-second pitch

**Nathan Ellis** is the lead orchestrator — a Tavus avatar that joins a client's Microsoft Teams meeting as a real participant, listens, talks, looks things up in real time (web, LinkedIn, project files), and files meeting notes when done. Behind Nathan sits a 12-person AI specialist team (Alex visuals, Ava copy, Blake research, etc.) that executes the actual work between meetings. ParlayVU is the platform that orchestrates all of this on top of the client's existing Microsoft 365 tenant.

---

## 2. Runtime architecture

```
                                 ┌─────────────────────────────┐
                                 │   Microsoft Teams Meeting   │
                                 │   (client + Nathan avatar)  │
                                 └─────────────┬───────────────┘
                                               │ video/audio
                                               ▼
                            ┌──────────────────────────────────┐
                            │  Tavus CVI (Daily.co room)       │
                            │  Phoenix-3 avatar + STT/TTS      │
                            │  custom_llm → our API            │
                            └─────────────┬────────────────────┘
                                          │ POST /v1/chat/completions
                                          │ (OpenAI-compatible, bearer auth)
                                          ▼
        ┌─────────────────────────────────────────────────────────────────┐
        │                  parlayvu-api  (FastAPI, Python 3.12)            │
        │                  Azure Container App                              │
        │                                                                   │
        │  /v1/chat/completions ─── Claude Opus 4.7 tool loop ────────┐    │
        │                                                              │   │
        │  ┌─── Nathan's 6 tools ──┐  ┌── HTTP endpoints ────────┐    │   │
        │  │ web_search (Tavily)   │  │ /m365/files/meeting-notes│    │   │
        │  │ fetch_url (Jina)      │  │ /m365/email-drafts       │    │   │
        │  │ list_teams_files      │  │ /teams/messages          │    │   │
        │  │ read_teams_file       │  │ /heygen/live-meetings    │    │   │
        │  │ get_project_context   │  │ /dylan/generate-site     │    │   │
        │  │ save_meeting_notes    │  │ /approvals, /memory/*    │    │   │
        │  └───────────────────────┘  │ /v1/models, /readiness   │    │   │
        │                              └───────────────────────────┘   │   │
        │                                                              │   │
        │  ┌─── Shared services (app/services/, app/) ───────────────┐│   │
        │  │ meeting_notes_service ──► Graph upload + DB audit        ││   │
        │  │ microsoft365 (MicrosoftGraphClient)                      ││   │
        │  │ project_memory (clients, projects, events, outputs)      ││   │
        │  │ approvals (gated actions)                                ││   │
        │  │ teams (Bot Framework dispatch)                           ││   │
        │  │ agents/registry (12 specialist LLM definitions)          ││   │
        │  │ agents/workflows (meeting_strategy + others)             ││   │
        │  │ avatar/tavus (provider abstraction)                      ││   │
        │  └──────────────────────────────────────────────────────────┘   │
        └─────────────┬──────────────────┬───────────────┬────────────────┘
                      │                  │               │
                      ▼                  ▼               ▼
            ┌──────────────────┐  ┌────────────┐  ┌──────────────────┐
            │ Neon Postgres    │  │ MS Graph   │  │ Anthropic/Tavily │
            │ (project memory) │  │ Teams/M365 │  │ Jina/xAI         │
            └──────────────────┘  └────────────┘  └──────────────────┘
```

---

## 3. The tech stack

### Language + runtime
- **Python 3.12**, **FastAPI**, **Uvicorn** (ASGI)
- **Pydantic v2** for request/response models
- **SQLAlchemy 2.0** + `psycopg2-binary` for Postgres
- **httpx** (async) for all outbound HTTP
- **python-docx** for Word-document generation
- **LangGraph + LangChain** for the agent routing graph (Nathan → specialists)

### LLM providers (per-agent model map in `app/settings.py`)
- **Anthropic Claude Opus 4.7** — Nathan's brain (strategy + tool use)
- **Anthropic Sonnet 4.6** — Ava, Alex, Michael, Nora, Dylan, Codey (content quality)
- **Anthropic Haiku 4.5** — Riley, Casey, Taylor (fast simple ops)
- **xAI Grok 3** — Blake, Jordan, Morgan (real-time social / X intelligence)

### External services
- **Tavus CVI** — Nathan's avatar, voice, conversation pipeline, custom LLM hook
- **Tavily** — web search tool for Nathan
- **Jina Reader (r.jina.ai)** — URL-to-markdown for any public webpage (LinkedIn, etc.); no key needed
- **Microsoft Graph API** — Teams files, OneNote, mailboxes, SharePoint
- **Microsoft Bot Framework** — Teams chat dispatch (the `parlayvu-teams-media-bot` .NET service)
- **Cloudflare Pages** — Astro site deployments (Dylan)
- **Resend** — outbound transactional email
- **Neon Postgres** — managed serverless Postgres for project memory

### Infrastructure
- **Azure Container Apps** — runs `parlayvu-api` (and will eventually run `parlayvu-teams-media-bot`)
- **Azure Container Registry** (`parlayvucore`) — Docker image storage
- **Microsoft Entra ID (Azure AD)** — service principal `parlayvu-github-actions` with OIDC federated credential for CI

### CI/CD
- **GitHub Actions** — three workflows:
  - `deploy-api.yml` — on push to main: build Docker image, push to ACR, update Container App. Uses OIDC (no stored secrets for Azure auth).
  - `deploy-teams-media-bot.yml` — `workflow_dispatch` only (not in production yet)
  - `deploy-teams-media-worker.yml` — `workflow_dispatch` only (Windows .NET 8, deferred)

---

## 4. The agent team

| Agent | Role | Model |
|---|---|---|
| **Nathan Ellis** | Lead Orchestrator — strategy, routing, client-facing | Claude Opus 4.7 |
| **Alex Rivera** | Visuals & Design | Sonnet 4.6 |
| **Ava Hosseini** | Content Writing | Sonnet 4.6 |
| **Blake Quinn** | Intelligence & Insights (research, strategy) | Grok 3 |
| **Casey Johnson** | Engagement & Community | Haiku 4.5 |
| **Codey Miner** | Coding & Integrations | Sonnet 4.6 |
| **Dylan Brooks** | Web & Deployment (Astro + Cloudflare) | Sonnet 4.6 |
| **Jordan Lee** | Social Execution | Grok 3 |
| **Michael Stone** | Sales & Conversion | Sonnet 4.6 |
| **Morgan Reyes** | Paid Media | Grok 3 |
| **Nora Patel** | Partnerships & Affiliates | Sonnet 4.6 |
| **Riley Carter** | Publishing & Distribution | Haiku 4.5 |
| **Taylor Kim** | Customer Success & Retention | Haiku 4.5 |

Each agent has their own M365 mailbox (`nathan@parlayvu.ai`, `alex@parlayvu.ai`, etc.) for outbound communication and a system prompt in `app/agents/prompts.py`.

---

## 5. Project memory

Two sources, with priority:

1. **Neon Postgres** (primary, when populated) — `clients`, `projects`, `agent_events`, `generated_outputs`, `approvals` tables in `app/project_memory.py` and `app/database.py`.
2. **`client_artifacts/<client_id>/`** flat-file fallback — standard folder structure:
   - `00_Client_Brief/` — engagement brief, templates
   - `01_Source_Material/` — raw inputs
   - `02_Planning/` — project plan, schedules
   - `03_Deliverables/` — drafts and approved work
   - `04_Approvals/` — approval packets
   - `05_Performance/` — KPIs and dashboards

Currently only `ramair` is populated. The `get_project_context` tool tries the DB first, then falls back to the markdown files in this tree. **Both Postgres and the flat files ship in the Docker image** so production has access.

---

## 6. Integration surfaces

### Tavus (live avatar)
- **One Nathan persona per client.** Each persona shares the same replica (face + voice) but sends a different `X-Parlayvu-Client-Id` header on every custom-LLM call. Our `/v1/chat/completions` reads that header and loads the right `client_artifacts/<id>/config.yaml`, so Nathan publishes meeting notes into the right Teams channel and applies the right pronunciation/tone rules per call.
- **Replica** `ra534cde00e5` — Nathan's face/voice, shared across all client personas.
- **Per-client persona registry:**

  | Client | Persona ID | Client header value |
  |---|---|---|
  | RamAir | `p02372056aec` | `ramair` |
  | Christ's Hope | `p7017121a743` | `christshope` |
  | ULC Ann Arbor | `p577962cd534` | `ulcannarbor` |

- Custom LLM contract: OpenAI Chat Completions format, streaming + non-streaming both supported. Bearer auth via `NATHAN_LLM_API_KEY`. Per-client header is `X-Parlayvu-Client-Id` (see `app/main.py` /v1/chat/completions handler; falls back to `NATHAN_DEFAULT_CLIENT_ID` env var if header is missing).
- **Setup script:** `services/teams-media-bot/scripts/Update-NathanPersonaLLM.ps1 -PersonaId <id> -ClientId <client>` — re-runnable per client whenever a persona's LLM wiring needs to be re-applied.
- **Onboarding a new client persona:** (1) create the persona in the Tavus UI, cloning replica `ra534cde00e5` and writing a client-specific `system_prompt`, (2) run the setup script with the new persona ID and the client_id, (3) add the row to the table above.

### Microsoft Graph
- One **Entra app registration** with permissions: `Files.Read.All`, `Sites.Read.All`, `Mail.Send`, `Notes.ReadWrite.All` (and others)
- Single `MicrosoftGraphClient` in `app/microsoft365.py` is the only thing that talks to Graph — every other module goes through it
- Teams Bot Framework wraps this with `/teams/messages` for inbound bot conversations

### Approvals
- Any write action that touches production (deploy site, send email) goes through `app/approvals.py` first
- Approval cards rendered as Teams adaptive cards
- States: `pending`, `approved`, `rejected`, `changes_requested`, `cancelled`

---

## 7. Deployment

### Production environment
> All resources live in **ParlayVU's own Azure subscription** in **ParlayVU's Entra tenant**, as of the May 25 migration. The old Baker Strategy resources have been decommissioned. See [MIGRATION-PLAN.md](./MIGRATION-PLAN.md) for the history.

- **Tenant ID:** `45b63749-ebe1-48fa-928c-963050843179` (ParlayVU)
- **Subscription ID:** `dc976926-046e-4ce8-8659-4dbf602da289` (Azure subscription 1)
- **Resource group:** `rg-parlayvu-prod` (East US)
- **Container App:** `parlayvu-api` — public ingress on port 8000
- **FQDN:** `parlayvu-api.thankfulriver-96fed9c6.eastus.azurecontainerapps.io`
- **Registry:** `parlayvuacr.azurecr.io`
- **Managed environment:** `parlayvu-env`
- **Service principal (CI/CD):** `parlayvu-github-actions` with OIDC federation to GitHub Actions main branch
- **Entra app registration (Graph):** `ParlayVU Agents` with 14 admin-consented Microsoft Graph application permissions

### Required env vars on the Container App
- `DATABASE_URL` (Neon)
- `ANTHROPIC_API_KEY`, `XAI_API_KEY`
- `TAVILY_API_KEY`
- `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`
- `TAVUS_API_KEY`, `TAVUS_PERSONA_ID`, `TAVUS_REPLICA_ID`, `TAVUS_REPLICA_ID_NATHAN`
- `NATHAN_LLM_API_KEY` (bearer token Tavus sends to our `/v1/chat/completions`)
- `TEAMS_APP_ID`, `TEAMS_APP_PASSWORD`, `TEAMS_TENANT_ID`, `TEAMS_WEBHOOK_SECRET`
- Per-agent `<NAME>_MAILBOX` env vars
- M365 SharePoint targets: `M365_FILES_TEAM_ID`, `M365_FILES_CHANNEL_ID`, `ONENOTE_*`

### CI/CD secrets in GitHub
- `AZURE_CLIENT_ID` → service principal app ID
- `AZURE_TENANT_ID` → `45b63749-...`
- `AZURE_SUBSCRIPTION_ID` → `dc976926-...`
- `ACR_USERNAME` → `parlayvuacr`
- `ACR_PASSWORD` → ACR admin password

### Idempotent setup scripts
All migration / re-bootstrap operations live in `scripts/` as PowerShell:
- `Setup-ParlayvuAzure.ps1` — resource group, ACR, Container Apps environment
- `Setup-ParlayvuAppRegistration.ps1` — Entra app reg + 14 Graph permissions + admin consent + client secret
- `Setup-ParlayvuContainerApp.ps1` — build image, push to ACR, create Container App with all env vars
- `Setup-ParlayvuGitHubActions.ps1` — OIDC SP + federated credential

All scripts are idempotent — safe to re-run.

---

## 8. Development workflow

1. **Branch:** work on `main` directly for now (no PR review process yet — solo dev)
2. **Test locally:** `python -m unittest discover -s tests` (103+ tests as of `9b53ee5`)
3. **Push to main:** triggers `deploy-api.yml` automatically (when changes touch `app/**`, `requirements.txt`, `Dockerfile`, or the workflow itself)
4. **Watch CI:** github.com/davidbakera2/parlayvu-core/actions/workflows/deploy-api.yml
5. **Verify deploy:** `az containerapp revision list --name parlayvu-api --resource-group rg-parlayvu-prod` — image SHA should match latest commit
6. **Smoke test:** `GET https://parlayvu-api.thankfulriver-96fed9c6.eastus.azurecontainerapps.io/readiness` should return `"status": "ready"`
7. **End-to-end test:** start a Tavus conversation with Nathan Ellis persona, exercise the changed surface

---

## 9. What's working vs. what's deferred

### Working today
- Nathan joins (via Tavus shared window) a meeting and converses with Claude Opus 4.7 + 6 tools
- **Streaming with mid-tool narration** — Nathan talks while long-running tools (Graph uploads, etc.) execute so there's no awkward silence
- Web search + URL fetch + Teams file read + project context (RamAir) + meeting notes save
- **10-field structured meeting notes** with template rendering: title, date+time, project, attendees, summary, decisions, action items table, questions, next steps, source material
- **Local-first template loading** from `client_artifacts/<client>/...` (template ships in Docker image); Teams channel is the fallback source
- **Date awareness** — Nathan knows today's date and resolves "tomorrow"/"Friday"/"next week" to specific calendar dates
- **Multiple placeholder names per column** in action items table (`{{ACTION_DATE}}`, `{{DUE_DATE}}`, `{{ACTION_DUE}}` all work)
- Outbound email drafts (with approval gate)
- Astro site generation and Cloudflare Pages deploy (Dylan, via internal HTTP)
- Teams bot dispatch (inbound messages → routed to the right agent via older agent graph — see ROADMAP.md for the "one Nathan, multiple surfaces" unification work)
- OneNote and Teams Files meeting note publishing
- 12-agent specialist team registered and callable via internal routes

### Built but not wired
- **Native Teams video** — Nathan as a real Teams participant (not a shared window). Requires the Windows VM + Graph Communications Media SDK. All scaffolded in `services/teams-media-bot-media-worker/`. **Deferred indefinitely** — Tavus's shared-window flow is fine for v1.
- **Teams Media Bot (.NET service)** — Bot Framework wrapper. Builds, but `.NET 10 preview` build is currently failing. Not deployed.
- **HeyGen avatar paths** — removed in Phase 1 cleanup. Provider abstraction (`app/avatar/`) is in place if we ever revisit.

### Known follow-ups
- Strip orphaned `HEYGEN_*` env vars from the Container App (cosmetic, no behavior impact)
- Tavus custom LLM auth currently uses a bearer token in plain env var — fine for now but worth moving to Key Vault when we have more clients
- `client_artifacts/` is checked into git — fine for `ramair` but won't scale to clients with confidential data; needs a "private clients live elsewhere" pattern when we add client #2 (see ROADMAP.md "Multi-client foundation")
- Templates are per-client and **Teams-first**: the canonical copy lives in the client's Teams channel under `06_Templates/`, so clients can edit in Word and save back without a deploy. A starter copy ships in the repo at `client_artifacts/<client>/06_Templates/` and is also used as a cold-start fallback if Teams is unreachable. See [MEETING-NOTES-TEMPLATE-GUIDE.md](./docs/MEETING-NOTES-TEMPLATE-GUIDE.md) for authoring.

---

## 10. The repo at a glance

```
parlayvu-core/
├── .github/workflows/
│   ├── deploy-api.yml           # push → ACR → Container App (OIDC auth)
│   ├── deploy-teams-media-bot.yml      # dispatch-only
│   └── deploy-teams-media-worker.yml   # dispatch-only (Windows)
├── app/
│   ├── main.py                  # FastAPI app, all HTTP routes
│   ├── nathan_llm.py            # Custom LLM endpoint logic, tool loop (streaming)
│   ├── settings.py              # Per-agent model map, env config
│   ├── microsoft365.py          # MicrosoftGraphClient (sole Graph touchpoint),
│   │                              + DOCX template renderer with list/table duplication
│   ├── project_memory.py        # Postgres ORM + queries
│   ├── approvals.py             # Approval gate logic
│   ├── teams.py                 # Bot Framework dispatch (older agent-graph path)
│   ├── readiness.py             # /readiness checks
│   ├── agents/                  # 12-agent registry, prompts, workflows
│   ├── avatar/                  # Provider abstraction (currently Tavus)
│   ├── tools/                   # Nathan's 6 tool implementations
│   └── services/                # Shared business logic (meeting_notes, etc.)
├── client_artifacts/
│   └── ramair/                  # RamAir project files + meeting notes template
├── scripts/                     # Idempotent PowerShell setup scripts
│   ├── Setup-ParlayvuAzure.ps1
│   ├── Setup-ParlayvuAppRegistration.ps1
│   ├── Setup-ParlayvuContainerApp.ps1
│   └── Setup-ParlayvuGitHubActions.ps1
├── services/
│   ├── teams-media-bot/         # .NET Bot Framework service (not deployed yet)
│   └── teams-media-bot-media-worker/  # Windows .NET media worker (deferred)
├── sites/                       # Astro templates for Dylan
├── tests/                       # 103+ tests, unittest
├── docs/
│   └── MEETING-NOTES-TEMPLATE-GUIDE.md   # How to author meeting note templates
├── Dockerfile                   # Python 3.12-slim, copies app/ + client_artifacts/
├── SETUP.md                     # 6 env vars + setup instructions
├── MIGRATION-PLAN.md            # Baker Strategy → ParlayVU tenant migration (complete)
├── ROADMAP.md                   # What's next
├── DECISIONS.md                 # Why behind key architectural calls
└── ARCHITECTURE.md              # This file
```

---

## 11. Where to look when something breaks

| Symptom | First place to look |
|---|---|
| Nathan gives generic answers | Tavus persona dropdown — is it set to "Nathan Ellis"? |
| Nathan promises a write he can't do | `_NATHAN_MEETING_SYSTEM` rule #6 in `app/nathan_llm.py` |
| Tool calls fail | Container App logs: `az containerapp logs show ...` — look for `Nathan tool call:` lines |
| Deploy fails | GitHub Actions → click the red run → check `Log in to Azure` (OIDC) and `Build and push` (image) steps |
| 404 on Tavus calls | Persona's `layers.llm.base_url` must end in `/v1` |
| 401 on Tavus calls | `NATHAN_LLM_API_KEY` mismatch between Container App env and persona config |
| RamAir info missing | Confirm running image is recent (`client_artifacts/` only ships in `3b0ed80`+) |
| Tests fail after refactor | Most likely `patch("app.main.X")` needs to become `patch("app.services.X")` |
| Meeting notes template not used | Check log for `"Meeting notes template loaded from"` — Teams-first now, so it normally reads from the client's Teams `06_Templates/` folder. If that fails, log will show fallback to local `client_artifacts/<client>/06_Templates/` (or generated DOCX if neither works) |
| Action items table shows literal `{{ACTION_DATE}}` | Template uses an alias name; renderer accepts `{{ACTION_DUE}}`, `{{ACTION_DATE}}`, `{{DUE_DATE}}`, `{{DUE}}` — all should work since commit `768eb1f` |
| Nathan goes silent during a save | Streaming or narration regression — check `nathan_llm.py:run_nathan_conversation_streaming` |
| Nathan passes literal "Friday" as a due date | Date awareness regression — check that `_build_current_date_context()` is being prepended to the system prompt |

---

## 12. Keeping this document honest

This file goes stale the moment we ship something new. To prevent that:

- **When you add a new tool to Nathan:** add it to section 6 (Integration surfaces) and section 2 (the diagram)
- **When you add a new HTTP endpoint:** add it to the diagram in section 2
- **When you change CI:** update section 7 and section 8
- **When you add/remove an agent:** update section 4
- **When you move logic into a new module:** update section 10
- **When something breaks in a new way and you fix it:** add the symptom + fix to section 11

If the file is more than a sprint out of date, fix it in the next PR — easier than rewriting from scratch later.
