# Hardening Roadmap

## 1. Foundation

- Protect secrets with `.gitignore` and secret-manager-backed deployment configuration.
- Rotate any credentials that were stored in local files or exposed in chat/output.
- Document local setup, runtime architecture, and demo flow.
- Add container runtime files for repeatable local and Azure deployment.

## 2. Core API

- Move model/provider selection fully into environment-driven settings.
- Add startup validation for required settings by environment.
- Restrict CORS in production.
- Add structured logging and request IDs.
- Add tests for Nathan routing and Dylan site generation/deployment.

## 3. Project Memory

- Add migrations and tables for clients, projects, source assets, outputs, approvals, meetings, and agent events.
- Store brand voice, disclosure rules, approval rules, and channel preferences per client/project.
- Add retrieval helpers so agents and LiveAvatars answer from bounded project memory.

## 4. Microsoft 365 And Teams

- Register an Azure app for Microsoft Graph.
- Map each agent to a Microsoft 365 mailbox identity.
- Add Graph helpers for outbound email drafts, approved sends, inbound monitoring, and audit logs.
- Add Teams bot/app endpoints so Nathan can receive requests and return status, drafts, and approval cards.

## 5. HeyGen LiveAvatar

- Store avatar IDs and voice/persona configuration per agent.
- Add a realtime response path from HeyGen callbacks to ParlayVU project memory.
- Enforce answer boundaries: approved facts, unknowns, human review, and no unauthorized disclosure.
- Capture meeting summaries and action items back into project memory.

## 6. Deployment

- Package the API for Azure Container Apps.
- Use Azure Container App secrets or Azure Key Vault for production secrets.
- Add health checks, logs, and rollback notes.
- Keep Astro site output on Cloudflare Pages and wire domain verification for `parlayvu.ai`.

## 7. Demo Flow

- Ensure the RamAir client/project exists in project memory.
- Show Teams intake through Nathan.
- Generate a landing page with Dylan.
- Produce campaign copy with Ava and distribution steps with Riley/Jordan.
- Demonstrate an agent answering bounded project questions through HeyGen LiveAvatar.
