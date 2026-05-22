import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

AGENT_AVATAR_ENV = {
    "nathan": "HEYGEN_NATHAN_AVATAR_ID",
    "alex": "HEYGEN_ALEX_AVATAR_ID",
    "ava": "HEYGEN_AVA_AVATAR_ID",
    "blake": "HEYGEN_BLAKE_AVATAR_ID",
    "casey": "HEYGEN_CASEY_AVATAR_ID",
    "codey": "HEYGEN_CODEY_AVATAR_ID",
    "dylan": "HEYGEN_DYLAN_AVATAR_ID",
    "jordan": "HEYGEN_JORDAN_AVATAR_ID",
    "michael": "HEYGEN_MICHAEL_AVATAR_ID",
    "morgan": "HEYGEN_MORGAN_AVATAR_ID",
    "nora": "HEYGEN_NORA_AVATAR_ID",
    "riley": "HEYGEN_RILEY_AVATAR_ID",
    "taylor": "HEYGEN_TAYLOR_AVATAR_ID",
}

RAMAIR_CLIENT_ID = "ramair"
RAMAIR_PROJECT_ID = "ramair-straight-from-the-hart"
RAMAIR_LIVE_MEETING_NOTES_FOLDER = "03_Deliverables/Meeting Notes"


@dataclass(frozen=True)
class HeyGenSettings:
    api_key: str
    base_url: str
    webhook_secret: str
    agent_avatars: dict[str, str]

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def get_heygen_settings() -> HeyGenSettings:
    return HeyGenSettings(
        api_key=os.getenv("HEYGEN_API_KEY", ""),
        base_url=os.getenv("HEYGEN_BASE_URL", "https://api.heygen.com"),
        webhook_secret=os.getenv("HEYGEN_WEBHOOK_SECRET", ""),
        agent_avatars={
            agent: avatar_id
            for agent, env_name in AGENT_AVATAR_ENV.items()
            if (avatar_id := os.getenv(env_name, "").strip())
        },
    )


def heygen_status(settings: Optional[HeyGenSettings] = None) -> dict[str, Any]:
    active_settings = settings or get_heygen_settings()
    return {
        "configured": active_settings.configured,
        "base_url": active_settings.base_url,
        "webhook_secret_configured": bool(active_settings.webhook_secret),
        "agents": {
            agent: {
                "configured": agent in active_settings.agent_avatars,
                "avatar_id": active_settings.agent_avatars.get(agent),
            }
            for agent in AGENT_AVATAR_ENV
        },
    }


def avatar_for_agent(agent_name: str, settings: Optional[HeyGenSettings] = None) -> str:
    active_settings = settings or get_heygen_settings()
    avatar_id = active_settings.agent_avatars.get(agent_name.lower())
    if not avatar_id:
        raise ValueError(f"No HeyGen avatar is configured for agent: {agent_name}")
    return avatar_id


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    provided = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, provided)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_live_meeting_session(
    *,
    agent_name: str,
    avatar_id: str,
    project_context: dict[str, Any],
    meeting_title: str,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    heygen_session_id: Optional[str] = None,
    teams_meeting_id: Optional[str] = None,
    teams_meeting_link: Optional[str] = None,
    expected_attendees: Optional[list[str]] = None,
    operator_notes: Optional[str] = None,
) -> dict[str, Any]:
    client = project_context.get("client") or {}
    resolved_client_id = client_id or project_context.get("client_id") or RAMAIR_CLIENT_ID
    resolved_session_id = session_id or f"live-{uuid4()}"
    return {
        "session_id": resolved_session_id,
        "status": "active",
        "agent_name": agent_name.lower(),
        "avatar_id": avatar_id,
        "client_id": resolved_client_id,
        "client_name": client.get("name") or resolved_client_id,
        "project_id": project_context.get("id"),
        "project_name": project_context.get("name"),
        "meeting_title": meeting_title.strip() or "RamAir LiveAvatar meeting",
        "expected_attendees": expected_attendees or [],
        "heygen_session_id": heygen_session_id,
        "teams_meeting_id": teams_meeting_id,
        "teams_meeting_link": teams_meeting_link,
        "started_at": _now_iso(),
        "ended_at": None,
        "operator_notes": operator_notes,
        "provider": {
            "name": "heygen",
            "mode": "operator-controlled-live-avatar",
            "callback_shape": "POST /heygen/live-meetings/{session_id}/question",
        },
    }


def _display_items(items: list[dict[str, Any]], *, fallback_key: str = "id", limit: int = 3) -> list[str]:
    labels = []
    for item in items[:limit]:
        label = item.get("title") or item.get("name") or item.get("summary") or item.get(fallback_key)
        if label:
            labels.append(str(label))
    return labels


def build_live_project_answer(
    *,
    agent_name: str,
    question: str,
    project_context: dict[str, Any],
) -> dict[str, Any]:
    client = project_context.get("client") or {}
    approvals = project_context.get("approvals") or []
    pending_approvals = [approval for approval in approvals if approval.get("status") == "pending"]
    source_assets = project_context.get("source_assets") or []
    generated_outputs = project_context.get("generated_outputs") or []
    project_name = project_context.get("name") or project_context.get("id")
    client_name = client.get("name") or project_context.get("client_id")
    normalized_question = question.lower()
    asks_for_metrics = any(
        term in normalized_question
        for term in ["metric", "metrics", "kpi", "performance", "results", "roi", "conversion", "engagement"]
    )
    asks_for_approval = any(term in normalized_question for term in ["approval", "approved", "pending", "sign off"])
    asks_for_status = any(term in normalized_question for term in ["status", "where are we", "progress", "ready"])

    answer_parts = [
        f"I am {agent_name.title()} from ParlayVU, grounded in the stored {client_name} project memory.",
    ]

    if asks_for_status:
        status = project_context.get("status") or "active"
        answer_parts.append(f"For {project_name}, the current stored status is {status}.")
    else:
        answer_parts.append(f"This answer is tied to {project_name}.")

    objective = project_context.get("objective")
    if objective:
        answer_parts.append(f"The objective on record is: {objective}")

    if source_assets:
        labels = _display_items(source_assets)
        source_text = f"{len(source_assets)} source asset(s)"
        if labels:
            source_text += f", including {', '.join(labels)}"
        answer_parts.append(f"I can see {source_text}.")
    if generated_outputs:
        labels = _display_items(generated_outputs)
        output_text = f"{len(generated_outputs)} generated output(s)"
        if labels:
            output_text += f", including {', '.join(labels)}"
        answer_parts.append(f"Project memory also has {output_text}.")
    if asks_for_metrics:
        answer_parts.append(
            "I do not have approved live performance metrics in memory yet, so I should not quote results or ROI."
        )
    if asks_for_approval and not pending_approvals:
        answer_parts.append("I do not see pending approvals in the stored project memory.")
    if pending_approvals:
        answer_parts.append(
            f"{len(pending_approvals)} item(s) are still pending approval, so I will avoid presenting them as final."
        )
    answer_parts.append(
        "If you need a new claim, metric, publishing decision, or client-facing commitment, I will say what is missing and route it for human review."
    )
    grounded_sources = {
        "source_assets": _display_items(source_assets),
        "generated_outputs": _display_items(generated_outputs),
        "pending_approvals": _display_items(pending_approvals),
    }

    return {
        "answer": " ".join(answer_parts),
        "question": question,
        "needs_human_review": bool(pending_approvals or asks_for_metrics),
        "grounding": {
            "project_id": project_context.get("id"),
            "client_id": project_context.get("client_id"),
            "project_status": project_context.get("status"),
            "source_asset_count": len(source_assets),
            "generated_output_count": len(generated_outputs),
            "pending_approval_count": len(pending_approvals),
            "grounded_sources": grounded_sources,
            "unsupported_metric_requested": asks_for_metrics,
        },
    }
