# parlayvu-core/app/agents/router.py
from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel, Field

class AgentName(str, Enum):
    NATHAN = "nathan"
    ALEX = "alex"
    AVA = "ava"
    BLAKE = "blake"
    CASEY = "casey"
    CODEY = "codey"
    DYLAN = "dylan"
    JORDAN = "jordan"
    MICHAEL = "michael"
    MORGAN = "morgan"
    NORA = "nora"
    RILEY = "riley"
    TAYLOR = "taylor"

class RouteDecision(BaseModel):
    """Nathan's structured routing decision used by the entire graph."""
    target_agent: AgentName = Field(
        ..., description="Exact agent name (lowercase, must match registry key)"
    )
    reason: str = Field(
        ..., min_length=10, max_length=300,
        description="Clear 1-2 sentence reasoning for LangSmith + debugging"
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="All data the target agent needs (client_id, brand_voice, content, etc.)"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="0.0-1.0 confidence score"
    )
    needs_human_review: bool = Field(
        False, description="If true, surface to client in Teams/Copilot"
    )

def enrich_default_payload(decision: RouteDecision) -> RouteDecision:
    """Lightweight defaults per agent."""
    if decision.target_agent == AgentName.DYLAN and "site_type" not in decision.payload:
        decision.payload["site_type"] = "marketing_landing_page"
    if decision.target_agent == AgentName.ALEX and "style_direction" not in decision.payload:
        decision.payload["style_direction"] = "clean, professional, high-contrast"
    # Add more agent-specific defaults here later
    return decision