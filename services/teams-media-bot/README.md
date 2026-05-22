# ParlayVU Teams Media Bot

This service is a conservative scaffold for a native Microsoft Teams media bot. It is separate from the FastAPI ParlayVU backend because application-hosted Teams media bots use Microsoft Graph Cloud Communications calling patterns and have specialized hosting, permission, and media-compliance requirements.

The scaffold is intentionally not a verified live Teams media join implementation yet. It can run locally, receive Graph lifecycle callbacks, build or submit an opt-in Graph scheduled-meeting join request, and call the existing ParlayVU live meeting endpoints for meeting registration, grounded answers, and approved meeting notes.

## Current Scope

- `GET /health` reports service, ParlayVU, and Graph bot configuration readiness.
- `GET /avatar/providers/status` reports whether Tavus, HeyGen LiveAvatar, D-ID, and Soul Machines adapter inputs are configured. It does not validate real-time media bridging.
- `POST /teams/calling/notifications` accepts Graph communications lifecycle notification payloads and logs them.
- `POST /meetings/join` validates a Teams meeting reference, optionally registers the live meeting with ParlayVU through `POST /heygen/live-meetings/start`, and can optionally attempt a Microsoft Graph Cloud Communications scheduled-meeting join when hosted configuration is complete.
- `POST /meetings/join/graph-request-preview` builds the Graph `POST /communications/calls` request body for a scheduled meeting without calling Graph.
- `POST /meetings/{sessionId}/question` forwards operator-triggered or later speech-recognized questions to `POST /heygen/live-meetings/{session_id}/question`.
- `POST /meetings/{sessionId}/notes` forwards a Teams native transcript, summary, or operator-approved transcript to `POST /heygen/live-meetings/{session_id}/notes`.

## Local Run

```powershell
cd services/teams-media-bot/src/ParlayVu.TeamsMediaBot
$env:PARLAYVU_BASE_URL = "http://127.0.0.1:8000"
dotnet run
```

Optional environment variables:

```text
PARLAYVU_API_KEY=
TEAMS_MEDIA_BOT_TENANT_ID=
TEAMS_MEDIA_BOT_APP_ID=
TEAMS_MEDIA_BOT_APP_SECRET=
TEAMS_MEDIA_BOT_CALLBACK_BASE_URL=
TEAMS_MEDIA_BOT_CALLING_WEBHOOK_PATH=/teams/calling/notifications
TEAMS_MEDIA_BOT_GRAPH_JOIN_ENABLED=false
TAVUS_API_KEY=
TAVUS_REPLICA_ID=
TAVUS_PERSONA_ID=
LIVEAVATAR_API_KEY=
DID_AGENT_ID=
DID_CLIENT_KEY=
```

`config/appsettings.sample.json` has the equivalent configuration shape for hosted environments.

Use the helper scripts for a first hosted join attempt:

```powershell
# Start the bot with Graph join still disabled by default.
.\services\teams-media-bot\scripts\Start-Local.ps1 `
  -ParlayVuBaseUrl "https://<parlayvu-api-host>" `
  -TenantId "<tenant-id>" `
  -AppId "<bot-app-id>" `
  -AppSecret "<bot-app-secret>" `
  -CallbackBaseUrl "https://<public-teams-media-bot-host>"

# Preview the Graph create-call payload. A Teams join URL alone is not enough.
.\services\teams-media-bot\scripts\Invoke-JoinMeeting.ps1 `
  -BotBaseUrl "https://<public-teams-media-bot-host>" `
  -JoinMeetingUrl "https://teams.microsoft.com/l/meetup-join/..." `
  -ChatThreadId "19:meeting_...@thread.v2" `
  -ChatMessageId "0" `
  -OrganizerUserId "<organizer-user-object-id>" `
  -OrganizerTenantId "<tenant-id>" `
  -TenantId "<tenant-id>" `
  -PreviewOnly
```

Only add `-EnableGraphJoin` to `Start-Local.ps1` and `-AttemptGraphJoin` to `Invoke-JoinMeeting.ps1` after Azure Bot calling, Graph admin consent, and public HTTPS callback hosting are configured.

## Microsoft Graph Status

The first Graph join request path is scaffolded and opt-in. It uses Microsoft Graph Cloud Communications `POST /v1.0/communications/calls` with `serviceHostedMediaConfig` for a roster/callback proof, not the later Tavus media bridge. Before enabling it, complete the Azure Bot registration, Graph application permissions, Teams calling channel setup, and supported Azure Windows hosting described in `docs/azure-deployment-runbook.md`.

Do not use this service to record or persist raw Teams media. Meeting notes must come from Teams native transcription/recording retrieval where tenant policy and Graph permissions allow it, or from an operator/client-approved transcript upload into ParlayVU.

## Avatar Provider Status

The provider-neutral contracts are documented in `docs/avatar-provider-contract.md`. The current service only exposes configuration readiness and contract types; it does not yet connect Tavus, HeyGen LiveAvatar, D-ID, or Soul Machines media to Microsoft Graph media sockets.

Tavus is the first avatar provider for the Teams bridge spike. Use `scripts/Invoke-TavusSpike.ps1 -DryRun` to inspect the grounded Tavus conversation request shape. The script injects `config/parlayvu-avatar-grounding.md` into Tavus `conversational_context`; keep provider persona facts subordinate to ParlayVU project memory and that grounding file. Remove `-DryRun` only after real Tavus credentials and a disposable replica/persona are available. Grounding and persona cleanup steps are in `docs/tavus-grounding-runbook.md`.
