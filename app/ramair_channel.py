from __future__ import annotations

from typing import Mapping

RAMAIR_CLIENT_ID = "ramair"
RAMAIR_PROJECT_ID = "ramair-straight-from-the-hart"
RAMAIR_PROJECT_NAME = "Straight from the Hart Content Engine"
RAMAIR_CHANNEL_NAME = "RamAir"

BINDING_COMMAND = "@ParlayVU bind this channel to RamAir"
IN_TEAMS_BINDING_PATH = [
    "Open Microsoft Teams",
    "Go to the client team that contains the RamAir project",
    "Open the RamAir channel",
    "Select Posts",
    f"Type `{BINDING_COMMAND}` and send it",
]

CHANNEL_TABS = [
    {
        "name": "Posts",
        "purpose": "Day-to-day updates, Nathan questions, approvals, and decision history.",
    },
    {
        "name": "Files",
        "purpose": "Canonical client/project documents in the channel SharePoint folder.",
    },
    {
        "name": "Planner or Tasks",
        "purpose": "Milestones, interviews, deliverables, publishing work, and approval gates.",
    },
    {
        "name": "Meeting notes in Files",
        "purpose": "Nathan-published Markdown and Word meeting notes in the channel SharePoint folder.",
    },
    {
        "name": "Performance dashboard",
        "purpose": "Power BI, Excel, or dashboard tab for campaign metrics once data is connected.",
    },
    {
        "name": "ParlayVU/Nathan",
        "purpose": "Project memory, approvals, context summaries, and next actions.",
    },
]

STARTER_FOLDERS = [
    {
        "path": "00_Client_Brief",
        "purpose": "Client overview, brand voice, objectives, target audiences, and scope.",
    },
    {
        "path": "01_Source_Material",
        "purpose": "Podcast episodes, transcripts, interviews, uploaded documents, and reference links.",
    },
    {
        "path": "02_Planning",
        "purpose": "Content calendars, campaign plans, interview schedules, and milestone plans.",
    },
    {
        "path": "03_Deliverables",
        "purpose": "Generated assets, drafts, social posts, email drafts, and landing page copy.",
    },
    {
        "path": "04_Approvals",
        "purpose": "Approval packets, final decisions, client sign-off records, and approval IDs.",
    },
    {
        "path": "05_Performance",
        "purpose": "Campaign reports, metrics exports, learnings, and optimization notes.",
    },
]

STARTER_ARTIFACTS = [
    {
        "path": "client_artifacts/ramair/README.md",
        "purpose": "Pilot overview, Teams tab standard, binding instructions, and operating rules.",
    },
    {
        "path": "client_artifacts/ramair/00_Client_Brief/client-brief.md",
        "purpose": "Starter client brief and project objective.",
    },
    {
        "path": "client_artifacts/ramair/01_Source_Material/source-material-index.md",
        "purpose": "Source material inventory and missing data notes.",
    },
    {
        "path": "client_artifacts/ramair/02_Planning/project-plan.md",
        "purpose": "Four-lane working plan for the first campaign cycle.",
    },
    {
        "path": "client_artifacts/ramair/02_Planning/interview-schedule.md",
        "purpose": "Upcoming interview/event planning stub.",
    },
    {
        "path": "client_artifacts/ramair/03_Deliverables/weekly-campaign-kit.md",
        "purpose": "Starter deliverable checklist for a weekly episode kit.",
    },
    {
        "path": "client_artifacts/ramair/04_Approvals/approval-packet.md",
        "purpose": "Approval packet template tied to Teams approval IDs.",
    },
    {
        "path": "client_artifacts/ramair/05_Performance/performance-snapshot.md",
        "purpose": "Manual performance snapshot template with strict missing-data language.",
    },
    {
        "path": "client_artifacts/ramair/05_Performance/social-performance-dashboard-spec.md",
        "purpose": "Power BI dashboard starter spec for client-facing social performance reporting.",
    },
    {
        "path": "client_artifacts/ramair/05_Performance/social-performance-workbook-template.md",
        "purpose": "Excel workbook worksheet map compatible with the CSV data layer.",
    },
    {
        "path": "client_artifacts/ramair/05_Performance/data/social_posts.csv",
        "purpose": "SharePoint-friendly post-level sample data for Power BI.",
    },
    {
        "path": "client_artifacts/ramair/05_Performance/data/social_daily_metrics.csv",
        "purpose": "Daily campaign metric sample data for Power BI trend pages.",
    },
    {
        "path": "client_artifacts/ramair/05_Performance/data/social_kpi_targets.csv",
        "purpose": "KPI target table for Power BI cards and variance calculations.",
    },
    {
        "path": "client_artifacts/ramair/nathan-prompts.md",
        "purpose": "Standard Nathan prompts for status, approvals, interviews, metrics, and weekly updates.",
    },
    {
        "path": "client_artifacts/ramair/next-automation.md",
        "purpose": "The first next automation after channel binding.",
    },
]

STANDARD_NATHAN_PROMPTS = [
    {
        "name": "Project Status",
        "prompt": "@ParlayVU summarize the current RamAir project status from project memory.",
        "guardrail": "Use only stored RamAir memory and name any missing source material.",
    },
    {
        "name": "Approvals",
        "prompt": "@ParlayVU what approvals are pending for RamAir, including approval IDs and blockers?",
        "guardrail": "Do not imply anything is approved unless the approval record says so.",
    },
    {
        "name": "Interviews",
        "prompt": "@ParlayVU what RamAir interviews or events are planned, and what prep is missing?",
        "guardrail": "Say when planned interviews/events have not been stored yet.",
    },
    {
        "name": "Metrics",
        "prompt": "@ParlayVU summarize the latest RamAir performance snapshot and call out missing metrics.",
        "guardrail": "Never invent performance numbers; report only connected or stored metrics.",
    },
    {
        "name": "Weekly Update",
        "prompt": "@ParlayVU prepare a client-facing weekly RamAir update with decisions, blockers, and next actions.",
        "guardrail": "Keep the update client-safe and flag approval-required claims.",
    },
]

NEXT_AUTOMATION = {
    "name": "planned_interviews_and_events",
    "title": "Planned interviews/events capture",
    "reason": (
        "After the channel is bound, Nathan needs a structured way to store upcoming interviews "
        "and events from Teams posts so weekly updates can answer what is planned without guessing."
    ),
    "teams_prompt": "@ParlayVU add this planned RamAir interview to project memory: <guest/topic/date/prep notes>",
    "memory_target": "project memory agent event or future interview/event table",
}


def binding_status_from_env(env: Mapping[str, str]) -> dict[str, object]:
    required = {
        "RAMAIR_TEAMS_TEAM_ID": env.get("RAMAIR_TEAMS_TEAM_ID", ""),
        "RAMAIR_TEAMS_CHANNEL_ID": env.get("RAMAIR_TEAMS_CHANNEL_ID", ""),
    }
    missing = [name for name, value in required.items() if not value]
    return {
        "configured": not missing,
        "missing": missing,
        "team_id": required["RAMAIR_TEAMS_TEAM_ID"],
        "channel_id": required["RAMAIR_TEAMS_CHANNEL_ID"],
        "channel_name": env.get("RAMAIR_TEAMS_CHANNEL_NAME", RAMAIR_CHANNEL_NAME),
        "bound_by": env.get("RAMAIR_TEAMS_BOUND_BY", ""),
        "in_teams_path": IN_TEAMS_BINDING_PATH,
        "command": BINDING_COMMAND,
    }


def render_ramair_channel_pilot() -> str:
    lines = [
        "# RamAir Client Channel Pilot",
        "",
        f"Client: `{RAMAIR_CLIENT_ID}`",
        f"Project: `{RAMAIR_PROJECT_ID}`",
        f"Teams channel: `{RAMAIR_CHANNEL_NAME}`",
        "",
        "## Teams Tabs",
    ]
    lines.extend(f"- `{tab['name']}`: {tab['purpose']}" for tab in CHANNEL_TABS)
    lines.extend(["", "## Files Folder Structure"])
    lines.extend(f"- `{folder['path']}`: {folder['purpose']}" for folder in STARTER_FOLDERS)
    lines.extend(["", "## Binding"])
    lines.extend(f"{index}. {step}" for index, step in enumerate(IN_TEAMS_BINDING_PATH, start=1))
    lines.extend(["", "## Standard Nathan Prompts"])
    lines.extend(f"- {item['name']}: `{item['prompt']}`" for item in STANDARD_NATHAN_PROMPTS)
    lines.extend(["", "## Next Automation"])
    lines.append(f"{NEXT_AUTOMATION['title']}: {NEXT_AUTOMATION['reason']}")
    return "\n".join(lines) + "\n"
