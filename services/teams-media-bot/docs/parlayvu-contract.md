# ParlayVU Live Meeting Contract

The Teams media bot talks to the existing ParlayVU FastAPI live meeting endpoints. The endpoint names currently live under `/heygen/live-meetings/*` because the first implementation was the operator-controlled HeyGen LiveAvatar flow. For the native Teams bot milestone, keep that backend contract stable and adapt the .NET service to it.

## Configuration

The media bot needs:

```text
PARLAYVU_BASE_URL=http://127.0.0.1:8000
PARLAYVU_API_KEY=
```

`PARLAYVU_API_KEY` is optional in the current local backend, but should be wired to production authentication before exposing the media bot to the internet.

## Start Or Register Meeting

Media bot endpoint:

```text
POST /meetings/join
```

Example body:

```json
{
  "meetingJoinUrl": "https://teams.microsoft.com/l/meetup-join/...",
  "teamsMeetingId": "optional-teams-meeting-id",
  "meetingTitle": "RamAir Teams call with David Hart",
  "agentName": "nathan",
  "clientId": "ramair",
  "projectId": "ramair-straight-from-the-hart",
  "expectedAttendees": ["David Hart", "ParlayVU operator"],
  "operatorNotes": "Native media bot registration dry run."
}
```

The scaffold forwards this to:

```text
POST /heygen/live-meetings/start
```

and returns ParlayVU's session plus an explicit `graphJoin.status = "not_implemented"` marker.

## Live Question

Media bot endpoint:

```text
POST /meetings/{sessionId}/question
```

Example body:

```json
{
  "question": "What is the current RamAir campaign status?",
  "speakerName": "David Hart",
  "providerEventId": "graph-call-event-id",
  "meetingId": "teams-meeting-id"
}
```

The scaffold forwards this to:

```text
POST /heygen/live-meetings/{session_id}/question
```

The response includes Nathan's grounded answer, `provider_response.spoken_text`, `needs_human_review`, and grounding metadata. A future media implementation can pass `provider_response.spoken_text` into the approved outbound TTS/audio path.

Expected media-bot interpretation:

```json
{
  "answer": "Grounded Nathan response text.",
  "provider_response": {
    "spoken_text": "Text safe to send to the selected avatar provider.",
    "voice_instructions": "Optional delivery guidance when supported by the provider.",
    "avatar_provider_hint": "tavus|heygen-liveavatar|did|soul-machines"
  },
  "needs_human_review": false,
  "safety": {
    "approved_for_live_speech": true,
    "requires_operator_intervention": false
  },
  "grounding": {
    "project_id": "ramair-straight-from-the-hart",
    "client_id": "ramair",
    "unsupported_metric_requested": false,
    "grounded_sources": {
      "source_assets": [],
      "generated_outputs": [],
      "pending_approvals": []
    }
  }
}
```

The current FastAPI response already provides the answer, `provider_response.spoken_text`, `needs_human_review`, and grounding fields. `voice_instructions`, `avatar_provider_hint`, and explicit `safety` flags are contract targets for the next backend iteration; until they exist, the media bot must default to conservative operator review when `needs_human_review` is true.

## Meeting Notes

Media bot endpoint:

```text
POST /meetings/{sessionId}/notes
```

Example body:

```json
{
  "title": "RamAir Weekly Meeting Notes",
  "summary": "Client-approved recap, decisions, blockers, and next actions.",
  "transcript": "Optional Teams native transcript or approved upload text.",
  "teamId": "optional-real-team-id",
  "channelId": "optional-real-channel-id"
}
```

The scaffold forwards this to:

```text
POST /heygen/live-meetings/{session_id}/notes
```

ParlayVU publishes the meeting notes to the existing Teams Files workflow as `.md` and template `.docx` when Microsoft 365 configuration is available.

## Lifecycle Callback

The Azure Bot calling webhook should eventually point to:

```text
POST /teams/calling/notifications
```

The current implementation only accepts and logs lifecycle notifications. It does not parse or answer calls yet.

## Avatar Provider Bridge

The media bot-to-avatar contract lives in `avatar-provider-contract.md`. ParlayVU is responsible for grounded content and safety signals; the Teams media bot is responsible for provider selection, session lifecycle, and only injecting media after Teams Graph media handling has been implemented and validated.
