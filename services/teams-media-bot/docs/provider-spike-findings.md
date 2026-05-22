# Avatar Provider Spike Findings

Updated May 18, 2026. This is a documentation and harness spike only; no provider has been validated as a native Microsoft Teams media source yet.

## Decision Question

Can the provider programmatically generate or expose real-time Nathan audio/video in a form a Microsoft Graph application-hosted Teams media bot can inject into a Teams meeting?

## Tavus

Current docs show Tavus Conversational Video Interface creates real-time conversations with `POST /v2/conversations` on `https://tavusapi.com`. The request can include `replica_id`, `persona_id`, `callback_url`, `conversation_name`, `conversational_context`, `custom_greeting`, `audio_only`, and room properties. The response includes `conversation_id`, `conversation_url`, `status`, and, for private rooms, a `meeting_token`.

Media shape:

- Real-time WebRTC conversation room, documented as Daily-powered.
- Supports real-time interaction/control through room-level protocols and callbacks.
- Strong fit for starting a provider session from the media bot.
- Open question: whether the bot service can legally and technically consume the Daily/WebRTC tracks server-side and bridge them into Microsoft Graph media sockets without a browser participant shim.

Harness:

- `scripts/Invoke-TavusSpike.ps1 -DryRun` prints the create-conversation payload.
- The harness injects `config/parlayvu-avatar-grounding.md` into `conversational_context` so ParlayVU source-of-truth context overrides provider persona memory.
- Without `-DryRun`, it calls Tavus only when `TAVUS_API_KEY`, `TAVUS_REPLICA_ID`, and `TAVUS_PERSONA_ID` are set.
- The harness deliberately sets `enable_recording` to `false`.
- Grounding and persona-cleanup steps are documented in `docs/tavus-grounding-runbook.md`.

Preliminary adapter mapping:

```json
{
  "providerName": "tavus",
  "transport": "daily-webrtc",
  "sessionStart": "POST /v2/conversations",
  "speakMode": "provider persona/conversation pipeline, not yet direct text push from media bot",
  "audioAvailable": true,
  "videoAvailable": true,
  "mediaBridgeValidated": false
}
```

## HeyGen LiveAvatar

Current LiveAvatar docs show `POST /v1/sessions/start` returning `session_id`, `livekit_url`, `livekit_client_token`, `livekit_agent_token`, `max_session_duration`, and `ws_url` for custom-mode events.

Media shape:

- LiveKit room/token model is promising because LiveKit has server and client SDKs for media tracks.
- ParlayVU already has HeyGen configuration and live-meeting endpoints, but those endpoints are currently operator-controlled and provider-named under `/heygen/live-meetings/*`.
- Open question: exact LiveAvatar API for instructing Nathan to speak in custom mode and whether the provider terms permit server-side track extraction for Teams injection.

Preliminary adapter mapping:

```json
{
  "providerName": "heygen-liveavatar",
  "transport": "livekit",
  "sessionStart": "POST /v1/sessions/start",
  "speakMode": "LiveAvatar SDK/WebSocket custom events, to be validated",
  "audioAvailable": true,
  "videoAvailable": true,
  "mediaBridgeValidated": false
}
```

## D-ID

Current Agents SDK docs show a front-end SDK, `@d-id/client-sdk`, for embedding streaming avatars. The SDK supports Talks and Clips over WebRTC and Expressives over LiveKit. It exposes methods such as `connect()`, `speak({ type, input })`, `chat(string)`, `interrupt()`, and microphone publishing for supported Expressive avatars. The docs explicitly describe the SDK as front-end development only; agent and knowledge-base creation happen through D-ID APIs or Studio.

Media shape:

- Browser SDK gives access to a `srcObject` media stream through callbacks.
- Expressive avatars use LiveKit, which may eventually map to server-side media handling.
- Open question: whether D-ID exposes a backend-supported media-track path suitable for a headless Teams media bot. The searched docs did not show a Microsoft Teams-native participant integration.

Preliminary adapter mapping:

```json
{
  "providerName": "did",
  "transport": "browser-webrtc|livekit",
  "sessionStart": "client SDK connect() or provider API",
  "speakMode": "agentManager.speak() or chat() in front-end SDK",
  "audioAvailable": true,
  "videoAvailable": true,
  "mediaBridgeValidated": false
}
```

## Soul Machines

Soul Machines remains a later enterprise evaluation. No code path is scaffolded beyond configuration status because the immediate decision gate should first resolve Tavus, HeyGen LiveAvatar, and D-ID media accessibility.

Preliminary adapter mapping:

```json
{
  "providerName": "soul-machines",
  "transport": "unknown",
  "sessionStart": "enterprise integration discovery required",
  "speakMode": "unknown",
  "audioAvailable": false,
  "videoAvailable": false,
  "mediaBridgeValidated": false
}
```

## Current Recommendation

Proceed with Tavus as the first avatar provider for the Teams bridge because it has the clearest create-conversation API, a tested provider-hosted Nathan conversation path, and a real-time WebRTC room model. The immediate Tavus work is grounding, provider session lifecycle, and WebRTC/Daily media-access validation. In parallel, keep HeyGen LiveAvatar as a secondary validation path because existing ParlayVU HeyGen assets may shorten the path if its server-side media access is clean.

Do not choose a provider for production until one provider proves both:

- Nathan audio/video tracks can be consumed by the media bot process without violating provider terms.
- Those tracks can be transformed into Microsoft Graph application-hosted media formats and injected into a test Teams meeting.
