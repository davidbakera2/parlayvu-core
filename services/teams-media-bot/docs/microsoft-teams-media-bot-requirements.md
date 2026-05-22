# Microsoft Teams Media Bot Requirements

This document captures the current implementation constraints for a native Teams media bot that joins calls as Nathan. It is based on Microsoft Graph Cloud Communications and Teams application-hosted media bot guidance:

- [Build application-hosted media bots](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/requirements-considerations-application-hosted-media-bots)
- [Choose a media hosting option](https://learn.microsoft.com/en-us/graph/cloud-communications-media)
- [Graph Communications Bot Media SDK](https://microsoftgraph.github.io/microsoft-graph-comms-samples/docs/bot_media/)
- [Teams calling and meeting bot sample](https://learn.microsoft.com/en-us/samples/officedev/microsoft-teams-samples/officedev-microsoft-teams-samples-bot-calling-meeting-csharp/)
- [Teams meeting transcripts and recordings APIs](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/meeting-transcripts/overview-transcripts)

## Service Shape

- Native media bots use Microsoft Graph Cloud Communications calling APIs and application-hosted media patterns.
- Microsoft's media SDK path is C#/.NET through `Microsoft.Graph.Communications.Calls.Media`.
- The media bot must be stateful because real-time media calls are pinned to the compute instance handling the call.
- The production media bot should run as a separate service from the FastAPI backend. ParlayVU remains the project-memory, reasoning, approvals, and notes-publishing backend.
- Avatar providers must stay behind the adapter contract in `avatar-provider-contract.md`; the Graph media layer should not depend directly on Tavus, HeyGen LiveAvatar, D-ID, or Soul Machines SDK types.

## Permissions

Minimum permissions depend on the exact join and media path, but the Teams calling sample and Cloud Communications docs require admin-consented Microsoft Graph application permissions such as:

- `Calls.JoinGroupCall.All` for the first scheduled-meeting roster/callback join milestone.
- `Calls.JoinGroupCallAsGuest.All` if joining as a guest is required
- `Calls.AccessMedia.All` for the later application-hosted media bridge milestone
- `Calls.Initiate.All` and `Calls.InitiateGroupCall.All` if the service initiates calls
- `OnlineMeetings.ReadWrite.All` only if the service creates or manages online meetings

Transcript retrieval is a separate permission and policy decision:

- `OnlineMeetingTranscript.Read.All` or resource-specific `OnlineMeetingTranscript.Read.Chat` for supported online meeting transcript scenarios
- `CallTranscripts.Read.All` for supported ad hoc call transcript scenarios

Tenant admins may also need to configure application access policies for application-permission transcript access.

## First Join Request Shape

The current scaffold can build and optionally submit a Microsoft Graph Cloud Communications `POST /v1.0/communications/calls` request for a scheduled Teams meeting. This is a roster/callback proof only:

- It uses `#microsoft.graph.serviceHostedMediaConfig`.
- It requests `audio` modality by default.
- It does not inject Tavus audio or video.
- It does not record, persist, or derive artifacts from raw Teams media.
- It is disabled unless `GraphBot:JoinEnabled=true` or `TEAMS_MEDIA_BOT_GRAPH_JOIN_ENABLED=true` and the request sets `attemptGraphJoin=true`.

Graph scheduled-meeting join requires more than the Teams join URL. Provide the meeting values normally obtained from the Teams/Graph online meeting context:

```json
{
  "meetingJoinUrl": "https://teams.microsoft.com/l/meetup-join/...",
  "chatThreadId": "19:meeting_...@thread.v2",
  "chatMessageId": "0",
  "organizerUserId": "<organizer-user-object-id>",
  "organizerDisplayName": "<optional display name>",
  "organizerTenantId": "<tenant-id>",
  "tenantId": "<tenant-id>",
  "callbackUri": "https://<teams-media-bot-host>/teams/calling/notifications",
  "requestedModalities": ["audio"]
}
```

Use `POST /meetings/join/graph-request-preview` or `scripts/Invoke-JoinMeeting.ps1 -PreviewOnly` to verify the generated Graph payload before any live attempt.

## Azure Bot Configuration Checklist

Complete these user/admin actions before setting `attemptGraphJoin=true`:

- Create or identify the Microsoft Entra app registration used by the Azure Bot. Record the Application/client ID and Directory/tenant ID.
- Create a client secret or certificate and store it in Key Vault or host secrets. Configure this service with `TEAMS_MEDIA_BOT_APP_ID`, `TEAMS_MEDIA_BOT_APP_SECRET`, and `TEAMS_MEDIA_BOT_TENANT_ID`.
- Create or update the Azure Bot to use the same Microsoft App ID. Do not mix a different Azure Bot app ID with the Graph token app ID.
- Enable the Microsoft Teams channel on the Azure Bot.
- In the Teams channel Calling tab, enable calling and set Webhook (for calling) exactly to `https://<teams-media-bot-host>/teams/calling/notifications`.
- Ensure the Teams app manifest bot entry has `supportsCalling: true`; set `supportsVideo: true` only when video support is intentionally being tested.
- Add Microsoft Graph application permission `Calls.JoinGroupCall.All` and have a tenant admin grant consent. Re-run admin consent after any permission change.
- Add `Calls.AccessMedia.All` before the Tavus/native media bridge milestone, not because the current roster proof uses it.
- Host the bot behind a public HTTPS URL with a valid certificate. Localhost and private VPN-only URLs are not valid callback targets for Graph calling notifications.
- Verify `GET https://<teams-media-bot-host>/health` reports `graphBotConfigured=true` and the `graphCallingWebhook` value matches the Azure Bot calling webhook.
- Verify a non-production Teams meeting has the required `chatInfo` and organizer `meetingInfo` values before attempting a live join.

## Hosting Constraints

Application-hosted media bots require supported Azure hosting with Windows Server for production. Documented patterns include:

- Azure Cloud Service
- Service Fabric with VM Scale Sets
- Azure IaaS virtual machines
- AKS with Windows node pools

Do not plan this workload for Azure Container Apps or Azure App Service until Microsoft explicitly supports that application-hosted media pattern. The service must have public callback/media reachability, and each media-handling instance must be addressable in the way the Graph media platform expects.

## Recording And Transcription Limits

Do not treat media access as permission to record meetings. Microsoft's media access guidance restricts recording or persisting call media, or data derived from that media, unless the application follows the required recording status flow and has the appropriate compliance-recording basis.

For ParlayVU meeting notes, the compliant path is:

- Teams native transcription or recording, visibly controlled by Teams meeting policy and organizer/user consent.
- Graph transcript retrieval after the meeting where tenant policy, licensing, metered API requirements, and application permissions allow it.
- Operator/client-approved transcript upload into ParlayVU when Graph retrieval is not available.

The first milestone should not implement autonomous raw media recording or raw transcript generation from captured audio. Avatar video streaming remains a separate milestone after provider media access and Graph media injection are proven in a non-production Teams meeting.

## Native Participant Milestones

1. Scaffold readiness: service runs, reports configuration, accepts Graph lifecycle callbacks, and registers ParlayVU live meetings.
2. Roster participant: bot submits a Graph create-call request, receives lifecycle callbacks, and is observed in a test Teams meeting as a visible Nathan/ParlayVU participant with no media injection claims beyond what is observed.
3. Tavus provider bridge: start a grounded Tavus Nathan conversation from the media bot and validate server-side access to Tavus/Daily WebRTC tracks.
4. Audio-only bridge: approved Nathan response text becomes provider audio and is injected into Teams.
5. Audio/video bridge: provider video frames are injected alongside audio after latency, format conversion, and compliance review.
6. Notes flow: Teams native transcript or approved upload publishes through the existing Teams Files `.md` and template `.docx` path.

Tavus is the first avatar provider for the Teams bridge spike. Keep `mediaBridgeValidated=false` until Tavus media is observed inside a test Teams meeting through the Microsoft Graph application-hosted media path.
