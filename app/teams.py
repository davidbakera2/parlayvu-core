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


def is_one_to_one_dm(payload: dict[str, Any]) -> bool:
    """True if the Bot Framework activity is a 1:1 personal chat, not a
    channel/group conversation.

    Heuristic: channel messages have `channelData.team.id` and
    `channelData.channel.id`. 1:1 DMs lack the team/channel block.
    Conservatively also treat anything where `conversation.conversationType`
    is explicitly 'personal' as a DM, regardless of channelData.
    """
    conversation = payload.get("conversation") or {}
    if (conversation.get("conversationType") or "").lower() == "personal":
        return True
    channel_data = payload.get("channelData") or {}
    team = channel_data.get("team") or {}
    channel = channel_data.get("channel") or {}
    return not (team.get("id") and channel.get("id"))


# ── Attachment handling ────────────────────────────────────────────────────────
#
# Teams file uploads arrive in Bot Framework activities under `attachments`
# with contentType="application/vnd.microsoft.teams.file.download.info".
# The actual file lives at attachment["content"]["downloadUrl"] — a pre-
# authorized SharePoint URL that doesn't require a bearer token.
# Other attachment shapes (inline images, etc.) are handled best-effort.

TEAMS_FILE_CONTENT_TYPE = "application/vnd.microsoft.teams.file.download.info"


def extract_teams_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Bot Framework attachments into a flat list of
    `{name, content_type, content_url, size}` dicts.

    Skips attachments with no usable URL (e.g. card definitions, mentions
    encoded as attachments).
    """
    out: list[dict[str, Any]] = []
    for att in payload.get("attachments") or []:
        if not isinstance(att, dict):
            continue
        name = att.get("name") or ""
        content_type = att.get("contentType") or ""
        # Teams file uploads put the real download URL inside `content`.
        inner_content = att.get("content") if isinstance(att.get("content"), dict) else {}
        content_url = (
            inner_content.get("downloadUrl")
            or att.get("contentUrl")
            or ""
        )
        if not content_url:
            continue
        out.append({
            "name": name or "attachment",
            "content_type": content_type,
            "content_url": content_url,
            "size": inner_content.get("fileSize") or att.get("contentLength"),
            "is_teams_file": content_type == TEAMS_FILE_CONTENT_TYPE,
        })
    return out


async def download_bot_framework_attachment(
    content_url: str,
    *,
    settings: TeamsSettings | None = None,
    requires_bot_auth: bool = False,
) -> bytes:
    """Download a Teams attachment by URL.

    `requires_bot_auth=True` adds the Bot Framework OAuth token (needed for
    some attachment URLs that aren't pre-authorized). Teams file uploads
    use pre-signed SharePoint download URLs that work without a token, so
    the default is no auth.
    """
    headers: dict[str, str] = {}
    if requires_bot_auth:
        token = await get_bot_framework_token(settings)
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(content_url, headers=headers)
        response.raise_for_status()
        return response.content


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


_RESET_PATTERNS = (
    "start over",
    "starting over",
    "reset conversation",
    "reset chat",
    "reset memory",
    "new conversation",
    "new chat",
    "forget that",
    "forget everything",
    "clear history",
    "clear memory",
    "fresh start",
)


def is_conversation_reset_request(text: str) -> bool:
    """Detect explicit asks to clear Nathan's conversation memory.

    Matches a small set of natural phrasings rather than a slash command
    so users don't have to learn syntax. Case-insensitive, ignores the bot
    mention. Conservative on purpose — false positives wipe history, so we
    require a multi-word phrase rather than a single word like "reset"
    (which could appear in legitimate questions like "what's our reset
    policy on subscriptions?").
    """
    normalized = normalize_teams_message(text).lower().strip()
    if not normalized:
        return False
    return any(pattern in normalized for pattern in _RESET_PATTERNS)


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
    """Match a `@ParlayVU bind this channel to <client>` chat command against
    any active client's id or display_name in client_artifacts/.

    Reads the live client roster from list_clients() and load_client_config()
    so adding a new client (drop a config.yaml, no code change) automatically
    becomes bindable from chat. Falls back to nothing if no client matches.

    Matching is case-insensitive and tolerates a few variants:
      - "RamAir" or "ramair" → ramair
      - "Christ's Hope" or "Christs Hope" or "christshope" → christshope
      - "ULC" or "ULC Ann Arbor" or "ulcannarbor" → ulcannarbor
    Apostrophes and whitespace are stripped before comparison.
    """
    from app.client_config import ClientConfigError, list_clients, load_client_config

    if not text:
        return None
    needle = _normalize_for_match(text)

    best_match: tuple[str, str, str] | None = None  # (client_id, display_name, matched_token)
    for client_id in list_clients():
        try:
            config = load_client_config(client_id)
        except ClientConfigError:
            continue
        # Build the set of strings that count as a match for this client.
        candidates = {client_id, config.display_name}
        for cand in list(candidates):
            candidates.add(_normalize_for_match(cand))
        for cand in candidates:
            cand_norm = _normalize_for_match(cand)
            if cand_norm and cand_norm in needle:
                # Prefer the longest match if multiple clients hit (e.g.
                # "ulc" would match a hypothetical "ulc" prefix in another
                # client's display name).
                if best_match is None or len(cand_norm) > len(best_match[2]):
                    best_match = (client_id, config.display_name, cand_norm)
                break

    if not best_match:
        return None
    client_id, display_name, _ = best_match
    return {
        "client_id": client_id,
        # No project_id concept per-client yet — keep stable for the bind row
        # but don't fabricate one. The caller stores client_id; project_id is
        # informational metadata for now.
        "project_id": f"{client_id}-default",
        "project_name": display_name,
    }


def _normalize_for_match(value: str) -> str:
    """Strip punctuation + whitespace and lowercase for fuzzy client matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


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


# ── Adaptive Card builders for site-approval flow ─────────────────────────────


def build_site_variations_approval_card(
    *,
    approval_id: str,
    client_display_name: str,
    target_domain: str | None,
    variations: list[dict[str, Any]],
    preview_index_url: str | None,
) -> dict[str, Any]:
    """Build an Adaptive Card 1.4 JSON payload for a variations-approval prompt.

    The card lists each variation with its design thesis + a direct preview
    link, and surfaces one "Approve variant N" Action.Submit per variant. Tap
    posts back to the bot with `{ kind: "approve_site_variant", approval_id, selected_variant }`
    in the activity value, which `/teams/messages` routes to the approvals
    decision handler.

    `variations` entries are expected to have keys: variation_number (int),
    thesis (str). Preview URL per variant is composed from preview_index_url +
    "/variation-{n}/".
    """
    domain_line = (
        f"Approve to publish your pick to **{target_domain}**."
        if target_domain
        else "Approve to publish your pick to production."
    )
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"{client_display_name} — homepage drafts",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": domain_line,
            "wrap": True,
            "isSubtle": True,
            "spacing": "Small",
        },
    ]
    if preview_index_url:
        body.append(
            {
                "type": "TextBlock",
                "text": f"[Browse all drafts]({preview_index_url})",
                "wrap": True,
                "spacing": "Small",
            }
        )

    actions: list[dict[str, Any]] = []
    for v in variations:
        n = v["variation_number"]
        thesis = str(v.get("thesis", "")).strip()
        variant_url = (
            preview_index_url.rstrip("/") + f"/variation-{n}/"
            if preview_index_url
            else None
        )
        # One row per variant: thesis + open-preview link.
        row_text = f"**Variant {n}** — {thesis}" if thesis else f"**Variant {n}**"
        if variant_url:
            row_text += f"  ·  [open preview]({variant_url})"
        body.append(
            {
                "type": "TextBlock",
                "text": row_text,
                "wrap": True,
                "spacing": "Medium",
            }
        )
        actions.append(
            {
                "type": "Action.Submit",
                "title": f"Approve variant {n}",
                "data": {
                    "kind": "approve_site_variant",
                    "approval_id": approval_id,
                    "selected_variant": n,
                },
            }
        )
    actions.append(
        {
            "type": "Action.Submit",
            "title": "Reject all",
            "style": "destructive",
            "data": {
                "kind": "reject_site_variants",
                "approval_id": approval_id,
            },
        }
    )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }


def build_site_edit_approval_card(
    *,
    approval_id: str,
    client_display_name: str,
    target_domain: str | None,
    change_description: str,
    preview_url: str | None,
) -> dict[str, Any]:
    """Approval card for a single targeted edit (one Approve / Reject pair)."""
    domain_line = (
        f"Approve to publish this edit to **{target_domain}**."
        if target_domain
        else "Approve to publish this edit to production."
    )
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"{client_display_name} — homepage edit",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": domain_line,
            "wrap": True,
            "isSubtle": True,
            "spacing": "Small",
        },
        {
            "type": "TextBlock",
            "text": f"**Change:** {change_description}",
            "wrap": True,
            "spacing": "Medium",
        },
    ]
    if preview_url:
        body.append(
            {
                "type": "TextBlock",
                "text": f"[Open preview]({preview_url})",
                "wrap": True,
                "spacing": "Small",
            }
        )
    actions = [
        {
            "type": "Action.Submit",
            "title": "Approve",
            "style": "positive",
            "data": {
                "kind": "approve_site_edit",
                "approval_id": approval_id,
            },
        },
        {
            "type": "Action.Submit",
            "title": "Reject",
            "style": "destructive",
            "data": {
                "kind": "reject_site_edit",
                "approval_id": approval_id,
            },
        },
    ]
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": actions,
    }


async def send_bot_framework_card(
    activity: dict[str, Any],
    card: dict[str, Any],
    settings: TeamsSettings | None = None,
) -> None:
    """Post an Adaptive Card attachment back to the same Teams channel/conversation
    as the inbound `activity`. Generic — works for any card JSON, not just
    site-approval cards.
    """
    service_url = (activity.get("serviceUrl") or "").rstrip("/")
    conversation = activity.get("conversation") or {}
    conversation_id = conversation.get("id")
    activity_id = activity.get("id")
    if not service_url or not conversation_id or not activity_id:
        raise ValueError(
            "Bot Framework activity is missing serviceUrl, conversation.id, or id"
        )

    token = await get_bot_framework_token(settings)
    reply = {
        "type": "message",
        "from": activity.get("recipient"),
        "recipient": activity.get("from"),
        "conversation": conversation,
        "replyToId": activity_id,
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{service_url}/v3/conversations/{conversation_id}/activities/{activity_id}",
            headers={"Authorization": f"Bearer {token}"},
            json=reply,
        )
        response.raise_for_status()
