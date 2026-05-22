# Production Readiness Checks

ParlayVU exposes a consolidated readiness report for investor demos and production setup.

## Endpoints

- `GET /health` returns basic service health plus `readiness_status`.
- `GET /readiness` returns subsystem configuration checks.

## Readiness Sections

- `llm`: active provider and model, with only a configured/not-configured flag.
- `database`: whether `DATABASE_URL` is configured and whether `PROJECT_MEMORY_ENABLED` is on.
- `m365`: Microsoft Graph and agent mailbox readiness.
- `heygen`: HeyGen API and avatar readiness.
- `teams`: Teams app/bot readiness.
- `approvals`: approval workflow availability and gated actions.

The readiness report does not call external services and does not expose secrets. It is a configuration and wiring check, not a live connectivity probe.

## Demo Interpretation

- `ready`: LLM, database, and approvals are configured.
- `needs_configuration`: at least one required demo foundation setting is missing.

M365, HeyGen, and Teams can be reviewed inside their own readiness sections because those integrations may be staged independently during setup.
