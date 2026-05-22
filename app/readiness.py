import os
from typing import Any

from app.heygen import heygen_status
from app.microsoft365 import mailbox_status
from app.project_memory import project_memory_enabled
from app.settings import Settings, get_settings
from app.teams import teams_status


def llm_readiness(settings: Settings | None = None) -> dict[str, Any]:
    active_settings = settings or get_settings()
    if active_settings.llm_provider == "openai":
        configured = bool(active_settings.openai_api_key)
    elif active_settings.llm_provider == "groq":
        configured = bool(active_settings.groq_api_key)
    else:
        configured = bool(active_settings.xai_api_key)

    return {
        "configured": configured,
        "provider": active_settings.llm_provider,
        "model": active_settings.active_model,
    }


def database_readiness() -> dict[str, Any]:
    return {
        "configured": bool(os.getenv("DATABASE_URL")),
        "project_memory_enabled": project_memory_enabled(),
    }


def approval_readiness() -> dict[str, Any]:
    database = database_readiness()
    return {
        "configured": database["configured"],
        "requires_project_memory": True,
        "decision_states": ["approved", "rejected", "changes_requested", "cancelled"],
        "gated_actions": ["deploy_site", "send_email"],
    }


def overall_status(checks: dict[str, dict[str, Any]]) -> str:
    required = ["llm", "database", "approvals"]
    if all(checks[name].get("configured") for name in required):
        return "ready"
    return "needs_configuration"


def readiness_report(settings: Settings | None = None) -> dict[str, Any]:
    checks = {
        "llm": llm_readiness(settings),
        "database": database_readiness(),
        "m365": mailbox_status(),
        "heygen": heygen_status(),
        "teams": teams_status(),
        "approvals": approval_readiness(),
    }
    return {
        "status": overall_status(checks),
        "checks": checks,
    }
