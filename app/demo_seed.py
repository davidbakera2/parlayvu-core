from sqlalchemy.orm import Session

from app.models import AgentEvent, Approval, Client, GeneratedOutput, Project, SourceAsset
from app.ramair_channel import NEXT_AUTOMATION, STANDARD_NATHAN_PROMPTS, STARTER_ARTIFACTS

RAMAIR_CLIENT_ID = "ramair"
RAMAIR_PROJECT_ID = "ramair-straight-from-the-hart"
RAMAIR_CLIENT_NAME = "RamAir International"


def seed_ramair_demo(session: Session) -> dict:
    """Seed an idempotent RamAir demo project for investor walkthroughs."""
    client = session.get(Client, RAMAIR_CLIENT_ID)
    if client is None:
        client = Client(
            id=RAMAIR_CLIENT_ID,
            name=RAMAIR_CLIENT_NAME,
            brand_voice_summary="Practical, credible, and sales-supportive for B2B facility and duct-cleaning audiences.",
            disclosure_rules={
                "client_facing_claims_require_approval": True,
                "sales_lead_metrics_require_source": True,
            },
            channel_preferences={
                "primary": ["YouTube", "LinkedIn", "RamAir website"],
                "secondary": ["Instagram", "TikTok", "Facebook", "X"],
            },
        )
        session.add(client)
    elif client.name != RAMAIR_CLIENT_NAME:
        client.name = RAMAIR_CLIENT_NAME

    project = session.get(Project, RAMAIR_PROJECT_ID)
    if project is None:
        project = Project(
            id=RAMAIR_PROJECT_ID,
            client=client,
            name="Straight from the Hart Content Engine",
            objective=(
                "Turn each weekly podcast episode into a coordinated campaign across video, "
                "short clips, social posts, website updates, transcript insights, case studies, "
                "and sales collateral."
            ),
            approval_policy={
                "publish_requires_human_approval": True,
                "deploy_requires_human_approval": True,
                "outbound_email_requires_human_approval": True,
            },
            metadata_json={
                "case_study": "RamAir: Straight from the Hart",
                "proof_point": "One weekly show becomes a multi-channel marketing cadence.",
                "teams_channel_pilot": {
                    "channel_name": "RamAir",
                    "artifact_root": "client_artifacts/ramair",
                },
            },
        )
        session.add(project)
    else:
        project.metadata_json = {
            **(project.metadata_json or {}),
            "teams_channel_pilot": {
                "channel_name": "RamAir",
                "artifact_root": "client_artifacts/ramair",
            },
        }

    source = (
        session.query(SourceAsset)
        .filter_by(project_id=RAMAIR_PROJECT_ID, title="Straight from the Hart weekly episode")
        .one_or_none()
    )
    if source is None:
        source = SourceAsset(
            project=project,
            asset_type="video_podcast",
            title="Straight from the Hart weekly episode",
            uri="https://www.youtube.com/playlist?list=PLfwEIpYOOZ7IGdzFAhfPHjdPBi9a_ONDY",
            summary=(
                "Weekly expert-led RamAir source content used to generate clips, posts, "
                "website updates, educational excerpts, case studies, and sell sheets."
            ),
            metadata_json={
                "shorts_playlist": "https://www.youtube.com/playlist?list=PLfwEIpYOOZ7Is0JshJZ5Elnomg9H0GvWk",
                "website": "https://ramair.co/blogs/",
                "industry_site": "https://www.positiveairductcleaning.org/",
            },
        )
        session.add(source)

    artifact_source = (
        session.query(SourceAsset)
        .filter_by(project_id=RAMAIR_PROJECT_ID, title="RamAir client channel starter artifacts")
        .one_or_none()
    )
    if artifact_source is None:
        artifact_source = SourceAsset(
            project=project,
            asset_type="document_library",
            title="RamAir client channel starter artifacts",
            uri="client_artifacts/ramair/README.md",
            summary=(
                "Starter Teams channel materials for client brief, source inventory, planning, "
                "deliverables, approvals, performance, Nathan prompts, and next automation."
            ),
            metadata_json={
                "artifact_paths": [artifact["path"] for artifact in STARTER_ARTIFACTS],
                "teams_channel": "RamAir",
            },
        )
        session.add(artifact_source)

    output = (
        session.query(GeneratedOutput)
        .filter_by(project_id=RAMAIR_PROJECT_ID, title="Weekly episode campaign kit")
        .one_or_none()
    )
    if output is None:
        output = GeneratedOutput(
            project=project,
            source_asset=source,
            agent_name="nathan",
            output_type="campaign_kit",
            title="Weekly episode campaign kit",
            content=(
                "Demo output bundle: YouTube episode, Shorts/Reels/TikTok clips, LinkedIn and "
                "Facebook posts, website recap, transcript insights, case-study draft, and sell-sheet angles."
            ),
            status="draft",
            metadata_json={
                "demo_ready": True,
                "agents": ["nathan", "ava", "dylan", "riley", "jordan", "michael"],
            },
        )
        session.add(output)

    channel_output = (
        session.query(GeneratedOutput)
        .filter_by(project_id=RAMAIR_PROJECT_ID, title="RamAir Teams channel pilot kit")
        .one_or_none()
    )
    if channel_output is None:
        channel_output = GeneratedOutput(
            project=project,
            source_asset=artifact_source,
            agent_name="nathan",
            output_type="client_channel_pilot",
            title="RamAir Teams channel pilot kit",
            content=(
                "Standard Teams channel tabs, Files folder structure, starter RamAir project "
                "artifacts, binding instructions, Nathan prompts, and first next automation."
            ),
            uri="docs/ramair-client-channel-pilot.md",
            status="ready",
            metadata_json={
                "nathan_prompts": STANDARD_NATHAN_PROMPTS,
                "next_automation": NEXT_AUTOMATION,
            },
        )
        session.add(channel_output)

    session.flush()

    approval = (
        session.query(Approval)
        .filter_by(project_id=RAMAIR_PROJECT_ID, generated_output=output, requested_by_agent="nathan")
        .one_or_none()
    )
    if approval is None:
        approval = Approval(
            project=project,
            generated_output=output,
            requested_by_agent="nathan",
            status="pending",
            decision_notes="Demo approval gate for publishing/deployment actions.",
        )
        session.add(approval)

    event = (
        session.query(AgentEvent)
        .filter_by(project_id=RAMAIR_PROJECT_ID, agent_name="nathan", event_type="demo_seeded")
        .one_or_none()
    )
    if event is None:
        event = AgentEvent(
            project=project,
            client=client,
            agent_name="nathan",
            event_type="demo_seeded",
            channel="system",
            summary="Seeded RamAir demo project memory for investor walkthroughs.",
            payload={"client_id": RAMAIR_CLIENT_ID, "project_id": RAMAIR_PROJECT_ID},
        )
        session.add(event)

    next_automation_event = (
        session.query(AgentEvent)
        .filter_by(project_id=RAMAIR_PROJECT_ID, agent_name="nathan", event_type="next_automation_identified")
        .one_or_none()
    )
    if next_automation_event is None:
        next_automation_event = AgentEvent(
            project=project,
            client=client,
            agent_name="nathan",
            event_type="next_automation_identified",
            channel="teams",
            summary="Identified planned interviews/events capture as the first automation after channel binding.",
            payload=NEXT_AUTOMATION,
        )
        session.add(next_automation_event)

    session.flush()
    return {
        "client_id": client.id,
        "project_id": project.id,
        "source_asset_id": source.id,
        "artifact_source_asset_id": artifact_source.id,
        "generated_output_id": output.id,
        "channel_pilot_output_id": channel_output.id,
        "approval_id": approval.id,
        "agent_event_id": event.id,
        "next_automation_event_id": next_automation_event.id,
    }
