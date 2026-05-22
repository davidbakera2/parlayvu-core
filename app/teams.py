import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class TeamsSettings:
    app_id: str
    app_password: str
    tenant_id: str
    webhook_secret: str

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_password and self.tenant_id)


def get_teams_settings() -> TeamsSettings:
    return TeamsSettings(
        app_id=os.getenv("TEAMS_APP_ID", ""),
        app_password=os.getenv("TEAMS_APP_PASSWORD", ""),
        tenant_id=os.getenv("TEAMS_TENANT_ID", os.getenv("MICROSOFT_TENANT_ID", "")),
        webhook_secret=os.getenv("TEAMS_WEBHOOK_SECRET", ""),
    )


def teams_status(settings: TeamsSettings | None = None) -> dict[str, Any]:
    active_settings = settings or get_teams_settings()
    return {
        "configured": active_settings.configured,
        "tenant_configured": bool(active_settings.tenant_id),
        "webhook_secret_configured": bool(active_settings.webhook_secret),
    }


def normalize_teams_message(text: str) -> str:
    return " ".join(text.strip().split())


def strip_bot_mentions(text: str, entities: list[dict[str, Any]] | None = None) -> str:
    clean_text = text or ""
    for entity in entities or []:
        if entity.get("type") == "mention":
            mentioned = entity.get("mentioned") or {}
            if mentioned.get("application") or mentioned.get("bot") or mentioned.get("id"):
                clean_text = clean_text.replace(entity.get("text", ""), " ")
    return normalize_teams_message(clean_text)


def is_bot_framework_activity(payload: dict[str, Any]) -> bool:
    return "type" in payload and "conversation" in payload and "serviceUrl" in payload


def teams_message_from_activity(activity: dict[str, Any]) -> dict[str, Any]:
    channel_data = activity.get("channelData") or {}
    team = channel_data.get("team") or {}
    channel = channel_data.get("channel") or {}
    conversation = activity.get("conversation") or {}
    from_user = activity.get("from") or {}
    text = strip_bot_mentions(activity.get("text", ""), activity.get("entities") or [])

    client_id = "default-client"
    project_id = None
    if "ramair" in text.lower():
        client_id = "ramair"
        project_id = "ramair-straight-from-the-hart"

    return {
        "text": text,
        "from_user": from_user.get("userPrincipalName") or from_user.get("name") or from_user.get("id"),
        "conversation_id": conversation.get("id"),
        "team_id": team.get("id"),
        "channel_id": channel.get("id"),
        "channel_name": channel.get("name"),
        "client_id": client_id,
        "project_id": project_id,
    }


def is_channel_bind_request(text: str) -> bool:
    normalized = normalize_teams_message(text).lower()
    return "bind" in normalized and "channel" in normalized


def is_meeting_note_publish_request(text: str) -> bool:
    normalized = normalize_teams_message(text).lower()
    return (
        any(target in normalized for target in ("files", "sharepoint", "teams", "onenote"))
        and "meeting" in normalized
        and "note" in normalized
        and any(verb in normalized for verb in ("publish", "create", "write"))
    )


def is_graph_team_id(value: str | None) -> bool:
    return bool(
        re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            (value or "").strip(),
            flags=re.IGNORECASE,
        )
    )


def graph_files_target_from_teams_activity(team_id: str | None, channel_id: str | None) -> dict[str, str | None]:
    clean_team_id = (team_id or "").strip()
    clean_channel_id = (channel_id or "").strip()
    if not clean_team_id or not clean_channel_id or not is_graph_team_id(clean_team_id):
        return {"team_id": None, "channel_id": None}
    return {"team_id": clean_team_id, "channel_id": clean_channel_id}


def parse_meeting_note_publish_command(text: str) -> dict[str, str]:
    cleaned = re.sub(r"^\s*nathan[:,]?\s*", "", text.strip(), flags=re.IGNORECASE)
    title = "RamAir Meeting Notes"
    lowered = cleaned.lower()
    target = "onenote" if "onenote" in lowered else "files"

    title_match = re.search(
        r"(?:^|\s)title\s*:\s*(.+?)(?=\s+summary\s*:|$)",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if title_match:
        title = title_match.group(1).strip()

    summary_match = re.search(r"(?:^|\s)summary\s*:\s*(.+)", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if summary_match:
        summary = summary_match.group(1).strip()
    else:
        parts = re.split(
            r"(?:to\s+(?:onenote|files|sharepoint|teams\s+files)|meeting\s+note)\s*:\s*",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        summary = parts[-1].strip() if len(parts) > 1 else cleaned

    return {"title": title, "summary": summary, "target": target}


def resolve_demo_bind_target(text: str) -> dict[str, str] | None:
    if "ramair" not in text.lower():
        return None
    return {
        "client_id": "ramair",
        "project_id": "ramair-straight-from-the-hart",
        "project_name": "Straight from the Hart Content Engine",
    }


async def get_bot_framework_token(settings: TeamsSettings | None = None) -> str:
    active_settings = settings or get_teams_settings()
    if not active_settings.configured:
        raise RuntimeError("Teams bot credentials are not configured")

    token_tenant = active_settings.tenant_id or "botframework.com"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{token_tenant}/oauth2/v2.0/token",
            data={
                "client_id": active_settings.app_id,
                "client_secret": active_settings.app_password,
                "grant_type": "client_credentials",
                "scope": "https://api.botframework.com/.default",
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]


async def send_bot_framework_reply(activity: dict[str, Any], text: str, settings: TeamsSettings | None = None) -> None:
    service_url = (activity.get("serviceUrl") or "").rstrip("/")
    conversation = activity.get("conversation") or {}
    conversation_id = conversation.get("id")
    activity_id = activity.get("id")
    if not service_url or not conversation_id or not activity_id:
        raise ValueError("Bot Framework activity is missing serviceUrl, conversation.id, or id")

    token = await get_bot_framework_token(settings)
    reply = {
        "type": "message",
        "from": activity.get("recipient"),
        "recipient": activity.get("from"),
        "conversation": conversation,
        "replyToId": activity_id,
        "text": text,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{service_url}/v3/conversations/{conversation_id}/activities/{activity_id}",
            headers={"Authorization": f"Bearer {token}"},
            json=reply,
        )
        response.raise_for_status()


def nathan_response_to_text(nathan_response: dict[str, Any]) -> str:
    final_output = nathan_response.get("final_output") or {}
    if isinstance(final_output, dict):
        content = final_output.get("content")
        if content:
            return str(content)
    route_decision = nathan_response.get("route_decision") or {}
    if isinstance(route_decision, dict) and route_decision.get("reason"):
        return str(route_decision["reason"])
    project_context = nathan_response.get("project_context") or {}
    if project_context:
        return f"Nathan routed your request with project context for {project_context.get('name', 'this project')}."
    return "Nathan received your request and routed it to the ParlayVU team."


def grounded_project_reply(project_context: dict[str, Any], approvals: list[dict[str, Any]]) -> str:
    client = project_context.get("client") or {}
    client_name = client.get("name") or project_context.get("client_id") or "the client"
    project_name = project_context.get("name") or project_context.get("id") or "the project"
    objective = project_context.get("objective") or "No project objective is stored yet."
    sources = project_context.get("source_assets") or []
    outputs = project_context.get("generated_outputs") or []
    pending = [approval for approval in approvals if approval.get("status") == "pending"]

    lines = [
        f"Here is what I can say from ParlayVU project memory for {client_name}:",
        "",
        f"Project: {project_name}",
        f"Objective: {objective}",
        f"Memory: {len(sources)} source asset(s), {len(outputs)} generated output(s)",
        "",
        f"Pending approvals ({len(pending)}):",
    ]
    if pending:
        for approval in pending:
            metadata = approval.get("metadata") or {}
            output = approval.get("generated_output") or {}
            title = metadata.get("title") or output.get("title") or f"Approval {approval.get('id')}"
            summary = approval.get("decision_notes") or "No approval summary is stored."
            action_type = metadata.get("action_type", "approval")
            approval_id = approval.get("id")
            lines.append(f"- {title} ({action_type})")
            if approval_id:
                lines.append(f"  Approval ID: {approval_id}")
            lines.append(f"  Summary: {summary}")
    else:
        lines.append("- No pending approvals are stored for this project.")

    lines.extend(
        [
            "",
            "Next safe step: review the pending approval items before publishing, deploying, or sending anything externally.",
            "I do not have stored support for budgets, performance percentages, pipeline projections, venue contracts, or partner terms unless those are added to project memory or source assets.",
        ]
    )
    return "\n".join(lines)


def approval_to_teams_card(approval: dict[str, Any]) -> dict[str, Any]:
    metadata = approval.get("metadata") or {}
    output = approval.get("generated_output") or {}
    title = metadata.get("title") or output.get("title") or f"Approval {approval.get('id')}"
    action_type = metadata.get("action_type", "approval")

    return {
        "type": "approval_card",
        "approval_id": approval.get("id"),
        "project_id": approval.get("project_id"),
        "status": approval.get("status"),
        "title": title,
        "subtitle": f"{action_type} requested by {approval.get('requested_by_agent')}",
        "summary": approval.get("decision_notes"),
        "generated_output": output,
        "facts": {
            "action_type": action_type,
            "requested_by_agent": approval.get("requested_by_agent"),
            "created_at": approval.get("created_at"),
        },
        "actions": [
            {"id": "approved", "label": "Approve"},
            {"id": "changes_requested", "label": "Request Changes"},
            {"id": "rejected", "label": "Reject"},
        ],
    }


def approvals_to_teams_cards(approvals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [approval_to_teams_card(approval) for approval in approvals]
