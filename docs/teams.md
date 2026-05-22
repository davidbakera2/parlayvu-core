# Microsoft Teams Front Door

Teams is the intended front door for ParlayVU. Nathan receives messages from Teams, loads project context when a `project_id` is provided, routes the request through LangGraph, and returns the response payload that a Teams bot/app can render back to the conversation.

## Environment

Set these values in `.env` or the deployment secret store:

```text
TEAMS_APP_ID=
TEAMS_APP_PASSWORD=
TEAMS_TENANT_ID=
TEAMS_WEBHOOK_SECRET=
```

`TEAMS_TENANT_ID` can fall back to `MICROSOFT_TENANT_ID` if both Teams and Graph use the same tenant.

## API Endpoints

- `GET /teams/status` returns configuration readiness without exposing secrets.
- `POST /teams/messages` routes an inbound Teams-style message to Nathan.
- `GET /teams/approval-cards` returns pending approvals as Teams-ready card payloads.
- `POST /teams/approvals/{approval_id}/decision` records an approval decision from Teams.

Example request:

```json
{
  "text": "Nathan, summarize the current RamAir campaign.",
  "from_user": "dave@parlayvu.ai",
  "conversation_id": "teams-conversation-id",
  "team_id": "teams-team-id",
  "channel_id": "teams-channel-id",
  "client_id": "ramair",
  "project_id": "ramair-straight-from-the-hart"
}
```

Example response shape:

```json
{
  "status": "routed",
  "channel": "teams",
  "conversation_id": "teams-conversation-id",
  "nathan": {
    "agent": "Nathan",
    "route_decision": {},
    "final_output": {},
    "client_id": "ramair",
    "project_id": "ramair-straight-from-the-hart",
    "project_context": {}
  }
}
```

## Next Production Step

This endpoint is the backend routing scaffold. The next step is to create the actual Teams app/bot registration and adapt Bot Framework activity payloads into this simpler internal message shape.

## Approval Cards

Pending approvals can be listed for Teams rendering:

```text
GET /teams/approval-cards?project_id=ramair-straight-from-the-hart
```

Each card includes an `approval_id`, title, summary, facts, generated output details, and actions:

- `approved`
- `changes_requested`
- `rejected`

Decision payload:

```json
{
  "status": "approved",
  "approver": "dave@parlayvu.ai",
  "decision_notes": "Approved for demo.",
  "conversation_id": "teams-conversation-id",
  "team_id": "teams-team-id",
  "channel_id": "teams-channel-id"
}
```

## RamAir Channel Pilot

RamAir is the first standard client channel pilot. The channel should be named `RamAir`, bound to `project_id=ramair-straight-from-the-hart`, and set up with Posts, Files, Planner/Tasks, notes, performance dashboard, and ParlayVU/Nathan tabs. The full operating guide and starter artifact map are in `docs/ramair-client-channel-pilot.md`.

Bind from inside Teams after opening the real channel:

```text
@ParlayVU bind this channel to RamAir
```

If real Teams identifiers are available locally, the binding can also be created in project memory with:

```powershell
$env:RAMAIR_TEAMS_TEAM_ID = "<real Teams team id>"
$env:RAMAIR_TEAMS_CHANNEL_ID = "<real Teams channel id>"
python scripts/ramair_channel_pilot.py --bind
```

## Meeting Notes In Files

Nathan can publish a provided meeting summary into the RamAir channel SharePoint folder as both `.md` and `.docx`. ParlayVU project memory remains the source of truth; Teams/SharePoint Files are the client-facing artifacts, and file metadata is logged back to project memory when enabled.

For `.docx`, Nathan uses the RamAir Word template at `00_Client_Brief/Templates/RamAir Meeting Notes Template.docx` by default and replaces placeholders such as `{{MEETING_TITLE}}`, `{{CLIENT}}`, `{{CLIENT_NAME}}`, `{{SUMMARY}}`, `{{DECISIONS}}`, and `{{NEXT_STEPS}}`. Use `{{CLIENT}}` for the short Teams channel/client label such as `RamAir`, and `{{CLIENT_NAME}}` for the stored company name such as `RamAir International`. If the template cannot be downloaded or rendered, Nathan still publishes the `.md` copy and falls back to the built-in generated `.docx`.

The company name comes from project memory (`project_context.client.name` / `Client.name`). For the RamAir demo, run `python scripts/seed_demo.py` against the same `DATABASE_URL` used by the API to create or update `RamAir International`, then confirm with `GET /memory/projects/ramair-straight-from-the-hart`.

Example Teams prompt:

```text
@ParlayVU Nathan, publish meeting note to Files
Title: RamAir Weekly Meeting
Summary: Client-approved recap and next steps from ParlayVU project memory.
```

Required Graph setup is documented in `docs/microsoft365.md`.

## Power BI Dashboard Tab

The starter dashboard data layer lives in `client_artifacts/ramair/05_Performance/data/` and is designed for the Power BI SharePoint folder connector. Upload the CSV files to the RamAir channel Files tab, build the report from that SharePoint folder, publish it to the workspace associated with the Team, then add a `Power BI` tab in the RamAir channel.
