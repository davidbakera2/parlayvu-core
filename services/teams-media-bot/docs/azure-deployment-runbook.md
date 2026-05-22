# Azure Deployment Runbook

This service is not part of the existing Azure Container Apps path. Application-hosted Teams media bots need supported Azure hosting for stateful, real-time media handling and public Graph callback/media reachability.

## Recommended First Hosting Target

For the first native media milestone, use a Windows Server Azure VM or Windows VM Scale Set. This keeps the deployment close to Microsoft's application-hosted media bot requirements while the Graph Communications integration is still being proven.

Do not deploy to Azure Container Apps for media handling. Container Apps can continue hosting the FastAPI ParlayVU backend, but the Teams media bot should be its own Azure workload.

## Prerequisites

- Azure subscription with permission to create compute, networking, managed identity or Key Vault access, and Bot resources.
- Microsoft 365 tenant admin able to consent Graph application permissions and configure Teams policies.
- Azure Bot registration with Teams channel enabled and calling support configured.
- Public HTTPS DNS name for the media bot callback base URL.
- ParlayVU backend URL reachable from the media bot.

## Azure Bot And Graph Setup

1. Create or identify the Azure AD application used by the bot.
2. Configure client secret or certificate credential in Azure Key Vault.
3. Enable the Teams channel for the Azure Bot.
4. Configure the calling webhook to:

   ```text
   https://<teams-media-bot-host>/teams/calling/notifications
   ```

5. Add and admin-consent Graph permissions required for the selected milestone:

   ```text
   Calls.JoinGroupCall.All                 # required for first scheduled-meeting join proof
   Calls.AccessMedia.All                   # required before application-hosted media/Tavus bridge
   Calls.JoinGroupCallAsGuest.All        # only if guest join is required
   Calls.Initiate.All                    # only if the bot initiates calls
   Calls.InitiateGroupCall.All           # only if the bot starts group calls
   OnlineMeetings.ReadWrite.All          # only if the bot creates/manages meetings
   ```

   Re-run tenant admin consent every time Graph application permissions change.

6. Confirm Teams calling settings:

   ```text
   Azure Bot Teams channel: enabled
   Calling tab: Enable calling
   Webhook (for calling): https://<teams-media-bot-host>/teams/calling/notifications
   Teams app manifest bots[0].supportsCalling: true
   Teams app manifest bots[0].supportsVideo: false for roster proof; true only for explicit video testing
   ```

7. Add transcript permissions only after the transcript retrieval path is approved:

   ```text
   OnlineMeetingTranscript.Read.All
   OnlineMeetingTranscript.Read.Chat
   CallTranscripts.Read.All
   ```

## VM Deployment Outline

1. Create a Windows Server VM in Azure.
2. Assign a public DNS name and lock inbound traffic to required HTTPS/callback ports.
3. Install the .NET runtime compatible with the service target framework.
4. Install and configure IIS, Windows Service hosting, or another approved process supervisor.
5. Store secrets in Key Vault or VM environment variables:

   ```text
   PARLAYVU_BASE_URL=https://<parlayvu-api-host>
   PARLAYVU_API_KEY=<if-required>
   TEAMS_MEDIA_BOT_TENANT_ID=<tenant-id>
   TEAMS_MEDIA_BOT_APP_ID=<app-id>
   TEAMS_MEDIA_BOT_APP_SECRET=<secret-or-key-vault-reference>
   TEAMS_MEDIA_BOT_CALLBACK_BASE_URL=https://<teams-media-bot-host>
   TEAMS_MEDIA_BOT_CALLING_WEBHOOK_PATH=/teams/calling/notifications
   TEAMS_MEDIA_BOT_GRAPH_JOIN_ENABLED=false
   ```

6. Publish and copy the service:

   ```powershell
   dotnet publish services/teams-media-bot/src/ParlayVu.TeamsMediaBot/ParlayVu.TeamsMediaBot.csproj -c Release -o .publish/teams-media-bot
   ```

7. Start the service and verify:

   ```powershell
   Invoke-RestMethod https://<teams-media-bot-host>/health
   ```

8. Confirm Azure Bot calling notifications reach `/teams/calling/notifications`.
9. Preview a scheduled-meeting Graph request body:

   ```powershell
   .\services\teams-media-bot\scripts\Invoke-JoinMeeting.ps1 `
     -BotBaseUrl "https://<teams-media-bot-host>" `
     -JoinMeetingUrl "https://teams.microsoft.com/l/meetup-join/..." `
     -ChatThreadId "19:meeting_...@thread.v2" `
     -ChatMessageId "0" `
     -OrganizerUserId "<organizer-user-object-id>" `
     -OrganizerTenantId "<tenant-id>" `
     -TenantId "<tenant-id>" `
     -PreviewOnly
   ```

10. Only after the preview is correct, set `TEAMS_MEDIA_BOT_GRAPH_JOIN_ENABLED=true` and run the same script with `-AttemptGraphJoin` against a non-production Teams meeting. Treat Graph `201 Created` as "join requested"; claim live join only after the bot is visible in the roster and lifecycle callbacks arrive.

## Provider Decision Criteria

Choose an avatar provider only after a spike proves the provider can satisfy the adapter contract in `avatar-provider-contract.md`.

Required evidence:

- A server-side or service-controlled session start path exists.
- Nathan audio and video tracks can be accessed in real time without relying on an attended browser in the meeting.
- Provider terms allow the media-bot service to consume those tracks for live Teams injection.
- The stream can be transformed to Microsoft Graph application-hosted media formats with acceptable latency.
- The provider supports interruption or stop semantics for participant interjections and meeting end.
- The provider can be configured without embedding long-lived secrets in client-side code.

Current ordering:

1. Tavus first, because the Conversational Video Interface exposes a clear real-time conversation creation API and WebRTC room.
2. HeyGen LiveAvatar second, because ParlayVU already has HeyGen/Nathan configuration and LiveAvatar exposes a LiveKit session model.
3. D-ID third, unless a backend-supported LiveKit or Microsoft-native Teams path is confirmed.
4. Soul Machines later, only if enterprise integration support materially lowers Teams media risk.

## Compliance Boundaries

The native participant milestone must remain visibly and operationally compliant:

- Nathan must be identified as an AI-generated ParlayVU participant in meeting setup and/or opening remarks.
- Do not record, persist, or derive stored artifacts from raw Teams media unless the app implements Microsoft's required recording/compliance flow and tenant approval.
- Prefer Teams native transcription or recording indicators for transcript creation.
- Route notes through approved transcript retrieval or operator/client-approved upload before posting to ParlayVU.
- Keep provider recording features disabled during media-bridge spikes unless a separate recording approval exists.
- Log provider session IDs, Teams call IDs, timestamps, and status transitions; do not log raw transcript text or captured frames by default.

## Operational Checks

- Keep `Microsoft.Graph.Communications.Calls.Media` current once introduced; Microsoft deprecates stale media SDK versions.
- Treat each media call as pinned to an instance. Draining or restarting that instance can terminate calls.
- Log join attempts, Graph lifecycle notifications, ParlayVU session ids, questions, answers, transcript source, and notes-publishing results.
- Do not log raw transcript text by default. Log metadata and storage pointers instead.
- Document every tenant policy dependency before client demos.

## Rollback

Because this service is separate from the FastAPI API, rollback should be isolated:

1. Stop the media bot process or remove the Azure Bot calling webhook.
2. Leave the ParlayVU backend and Teams Files notes workflow online.
3. Fall back to the existing operator-controlled HeyGen/Teams meeting process.
