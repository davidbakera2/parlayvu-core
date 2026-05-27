import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database import session_scope
from app.models import (
    AgentEvent,
    Client,
    ConversationTurn,
    GeneratedOutput,
    Project,
    SourceAsset,
    TeamsChannelBinding,
)

logger = logging.getLogger("parlayvu.project_memory")


def project_memory_enabled() -> bool:
    return os.getenv("PROJECT_MEMORY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def default_project_id(client_id: str) -> str:
    return f"{client_id}-default"


def _dt(value) -> Optional[str]:
    return value.isoformat() if value else None


def serialize_client(client: Client) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "status": client.status,
        "brand_voice_summary": client.brand_voice_summary,
        "disclosure_rules": client.disclosure_rules or {},
        "channel_preferences": client.channel_preferences or {},
        "created_at": _dt(client.created_at),
        "updated_at": _dt(client.updated_at),
    }


def serialize_project(project: Project, *, include_related: bool = False) -> dict[str, Any]:
    payload = {
        "id": project.id,
        "client_id": project.client_id,
        "name": project.name,
        "status": project.status,
        "objective": project.objective,
        "approval_policy": project.approval_policy or {},
        "metadata": project.metadata_json or {},
        "created_at": _dt(project.created_at),
        "updated_at": _dt(project.updated_at),
    }
    if include_related:
        payload["client"] = serialize_client(project.client)
        payload["source_assets"] = [
            {
                "id": item.id,
                "asset_type": item.asset_type,
                "title": item.title,
                "uri": item.uri,
                "summary": item.summary,
                "metadata": item.metadata_json or {},
                "created_at": _dt(item.created_at),
            }
            for item in project.source_assets
        ]
        payload["generated_outputs"] = [
            {
                "id": item.id,
                "agent_name": item.agent_name,
                "output_type": item.output_type,
                "title": item.title,
                "uri": item.uri,
                "status": item.status,
                "metadata": item.metadata_json or {},
                "created_at": _dt(item.created_at),
            }
            for item in project.generated_outputs
        ]
        payload["approvals"] = [
            {
                "id": item.id,
                "generated_output_id": item.generated_output_id,
                "requested_by_agent": item.requested_by_agent,
                "approver": item.approver,
                "status": item.status,
                "decision_notes": item.decision_notes,
                "created_at": _dt(item.created_at),
            }
            for item in project.approvals
        ]
        payload["agent_events"] = [
            {
                "id": item.id,
                "agent_name": item.agent_name,
                "event_type": item.event_type,
                "channel": item.channel,
                "summary": item.summary,
                "payload": item.payload or {},
                "created_at": _dt(item.created_at),
            }
            for item in project.agent_events
        ]
    return payload


def serialize_teams_channel_binding(binding: TeamsChannelBinding) -> dict[str, Any]:
    return {
        "id": binding.id,
        "team_id": binding.team_id,
        "channel_id": binding.channel_id,
        "channel_name": binding.channel_name,
        "client_id": binding.client_id,
        "project_id": binding.project_id,
        "status": binding.status,
        "metadata": binding.metadata_json or {},
        "created_at": _dt(binding.created_at),
        "updated_at": _dt(binding.updated_at),
    }


def ensure_project_context(
    session: Session,
    *,
    client_id: str,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
    brand_voice_summary: Optional[str] = None,
) -> Project:
    client = session.get(Client, client_id)
    if client is None:
        client = Client(
            id=client_id,
            name=client_id.replace("-", " ").replace("_", " ").title(),
            brand_voice_summary=brand_voice_summary,
        )
        session.add(client)
    elif brand_voice_summary and not client.brand_voice_summary:
        client.brand_voice_summary = brand_voice_summary

    resolved_project_id = project_id or default_project_id(client_id)
    project = session.get(Project, resolved_project_id)
    if project is None:
        project = Project(
            id=resolved_project_id,
            client=client,
            name=project_name or resolved_project_id.replace("-", " ").replace("_", " ").title(),
        )
        session.add(project)
    return project


def record_generated_output(
    *,
    client_id: str,
    agent_name: str,
    output_type: str,
    title: str,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
    brand_voice_summary: Optional[str] = None,
    content: Optional[str] = None,
    uri: Optional[str] = None,
    status: str = "draft",
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    if not project_memory_enabled():
        return None

    try:
        with session_scope() as session:
            project = ensure_project_context(
                session,
                client_id=client_id,
                project_id=project_id,
                project_name=project_name,
                brand_voice_summary=brand_voice_summary,
            )
            output = GeneratedOutput(
                project=project,
                agent_name=agent_name,
                output_type=output_type,
                title=title,
                content=content,
                uri=uri,
                status=status,
                metadata_json=metadata or {},
            )
            session.add(output)
            session.flush()
            return output.id
    except Exception as exc:
        logger.warning("Project memory output write skipped: %s", exc)
        return None


def record_agent_event(
    *,
    agent_name: str,
    event_type: str,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    project_name: Optional[str] = None,
    channel: Optional[str] = None,
    summary: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    if not project_memory_enabled():
        return None

    try:
        with session_scope() as session:
            project = None
            if client_id:
                project = ensure_project_context(
                    session,
                    client_id=client_id,
                    project_id=project_id,
                    project_name=project_name,
                )
            event = AgentEvent(
                project=project,
                client_id=client_id,
                agent_name=agent_name,
                event_type=event_type,
                channel=channel,
                summary=summary,
                payload=payload or {},
            )
            session.add(event)
            session.flush()
            return event.id
    except Exception as exc:
        logger.warning("Project memory event write skipped: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------
# Append-only turn log keyed by (conversation_id, client_id). Backs the Teams
# multi-turn experience so Nathan can say "yes, regenerate variant 3" without
# the user re-explaining what variant 3 is. Replay defaults intentionally
# generous (20 turns, 72h) — David picked the looser end of the spec. Drop
# oldest turns first when the char budget would be exceeded.

CONVERSATION_MAX_TURNS = 20
CONVERSATION_MAX_AGE_HOURS = 72
CONVERSATION_MAX_CHARS = 60_000


def save_conversation_turn(
    *,
    conversation_id: Optional[str],
    role: str,
    content: str,
    client_id: Optional[str] = None,
    surface: str = "teams_chat",
) -> Optional[str]:
    """Append a single turn (user or assistant) to the conversation log.

    No-op when project memory is disabled or conversation_id is empty
    (1:1 DMs without a stable conversation handle skip memory). Returns the
    new row's id on success, None otherwise. Never raises — conversation
    memory is best-effort; Nathan still works without it.
    """
    if not project_memory_enabled():
        return None
    if not conversation_id or not content:
        return None
    if role not in {"user", "assistant"}:
        logger.warning("save_conversation_turn: unexpected role=%r", role)
        return None

    try:
        with session_scope() as session:
            turn = ConversationTurn(
                conversation_id=conversation_id,
                client_id=client_id,
                surface=surface,
                role=role,
                content=content,
            )
            session.add(turn)
            session.flush()
            return turn.id
    except Exception as exc:
        logger.warning("Conversation turn write skipped: %s", exc)
        return None


def load_conversation_history(
    *,
    conversation_id: Optional[str],
    client_id: Optional[str] = None,
    max_turns: int = CONVERSATION_MAX_TURNS,
    max_age_hours: int = CONVERSATION_MAX_AGE_HOURS,
    max_chars: int = CONVERSATION_MAX_CHARS,
) -> list[dict[str, Any]]:
    """Load the recent conversation history for replay into a Nathan call.

    Returns a list of {"role": "...", "content": "..."} dicts in
    chronological order (oldest first), suitable for prepending to a fresh
    user message before calling run_nathan_conversation.

    Three bounds, applied in order:
      1. Max age: ignore turns older than max_age_hours
      2. Max turns: keep only the most recent max_turns
      3. Max chars: if total content exceeds max_chars, drop oldest turns
         until it fits. Newest turns are most relevant; trimming the tail
         keeps the immediate context intact.

    Scoped by conversation_id (and client_id when provided) so two clients
    sharing a Teams tenant can never see each other's history. Returns []
    when project memory is disabled, conversation_id is empty, or no rows
    match — every caller path stays safe.
    """
    if not project_memory_enabled():
        return []
    if not conversation_id:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    try:
        with session_scope() as session:
            query = session.query(ConversationTurn).filter(
                ConversationTurn.conversation_id == conversation_id,
                ConversationTurn.created_at >= cutoff,
            )
            if client_id:
                query = query.filter(ConversationTurn.client_id == client_id)
            # Pull newest-first then reverse — lets us apply the turn cap on
            # the most-recent end before we sort back into chronological order.
            # Materialize as plain dicts INSIDE the session so we don't
            # touch detached SQLAlchemy instances after __exit__ commits/closes.
            recent_rows = (
                query.order_by(ConversationTurn.created_at.desc())
                .limit(max_turns)
                .all()
            )
            turns = [
                {"role": t.role, "content": t.content or ""}
                for t in reversed(recent_rows)  # chronological order
            ]
    except Exception as exc:
        logger.warning("Conversation history read skipped: %s", exc)
        return []

    # Char budget: drop oldest turns until total content fits. Newest turns
    # are the highest-signal context — trimming the tail keeps them intact.
    total_chars = sum(len(t["content"]) for t in turns)
    while turns and total_chars > max_chars:
        dropped = turns.pop(0)
        total_chars -= len(dropped["content"])

    return turns


def reset_conversation_history(
    *,
    conversation_id: Optional[str],
    client_id: Optional[str] = None,
) -> int:
    """Delete all turns for a (conversation_id, client_id) pair.

    Returns the number of rows deleted. No-op (returns 0) when project
    memory is disabled or conversation_id is empty. Never raises.
    """
    if not project_memory_enabled():
        return 0
    if not conversation_id:
        return 0

    try:
        with session_scope() as session:
            query = session.query(ConversationTurn).filter(
                ConversationTurn.conversation_id == conversation_id,
            )
            if client_id:
                query = query.filter(ConversationTurn.client_id == client_id)
            deleted = query.delete(synchronize_session=False)
            return int(deleted or 0)
    except Exception as exc:
        logger.warning("Conversation history reset skipped: %s", exc)
        return 0


def list_clients() -> list[dict[str, Any]]:
    with session_scope() as session:
        clients = session.query(Client).order_by(Client.name.asc()).all()
        return [serialize_client(client) for client in clients]


def list_projects(client_id: Optional[str] = None) -> list[dict[str, Any]]:
    with session_scope() as session:
        query = session.query(Project)
        if client_id:
            query = query.filter(Project.client_id == client_id)
        projects = query.order_by(Project.created_at.desc()).all()
        return [serialize_project(project) for project in projects]


def get_project_context(project_id: str) -> Optional[dict[str, Any]]:
    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            return None
        return serialize_project(project, include_related=True)


def get_teams_channel_binding(*, team_id: Optional[str], channel_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Resolve a Teams team+channel to a (client_id, project_id) binding.

    Two layers, in priority order:
      1. TeamsChannelBinding row in the database (set via /teams/channels/bind
         or a Teams "bind this channel to X" command at runtime).
      2. Static binding declared in any client_artifacts/<id>/config.yaml under
         `teams.team_id` / `teams.channel_id`. Onboarding a new client by
         populating their config.yaml is enough — no bind command needed.

    Layer 1 wins so runtime overrides are still possible. Layer 2 makes
    onboarding-via-config the default and matches the ParlayVU design rule
    that new clients land via config, never code.
    """
    if not channel_id:
        return None
    try:
        with session_scope() as session:
            query = session.query(TeamsChannelBinding).filter(
                TeamsChannelBinding.channel_id == channel_id,
                TeamsChannelBinding.status == "active",
            )
            if team_id:
                query = query.filter(TeamsChannelBinding.team_id == team_id)
            binding = query.one_or_none()
            if binding:
                return serialize_teams_channel_binding(binding)
    except Exception as exc:
        logger.warning("Teams channel binding DB lookup skipped: %s", exc)

    # Fallback: scan every client config for a matching team+channel.
    try:
        from app.client_config import list_clients, load_client_config

        for cid in list_clients():
            try:
                config = load_client_config(cid)
            except Exception:
                continue
            if (
                config.teams.channel_id == channel_id
                and (not team_id or config.teams.team_id == team_id)
            ):
                # Project convention: the channel's "default" project is the
                # client's website project. Callers that need a different
                # project for this channel can override via the DB.
                return {
                    "team_id": config.teams.team_id,
                    "channel_id": config.teams.channel_id,
                    "channel_name": None,
                    "client_id": config.client_id,
                    "project_id": f"{config.client_id}-website",
                    "project_name": f"{config.display_name} — Website",
                    "bound_by": "config.yaml",
                    "status": "active",
                    "source": "client_config",
                }
    except Exception as exc:
        logger.warning("Teams channel binding config fallback skipped: %s", exc)
    return None


def bind_teams_channel(
    *,
    team_id: str,
    channel_id: str,
    channel_name: Optional[str],
    client_id: str,
    project_id: str,
    project_name: Optional[str] = None,
    bound_by: Optional[str] = None,
) -> dict[str, Any]:
    with session_scope() as session:
        project = ensure_project_context(
            session,
            client_id=client_id,
            project_id=project_id,
            project_name=project_name,
        )
        binding = (
            session.query(TeamsChannelBinding)
            .filter(TeamsChannelBinding.channel_id == channel_id)
            .one_or_none()
        )
        if binding is None:
            binding = TeamsChannelBinding(
                team_id=team_id,
                channel_id=channel_id,
                channel_name=channel_name,
                client_id=client_id,
                project=project,
                metadata_json={},
            )
        else:
            binding.team_id = team_id
            binding.channel_name = channel_name
            binding.client_id = client_id
            binding.project = project
            binding.status = "active"
        binding.metadata_json = {
            **(binding.metadata_json or {}),
            "bound_by": bound_by,
        }
        session.add(binding)
        session.flush()
        return serialize_teams_channel_binding(binding)
