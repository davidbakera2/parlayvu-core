# HeyGen LiveAvatar Setup

ParlayVU uses HeyGen LiveAvatar for agent presence in Teams calls. The first backend scaffold keeps responses bounded to project memory and avoids unsupported claims.

## Environment

Set the HeyGen values in `.env` or the deployment secret store:

```text
HEYGEN_API_KEY=
HEYGEN_BASE_URL=https://api.heygen.com
HEYGEN_WEBHOOK_SECRET=
HEYGEN_NATHAN_AVATAR_ID=
```

Add specialist avatar IDs as they are created, for example:

```text
HEYGEN_AVA_AVATAR_ID=
HEYGEN_DYLAN_AVATAR_ID=
HEYGEN_RILEY_AVATAR_ID=
```

## API Endpoints

- `GET /heygen/status` returns HeyGen and avatar configuration readiness without exposing secrets.
- `POST /heygen/live-question` answers a live project-specific question from stored project memory.
- `POST /heygen/live-meetings/start` creates a lightweight Nathan LiveAvatar meeting session record for RamAir.
- `POST /heygen/live-meetings/{session_id}/question` answers a provider callback or operator-entered question for that meeting.
- `POST /heygen/live-meetings/{session_id}/notes` publishes the post-call recap to Teams Files as `.md` and template-based `.docx`.

Example request:

```json
{
  "agent_name": "nathan",
  "project_id": "ramair-straight-from-the-hart",
  "question": "What is the current campaign status?",
  "session_id": "heygen-session-id",
  "meeting_id": "teams-meeting-id"
}
```

## Safety Boundaries

- A live question requires a known `project_id`.
- A live question requires a configured avatar for the requested agent.
- Responses are grounded in stored project memory.
- Pending approvals are surfaced as `needs_human_review=true`.
- Claims, metrics, publishing decisions, deployments, and client-facing commitments should be routed for human approval.

This endpoint is a scaffold for the real-time flow. The next production step is to connect HeyGen's live session callbacks to this endpoint and then stream or return the response in the format HeyGen expects for the active avatar session.

## RamAir Live Meeting Flow

Start or register the operator-controlled Nathan session:

```json
{
  "agent_name": "nathan",
  "client_id": "ramair",
  "project_id": "ramair-straight-from-the-hart",
  "meeting_title": "RamAir Teams call with David Hart",
  "expected_attendees": ["David Hart", "ParlayVU operator"],
  "heygen_session_id": "optional-liveavatar-session-id",
  "teams_meeting_link": "optional-teams-link"
}
```

The response includes an internal `session.session_id`, Nathan's configured `avatar_id`, the project/client identity, and operator next steps. The backend does not join Teams, capture media, or record the call; the operator controls the Teams meeting and HeyGen LiveAvatar surface.

During the call, send HeyGen callbacks or browser-controller requests to:

```text
POST /heygen/live-meetings/{session_id}/question
```

Example body:

```json
{
  "question": "What is the campaign status?",
  "speaker_name": "David Hart",
  "provider_event_id": "optional-callback-id"
}
```

Responses include:

- `avatar_id`: the configured Nathan avatar.
- `answer` and `provider_response.spoken_text`: the concise spoken answer.
- `needs_human_review`: true when pending approvals or unsupported metrics/claims require human review.
- `grounding`: project id, source/output counts, pending approval count, and cited memory labels.

After the call, paste the approved summary or transcript:

```text
POST /heygen/live-meetings/{session_id}/notes
```

Example body:

```json
{
  "title": "RamAir LiveAvatar Meeting Notes",
  "summary": "Client-approved recap, decisions, blockers, and next actions.",
  "team_id": "optional-real-team-id",
  "channel_id": "optional-real-channel-id"
}
```

By default, files publish to `03_Deliverables/Meeting Notes` in the Teams channel Files workflow. If HeyGen's live session creation API details differ, keep the backend callback shape above and have the operator paste the active HeyGen session id into `heygen_session_id` when starting the meeting.
