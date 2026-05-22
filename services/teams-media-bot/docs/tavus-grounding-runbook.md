# Tavus Nathan Grounding Runbook

Updated May 18, 2026.

This runbook keeps Tavus Nathan aligned with ParlayVU source-of-truth context. Tavus provides the provider-hosted avatar session; ParlayVU owns company facts, team roles, project memory, approvals, and what Nathan is allowed to say.

## Source Of Truth

- Canonical non-secret grounding file: `services/teams-media-bot/config/parlayvu-avatar-grounding.md`.
- Runtime project/client facts: ParlayVU project memory supplied by the FastAPI backend.
- Provider persona content must not override either source.

Known corrections currently enforced by the grounding file:

- Official site/name is `ParlayVU.ai`, not `parlayvu.com`.
- Blake Quinn is Intelligence and Insights.
- Morgan Patel is Paid Media.
- No canonical ParlayVU role for Maya is present in the current repo context.

## Tavus Persona Cleanup

In Tavus, keep the Nathan persona focused on voice, tone, and avatar behavior. Remove or neutralize stored persona/knowledge-base facts that conflict with ParlayVU source of truth, especially:

- `parlayvu.com` as the company website.
- Blake owning paid media.
- Maya as a senior video producer or any other asserted ParlayVU team role.
- Any fixed team roster, client list, metrics, budgets, or deployment claims that are not sourced from ParlayVU project memory.

Preferred persona wording:

```text
Nathan is ParlayVU's grounded meeting orchestrator. Company, team, client, project, and Teams bridge facts are supplied at conversation creation time by ParlayVU and override persona memory.
```

## Create A Grounded Tavus Conversation

From the repo root:

```powershell
$env:TAVUS_API_KEY = "<tavus api key>"
$env:TAVUS_REPLICA_ID = "<replica id>"
$env:TAVUS_PERSONA_ID = "<persona id>"
$env:TEAMS_MEDIA_BOT_CALLBACK_BASE_URL = "https://<public media-bot host>"
.\services\teams-media-bot\scripts\Invoke-TavusSpike.ps1 -DryRun
```

Inspect the dry-run JSON and confirm `conversational_context` includes `ParlayVU.ai`, the Blake/Morgan corrections, the Maya unknown rule, and the warning that Tavus is not yet a native Teams participant.

Create the Tavus conversation only after the dry run looks correct:

```powershell
.\services\teams-media-bot\scripts\Invoke-TavusSpike.ps1
```

Add meeting-specific source-of-truth context when needed:

```powershell
.\services\teams-media-bot\scripts\Invoke-TavusSpike.ps1 `
  -AdditionalContext "This meeting is a non-production Teams bridge spike. Do not claim native Teams participation until Graph media injection is validated."
```

The response should include the Tavus `conversation_id` and `conversation_url` when credentials are valid.

## Teams Bridge Truth

Be explicit with stakeholders: a successful Tavus conversation proves Nathan can run in Tavus, not that Nathan is a native Microsoft Teams participant. The next engineering step is to implement the Teams media bridge:

- Join a test Teams meeting through Microsoft Graph Cloud Communications as a visible bot participant.
- Start a grounded Tavus conversation through the provider adapter.
- Validate whether the media bot can legally and technically consume Tavus/Daily WebRTC audio/video tracks server-side.
- Transform and inject those tracks into Microsoft Graph application-hosted media sockets.
- Keep `mediaBridgeValidated=false` until provider media is observed inside a test Teams meeting through the Graph media path.
