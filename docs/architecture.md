# ParlayVU Architecture

## Product Model

ParlayVU is designed as an agentic consulting and execution team. Microsoft Teams is the front door. Nathan receives requests, gathers project context, routes work to specialist agents, and returns drafts, status, approvals, and completed assets through the channels where the client already works.

## Runtime Architecture

```text
Microsoft Teams / M365 Mail / HeyGen LiveAvatar / Web
        |
        v
FastAPI + LangGraph API
        |
        +-- Nathan orchestrator
        +-- Specialist agent registry
        +-- Project memory and approval rules
        |
        +-- LLM providers: xAI Grok now, OpenAI/Groq optional
        +-- Neon Postgres for clients, projects, outputs, and audit history
        +-- Microsoft Graph for agent mailboxes and Teams integration
        +-- HeyGen for live avatar presence in calls
        +-- Cloudflare Pages for generated Astro sites
```

## Agent Team

- Nathan Ellis: lead orchestrator and Teams front door.
- Alex Rivera: visuals and design.
- Ava Hosseini: content writing.
- Blake Quinn: intelligence and insights.
- Casey Johnson: engagement, community, and operations.
- Codey Miner: coding and integrations.
- Dylan Brooks: web generation, deployment, SEO, and release verification.
- Jordan McKenney: social execution and publishing.
- Michael Chen: sales and conversion.
- Morgan Patel: paid media.
- Nora Russo: partnerships and affiliates.
- Riley Thompson: publishing and distribution.
- Taylor Kim: customer success and retention.

## Target Production Shape

- Host the FastAPI/LangGraph backend on AWS Fargate.
- Store production secrets in AWS Secrets Manager.
- Keep Neon Postgres as the managed relational database unless there is a later AWS-native RDS requirement.
- Keep generated marketing sites on Cloudflare Pages.
- Use Microsoft Graph for agent mailbox operations, Teams events, and approval cards.
- Use HeyGen LiveAvatar for bounded real-time agent presence in Teams calls.

## Control Principles

- Nathan is the primary user interface and routing authority.
- Specialist agents act within explicit project context and approval rules.
- Client-facing email, publishing, deployment, and disclosure actions require approval until configured otherwise.
- Every generated output should be tied to a `client_id`, `project_id`, source material, agent, timestamp, and approval state.
- Live avatar answers should come from approved project memory and say when something is unknown or requires human review.

## Project Memory Schema

The first persistence scaffold lives in SQLAlchemy models:

- `clients`: brand voice, disclosure rules, and channel preferences.
- `projects`: client workspaces with objectives, status, approval policy, and metadata.
- `source_assets`: transcripts, videos, links, summaries, and other source material.
- `generated_outputs`: drafts, pages, posts, emails, scripts, and deployment artifacts.
- `approvals`: requested, approved, rejected, or revised decisions tied to outputs.
- `agent_events`: routed tasks, Teams activity, email actions, LiveAvatar events, and audit history.

This schema is intentionally small enough for the investor demo while leaving room for migrations, retrieval, and channel-specific integrations.
