# RamAir Client Channel Pilot

RamAir is the pilot client channel for the standard ParlayVU Teams project room. Teams holds the client-facing conversation, files, tasks, notes, dashboards, and approvals; ParlayVU/Nathan holds memory, routing, summaries, approvals, and next actions.

## Channel Standard

Create one Teams channel named `RamAir` for the project `ramair-straight-from-the-hart`.

Recommended tabs:

- `Posts`: day-to-day updates, Nathan questions, approvals, and decision history.
- `Files`: canonical client/project documents in the channel SharePoint folder.
- `Planner` or `Tasks`: milestones, interviews, deliverables, publishing tasks, and approval gates.
- `Meeting notes in Files`: Nathan-published `.md` and `.docx` recaps in the channel SharePoint folder.
- `Performance dashboard`: Power BI in Teams backed by SharePoint-hosted CSV files.
- `ParlayVU/Nathan`: bot-driven project memory, approvals, summaries, and next actions.

Recommended `Files` folders:

- `00_Client_Brief`: client overview, brand voice, objectives, target audiences, and scope.
- `01_Source_Material`: podcast episodes, transcripts, interviews, uploaded documents, and reference links.
- `02_Planning`: content calendars, campaign plans, interview schedules, and milestone plans.
- `03_Deliverables`: generated assets, drafts, social posts, email drafts, and landing page copy.
- `04_Approvals`: approval packets, final decisions, client sign-off records, and approval IDs.
- `05_Performance`: campaign reports, metrics exports, learnings, and optimization notes.

Starter files live in `client_artifacts/ramair/` and mirror this folder structure.

## Binding To Project Memory

The backend can bind a real Teams channel to RamAir project memory when the real Teams identifiers are available:

```powershell
$env:RAMAIR_TEAMS_TEAM_ID = "<real Teams team id>"
$env:RAMAIR_TEAMS_CHANNEL_ID = "<real Teams channel id>"
$env:RAMAIR_TEAMS_CHANNEL_NAME = "RamAir"
$env:RAMAIR_TEAMS_BOUND_BY = "dave@parlayvu.ai"
python scripts/ramair_channel_pilot.py --bind
```

If the real Teams IDs are not available, bind from inside Teams:

1. Open Microsoft Teams.
2. Go to the client team that contains the RamAir project.
3. Open the `RamAir` channel.
4. Select `Posts`.
5. Send `@ParlayVU bind this channel to RamAir`.

Nathan will resolve that command to `client_id=ramair` and `project_id=ramair-straight-from-the-hart` when it is sent from a Bot Framework activity with real `team_id` and `channel_id` values.

## Standard Nathan Prompts

- Project status: `@ParlayVU summarize the current RamAir project status from project memory.`
- Approvals: `@ParlayVU what approvals are pending for RamAir, including approval IDs and blockers?`
- Interviews: `@ParlayVU what RamAir interviews or events are planned, and what prep is missing?`
- Metrics: `@ParlayVU summarize the latest RamAir performance snapshot and call out missing metrics.`
- Weekly update: `@ParlayVU prepare a client-facing weekly RamAir update with decisions, blockers, and next actions.`
- Meeting notes: `@ParlayVU Nathan, publish meeting note to Files Title: RamAir Weekly Meeting Summary: Client-approved recap and next steps.`

Nathan should be strict about missing memory. If interviews, events, metrics, or source materials are not stored yet, he should say so instead of filling gaps with assumptions.

## First Next Automation

The first automation after binding is planned interviews/events capture from Teams posts into project memory.

Target command:

```text
@ParlayVU add this planned RamAir interview to project memory: <guest/topic/date/prep notes>
```

This should be implemented before document ingestion or performance dashboard automation because it unlocks reliable weekly updates and lets Nathan answer what is planned without guessing.

## Meeting Notes In Files

The new MVP path is Teams/SharePoint Files, not OneNote. Nathan publishes every meeting note as:

- `.md` for machine-friendly project memory, search, and future agent ingestion.
- `.docx` for client-facing review in Word or Teams.

Default API path:

```text
POST /m365/files/meeting-notes
```

Default Teams command:

```text
@ParlayVU Nathan, publish meeting note to Files
Title: RamAir Weekly Meeting
Summary: Client-approved recap and next steps from ParlayVU project memory.
```

The files land under `03_Deliverables/Meeting Notes` unless `M365_FILES_BASE_PATH` or the API request `folder_path` overrides it.

## LiveAvatar Teams Call Workflow

This MVP uses HeyGen LiveAvatar as an operator-controlled meeting companion, not an autonomous Teams media bot. Nathan appears through HeyGen, answers grounded questions from ParlayVU project memory, and publishes approved post-call notes to Teams Files.

Before the call:

1. Confirm `HEYGEN_NATHAN_AVATAR_ID`, Microsoft 365 Files settings, and project memory are configured in the hosted environment.
2. Start or register the meeting with `POST /heygen/live-meetings/start` for `project_id=ramair-straight-from-the-hart`.
3. Open the Nathan HeyGen LiveAvatar controller and the Teams meeting. If needed, share the LiveAvatar window from the operator machine.

During the call:

1. Route client questions through `POST /heygen/live-meetings/{session_id}/question`.
2. Use the returned `provider_response.spoken_text` as Nathan's spoken response.
3. Treat `needs_human_review=true` as a stop sign for metrics, claims, publishing commitments, or pending approvals.

After the call:

1. Paste the approved recap or transcript into `POST /heygen/live-meetings/{session_id}/notes`.
2. Nathan publishes `.md` and `.docx` notes to `03_Deliverables/Meeting Notes`.
3. Share the Teams Files link back in the RamAir channel or meeting follow-up.

The deferred production path is a true Teams media bot with Microsoft Graph Cloud Communications permissions, recording/transcription compliance, and tenant policies. Do not demo this MVP as autonomous Teams joining or recording.

## Power BI Dashboard Starter

The dashboard MVP lives under `client_artifacts/ramair/05_Performance/`:

- `social-performance-dashboard-spec.md` defines pages, KPIs, starter DAX, and Teams tab setup.
- `social-performance-workbook-template.md` maps the optional Excel workbook worksheets to the CSV files.
- `data/social_posts.csv` stores planned and published content rows.
- `data/social_daily_metrics.csv` stores day/platform/campaign metric rows.
- `data/social_kpi_targets.csv` stores client-approved targets.
- `data/schema.md` documents stable column names for Power BI refresh.

To add the client-facing Teams tab:

1. Upload `05_Performance/data/` to the RamAir channel Files folder.
2. Build a Power BI report from the Team SharePoint folder connector.
3. Publish the report to the workspace connected to the client Team.
4. Add a Power BI tab in the RamAir channel and select the report.
5. Refresh the dataset after Nathan or an operator updates the CSV files.
