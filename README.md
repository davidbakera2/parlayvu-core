# ParlayVU Core

ParlayVU.ai is an agentic content operating system for turning source material into coordinated campaign assets, websites, publishing plans, and client-ready follow-up. Nathan is the orchestrator; specialist agents handle strategy, copy, design, deployment, sales, paid media, distribution, partnerships, and client success.

## Current Capabilities

- FastAPI API for Nathan routing and Dylan site generation/deployment.
- LangGraph workflow that routes requests from Nathan to specialist agents.
- xAI Grok-backed LLM integration, with environment placeholders for OpenAI and Groq.
- Dylan tooling that generates Astro + Tailwind marketing sites under `generated_sites/`.
- Cloudflare Pages deployment helper via Wrangler.
- Neon Postgres project memory scaffold for clients, projects, source assets, generated outputs, approvals, and agent events.
- Microsoft 365, Teams, and HeyGen LiveAvatar planned as the primary operating channels.

## Local Setup

1. Create a Python virtual environment.
2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in local secrets.
4. Start the API:

   ```powershell
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

5. Check health:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/health
   ```

## Key Endpoints

- `GET /health` - basic API health.
- `GET /readiness` - consolidated demo/production readiness checks without exposing secrets.
- `POST /nathan` - send a user request to Nathan for routing.
- `POST /dylan/generate-site` - generate a local Astro + Tailwind site.
- `POST /dylan/deploy-site` - build and deploy a generated site to Cloudflare Pages.
- `GET /approvals` - list approval requests by project or status.
- `POST /approvals` - request human approval for client-facing actions.
- `POST /approvals/{approval_id}/decision` - approve, reject, request changes, or cancel an approval.
- `GET /m365/status` - check Microsoft 365 Graph and agent mailbox readiness without exposing secrets.
- `POST /m365/email-drafts` - create an approval-ready draft in a configured agent mailbox.
- `GET /heygen/status` - check HeyGen and avatar readiness without exposing secrets.
- `POST /heygen/live-question` - answer a live project-bound avatar question from project memory.
- `GET /teams/status` - check Teams front-door readiness without exposing secrets.
- `POST /teams/messages` - route an inbound Teams-style message to Nathan.
- `GET /teams/approval-cards` - return pending approvals as Teams-ready cards.
- `POST /teams/approvals/{approval_id}/decision` - record approval decisions from Teams.

## Project Memory

The SQLAlchemy schema starts with:

- `Client`
- `Project`
- `SourceAsset`
- `GeneratedOutput`
- `Approval`
- `AgentEvent`

For early demos, `app.database.initialize_database()` can create tables directly from the models. Production deployments should move to Alembic migrations before real client data is stored.

Project memory writes are gated by `PROJECT_MEMORY_ENABLED`. Leave it `false` for local testing when you do not want API calls to write to Neon. Set it to `true` in a configured demo/prod environment after tables exist.

The RamAir Teams channel pilot is documented in `docs/ramair-client-channel-pilot.md`, with starter channel files under `client_artifacts/ramair/`. Print the channel standard or bind a real Teams channel when IDs are available with:

```powershell
python scripts/ramair_channel_pilot.py
python scripts/ramair_channel_pilot.py --bind
```

## Approvals

Approval setup is documented in `docs/approvals.md`. Use approvals as the required gate before outbound emails, publishing, deployments, client-facing claims, and live-avatar commitments.

Dylan deploy requests now require an approved `deploy_site` approval before deployment runs. Microsoft 365 draft creation can create `send_email` approval requests for review.

## Readiness

Readiness checks are documented in `docs/readiness.md`. Use `GET /readiness` before demos to confirm LLM, database/project memory, M365, HeyGen, Teams, and approvals are configured as expected.

## Azure Container Apps

The preferred hosted API path is Azure Container Apps with Neon Postgres kept as the database through `DATABASE_URL`. This keeps ParlayVU Dockerized and portable while aligning the hosted API with Teams, Microsoft 365, and Azure Bot Service. See `docs/azure-container-apps.md`. Print the Azure command checklist with:

```powershell
python scripts/azure_deploy_checklist.py
```

## Release Checklist

The final pitch-readiness gate is documented in `docs/release-checklist.md`. Print the checklist with:

```powershell
python scripts/release_checklist.py
```

## Microsoft 365

Agent mailbox and Teams/SharePoint Files setup is documented in `docs/microsoft365.md`. ParlayVU creates email drafts by default; direct outbound sends remain disabled unless `MICROSOFT_GRAPH_ALLOW_SEND=true`. Nathan can publish meeting notes to channel Files as both `.md` and `.docx` through `POST /m365/files/meeting-notes`.

## HeyGen LiveAvatar

LiveAvatar setup is documented in `docs/heygen.md`. The current scaffold answers project-bound questions from stored memory and flags pending approvals for human review.

## Microsoft Teams

Teams front-door setup is documented in `docs/teams.md`. The current scaffold accepts a normalized Teams-style message and routes it through Nathan with optional project memory.

## Native Teams Media Bot

The native Teams media bot scaffold lives under `services/teams-media-bot/`. It is a separate .NET service for Microsoft Graph Cloud Communications calling-bot work and is not part of the Azure Container Apps deployment path. The current scaffold registers meetings and forwards questions/approved transcript notes to the existing ParlayVU live meeting endpoints; it does not yet implement a real Graph media join.

## Hardening Priorities

1. Rotate any secrets that have been stored locally or shared outside secret managers.
2. Move production secrets into Azure Container App secrets, Azure Key Vault, or the deployment platform secret store.
3. Replace wide-open production CORS with explicit allowed origins.
4. Add database models and migrations for clients, projects, source assets, outputs, approvals, and agent activity.
5. Add Microsoft Graph helpers for agent mailboxes and Teams events.
6. Add HeyGen LiveAvatar callbacks connected to approved project memory.
7. Containerize the API for Azure Container Apps.
