# Microsoft 365 Setup

ParlayVU uses Microsoft 365 as an operating channel for agent identities. Each agent can be mapped to a mailbox, while outbound sends remain disabled by default.

## Azure App Registration

Create or use an Azure app registration with:

- Tenant ID
- Client ID
- Client secret
- Microsoft Graph application permissions appropriate for mailbox access
- Microsoft Graph application permission `Files.ReadWrite.All` or `Sites.ReadWrite.All` with admin consent for SharePoint/Teams Files publishing
- Microsoft Graph application permission `Notes.ReadWrite.All` with admin consent if the legacy OneNote page creation path remains enabled

For early draft creation, the expected Graph path is:

- `POST /users/{agent_mailbox}/messages`

Later, approved sends can use:

- `POST /users/{agent_mailbox}/sendMail`

For Teams/SharePoint Files meeting notes, the expected Graph paths are:

- `GET /teams/{team_id}/channels/{channel_id}/filesFolder`
- `GET /drives/{drive_id}/items/{folder_item_id}:/{template_path}:/content`
- `PUT /drives/{drive_id}/items/{folder_item_id}:/{path}/{filename}:/content`

For legacy OneNote meeting notes, the expected Graph path is:

- `POST /users/{onenote_owner_mailbox}/onenote/sections/{section_id}/pages`

Do not enable send behavior until approval gates and audit logging are confirmed.

## Environment

Set these values in `.env` or the deployment secret store:

```text
MICROSOFT_TENANT_ID=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_GRAPH_SCOPE=https://graph.microsoft.com/.default
MICROSOFT_GRAPH_ALLOW_SEND=false
ONENOTE_OWNER_MAILBOX=
ONENOTE_NOTEBOOK_ID=
ONENOTE_NOTEBOOK_NAME=RamAir
ONENOTE_SECTION_ID=
ONENOTE_SECTION_NAME=Meeting Notes
M365_FILES_TEAM_ID=
M365_FILES_CHANNEL_ID=
M365_FILES_DRIVE_ID=
M365_FILES_FOLDER_ITEM_ID=
M365_FILES_BASE_PATH=03_Deliverables/Meeting Notes
M365_FILES_MEETING_NOTES_TEMPLATE_PATH=00_Client_Brief/Templates/RamAir Meeting Notes Template.docx

NATHAN_MAILBOX=nathan@parlayvu.ai
AVA_MAILBOX=ava@parlayvu.ai
```

Add the remaining specialist mailboxes as they are created.

For Files publishing, prefer `M365_FILES_TEAM_ID` and `M365_FILES_CHANNEL_ID` so ParlayVU resolves the channel SharePoint folder through Graph. If a channel is not available, configure `M365_FILES_DRIVE_ID` and optionally `M365_FILES_FOLDER_ITEM_ID` to upload directly to a SharePoint document library. `M365_FILES_BASE_PATH` defaults to `03_Deliverables/Meeting Notes`.

For Word meeting notes, Nathan first downloads `M365_FILES_MEETING_NOTES_TEMPLATE_PATH` from the same configured Teams/SharePoint Files destination. The default is `00_Client_Brief/Templates/RamAir Meeting Notes Template.docx`. If the template is missing, unreadable, or does not include recognized placeholders, Nathan still publishes the `.md` copy and uses the built-in generated `.docx` fallback.

Supported Word template placeholders:

- `{{MEETING_TITLE}}`
- `{{MEETING_DATE}}`
- `{{CLIENT}}` - the short client/channel label, such as `RamAir`.
- `{{CLIENT_NAME}}` - the company name from project memory, such as `RamAir International`.
- `{{PROJECT}}`
- `{{ATTENDEES}}`
- `{{SUMMARY}}`
- `{{DECISIONS}}`
- `{{ACTION_ITEMS}}`
- `{{QUESTIONS}}`
- `{{NEXT_STEPS}}`
- `{{SOURCE_MATERIAL}}`

Use `{{CLIENT}}` when the template should show the Teams channel/client short label. Use `{{CLIENT_NAME}}` when it should show the formal company name. `{{CLIENT_NAME}}` is resolved from `project_context.client.name` or the stored `Client.name`; if no stored name is available, it falls back to the same display value as `{{CLIENT}}`.

For the RamAir demo, the seeded client name is `RamAir International` while the Teams channel label remains `RamAir`. Run `python scripts/seed_demo.py` against the target `DATABASE_URL` to create or update the seeded project memory, then confirm with `GET /memory/projects/ramair-straight-from-the-hart`.

`ONENOTE_OWNER_MAILBOX` defaults to `NATHAN_MAILBOX` when omitted. Prefer `ONENOTE_SECTION_ID` for production. If only names are configured, ParlayVU resolves `ONENOTE_NOTEBOOK_NAME=RamAir` and `ONENOTE_SECTION_NAME=Meeting Notes` through Graph before creating the page.

## API Endpoints

- `GET /m365/status` returns which agent mailboxes are configured without exposing secrets.
- `POST /m365/email-drafts` creates a draft in the configured agent mailbox.
- `POST /m365/files/meeting-notes` uploads `.md` and `.docx` meeting notes to Teams/SharePoint Files and logs file metadata back to project memory when enabled.
- `POST /m365/onenote/meeting-notes` creates an HTML OneNote page in the configured section for legacy demos.

Example Files request:

```json
{
  "title": "RamAir Weekly Meeting",
  "summary": "Client-approved recap and next steps from ParlayVU project memory.",
  "client_id": "ramair",
  "project_id": "ramair-straight-from-the-hart",
  "team_id": "teams-team-id",
  "channel_id": "teams-channel-id"
}
```

Outbound send is intentionally not exposed through an API endpoint yet. The underlying client refuses sends unless `MICROSOFT_GRAPH_ALLOW_SEND=true`, and that should remain false until production approval rules are implemented.
