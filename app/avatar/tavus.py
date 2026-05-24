"""
Tavus avatar provider — configuration and status.

ParlayVU's chosen avatar provider as of Phase 2 cleanup. The integration model:

  Tavus persona  ──(GET /v1/models, POST /v1/chat/completions)──>  parlayvu-api

So the Python app's job is to be a good OpenAI-compatible LLM backend for Tavus,
not to drive the avatar. Configuration of which persona uses which custom LLM
happens in the Tavus dashboard or via scripts/Update-NathanPersonaLLM.ps1.

When we need to programmatically start/stop Tavus conversations from Python
(e.g., automated meeting join), add a TavusClient class here. Until then this
module just centralizes config reading.
"""

import os
from dataclasses import dataclass
from typing import Any


# Per-agent replica overrides. Adding a new agent's avatar is one entry here
# plus one env var. The default is TAVUS_REPLICA_ID which is shared.
AGENT_REPLICA_ENV = {
    "nathan": "TAVUS_REPLICA_ID_NATHAN",
    # Future agents add lines here. Keep alphabetical.
}


@dataclass(frozen=True)
class TavusConfig:
    api_key: str
    persona_id: str
    default_replica_id: str
    agent_replicas: dict[str, str]

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.persona_id)


def get_tavus_config() -> TavusConfig:
    return TavusConfig(
        api_key=os.getenv("TAVUS_API_KEY", ""),
        persona_id=os.getenv("TAVUS_PERSONA_ID", ""),
        default_replica_id=os.getenv("TAVUS_REPLICA_ID", ""),
        agent_replicas={
            agent: replica_id
            for agent, env_name in AGENT_REPLICA_ENV.items()
            if (replica_id := os.getenv(env_name, "").strip())
        },
    )


def replica_for_agent(agent_name: str, config: TavusConfig | None = None) -> str:
    """Resolve which Tavus replica the named agent uses. Falls back to default."""
    cfg = config or get_tavus_config()
    return cfg.agent_replicas.get(agent_name.lower()) or cfg.default_replica_id


def tavus_status(config: TavusConfig | None = None) -> dict[str, Any]:
    """Shape used by /readiness."""
    cfg = config or get_tavus_config()
    return {
        "provider": "tavus",
        "configured": cfg.configured,
        "persona_id_configured": bool(cfg.persona_id),
        "default_replica_id_configured": bool(cfg.default_replica_id),
        "agent_replicas": {
            agent: {"configured": agent in cfg.agent_replicas}
            for agent in AGENT_REPLICA_ENV
        },
        "custom_llm_endpoint": "POST /v1/chat/completions",
        "models_endpoint": "GET /v1/models",
    }
