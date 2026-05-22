# Compliant Transcript And Meeting Notes Flow

The Teams media bot must not create meeting notes by silently recording or persisting raw Teams media. ParlayVU should receive text only after it is created through a compliant Teams transcript path or approved by the operator/client.

## Preferred Flow: Teams Native Transcript

1. The organizer enables Teams native transcription or recording according to tenant policy.
2. Meeting participants see the standard Teams transcription or recording indicators.
3. After the meeting, an authorized app or user retrieves the transcript through Microsoft Graph where policy and permissions allow it.
4. The transcript text is posted to the media bot:

   ```text
   POST /meetings/{sessionId}/notes
   ```

5. The media bot forwards the transcript to ParlayVU's existing notes endpoint.
6. ParlayVU publishes `.md` and template `.docx` meeting notes to the configured Teams Files folder.

## Alternative Flow: Approved Upload

Use this when Graph transcript retrieval is not available, the meeting type is unsupported, or the tenant has not approved the transcript API permissions.

1. The operator obtains a Teams transcript or client-approved notes text through an approved process.
2. The operator reviews and redacts sensitive content if needed.
3. The operator posts the approved summary or transcript to `POST /meetings/{sessionId}/notes`.
4. ParlayVU publishes the Files artifacts and logs the event in project memory when enabled.

## Permissions And Policy Checks

Before automating transcript retrieval, confirm:

- The tenant allows transcription or recording for the relevant users and meeting type.
- The app has admin-consented transcript permissions, such as `OnlineMeetingTranscript.Read.All`, `OnlineMeetingTranscript.Read.Chat`, or `CallTranscripts.Read.All`, depending on the scenario.
- Application access policies are configured when Microsoft Graph requires organizer-scoped access for application permissions.
- The meeting type is supported by the transcript API being used. Some APIs have limits for channel meetings or expired meetings.
- The tenant accepts any metered API requirements for Teams transcripts and recordings.

## Explicit Non-Goals

- No silent raw-media recording.
- No storing audio/video frames from Graph media APIs for later transcription.
- No autonomous transcript publishing without organizer policy, participant notice, and operator/client approval.
- No claim that Nathan can join and listen autonomously until Graph media join and compliance controls are implemented and tested.
