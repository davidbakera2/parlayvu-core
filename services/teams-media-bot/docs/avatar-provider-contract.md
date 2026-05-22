# Avatar Provider Adapter Contract

This contract keeps the native Teams media-bot layer separate from Tavus, HeyGen LiveAvatar, D-ID, or any later avatar provider. It is intentionally provider-neutral and does not claim that media has been injected into Teams yet.

## Boundary

ParlayVU owns:

- Meeting registration and project-memory context.
- Nathan's grounded response text.
- Human-review and safety signals.
- Approved post-call notes through the existing Teams Files `.md` plus template `.docx` workflow.

The Teams media bot owns:

- Microsoft Graph Cloud Communications call lifecycle.
- Provider session selection and lifecycle.
- Bridging provider audio/video into Teams media only after Graph media handling is implemented and tested.
- Logging metadata without storing raw Teams media.

The avatar provider owns:

- Real-time avatar rendering and audio generation.
- Provider-specific WebRTC, LiveKit, SDK, or WebSocket session handling.
- Interrupt/stop behavior when supported.

## Session Start

Adapter input:

```json
{
  "agentName": "nathan",
  "meetingSessionId": "live-123",
  "providerHint": "tavus",
  "conversationalContext": "Grounded RamAir context approved for this meeting.",
  "requireVideo": true,
  "requireAudio": true
}
```

Adapter output:

```json
{
  "providerName": "tavus",
  "providerSessionId": "c123456",
  "joinUrl": "https://provider.example/room",
  "webRtcRoomUrl": "https://provider.example/room",
  "clientToken": "optional-client-token",
  "agentToken": "optional-agent-token",
  "mediaBridgeValidated": false,
  "mediaAccess": {
    "transport": "daily-webrtc|livekit|browser-webrtc|sdk-callback|unknown",
    "audioAvailable": true,
    "videoAvailable": true,
    "notes": "Provider exposes a room/stream, but Teams media injection is not validated yet."
  }
}
```

`mediaBridgeValidated` must remain `false` until a bot has joined a test Teams meeting and injected provider media into Graph media sockets successfully.

## Speak Or Interrupt

Adapter input:

```json
{
  "providerSessionId": "provider-session-id",
  "text": "Grounded Nathan answer.",
  "voiceInstructions": "Calm, concise, executive tone.",
  "interruptCurrentSpeech": true
}
```

Adapter output:

```json
{
  "providerName": "provider-name",
  "providerSessionId": "provider-session-id",
  "status": "accepted|speaking|unsupported|failed",
  "providerEventId": "optional-provider-event-id"
}
```

If `needs_human_review` is true in the ParlayVU response, the bot must not auto-speak the response unless an operator explicitly approves it.

## Stop Session

The adapter must support a best-effort stop method with:

- `providerSessionId`
- `reason`
- cancellation token or timeout

Stop must clean up provider resources even when the Teams call ends unexpectedly.

## Error And Fallback Rules

- Provider setup errors should return a typed `failed` state with a provider message suitable for logs, not for meeting participants.
- If audio is available but video is not, the bot may continue only after the current milestone explicitly permits audio-only Teams participation.
- If no provider exposes retrievable media in a server-bridgeable form, keep the existing operator-controlled avatar workflow and document the blocker.
- Never fall back to recording or storing Teams raw media as a substitute for a provider stream.

## Provider Configuration

The scaffold reads these environment variables when present:

```text
TAVUS_API_KEY=
TAVUS_BASE_URL=https://tavusapi.com
TAVUS_REPLICA_ID=
TAVUS_PERSONA_ID=
LIVEAVATAR_API_KEY=
LIVEAVATAR_BASE_URL=https://api.liveavatar.com
HEYGEN_API_KEY=                    # accepted as a LiveAvatar key fallback
DID_API_KEY=
DID_AGENT_ID=
DID_CLIENT_KEY=
SOUL_MACHINES_API_KEY=
```

Use `GET /avatar/providers/status` to check whether required inputs are present. This endpoint does not perform live provider calls.
