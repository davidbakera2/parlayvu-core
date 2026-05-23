# parlayvu-core/app/agents/registry.py
import logging
from typing import Any, Callable, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from app.agents.prompts import (
    ALEX_PROMPT, AVA_PROMPT, BLAKE_PROMPT, CASEY_PROMPT,
    CODEY_PROMPT, DYLAN_PROMPT, JORDAN_PROMPT, MICHAEL_PROMPT,
    MORGAN_PROMPT, NORA_PROMPT, RILEY_PROMPT, TAYLOR_PROMPT,
)
from app.agents.router import RouteDecision

logger = logging.getLogger("parlayvu.registry")

SPECIALIST_PROMPTS: Dict[str, str] = {
    "alex": ALEX_PROMPT, "ava": AVA_PROMPT, "blake": BLAKE_PROMPT,
    "casey": CASEY_PROMPT, "codey": CODEY_PROMPT, "dylan": DYLAN_PROMPT,
    "jordan": JORDAN_PROMPT, "michael": MICHAEL_PROMPT, "morgan": MORGAN_PROMPT,
    "nora": NORA_PROMPT, "riley": RILEY_PROMPT, "taylor": TAYLOR_PROMPT,
}

_registry: Dict[str, Callable] = {}
_bound_llm: Optional[BaseChatModel] = None
_model_map: Dict[str, BaseChatModel] = {}


def get_bound_llm() -> Optional[BaseChatModel]:
    return _bound_llm


def get_agent_llm(name: str) -> Optional[BaseChatModel]:
    """Return the LLM assigned to a specific agent, falling back to default then bound LLM."""
    return _model_map.get(name) or _model_map.get("default") or _bound_llm


def _payload_from_decision(decision: Any) -> Dict[str, Any]:
    if isinstance(decision, RouteDecision):
        return decision.payload
    if isinstance(decision, dict):
        return decision.get("payload") or {}
    return getattr(decision, "payload", {}) or {}


def _task_from_state(state: dict) -> str:
    payload = _payload_from_decision(state.get("route_decision"))
    task = payload.get("task") or payload.get("content_to_repurpose") or ""
    if task:
        return str(task)

    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
        if isinstance(msg, dict) and msg.get("content"):
            return str(msg["content"])
        content = getattr(msg, "content", None)
        if content:
            return str(content)
    return ""


def _site_name_from_payload(payload: Dict[str, Any], task: str) -> str:
    explicit_name = payload.get("site_name") or payload.get("page_name")
    if explicit_name:
        return str(explicit_name)

    source_content = str(payload.get("source_content") or "")
    lowered = source_content.lower()
    if "ai content repurposing" in lowered or "content repurposing" in lowered:
        return "ai-content-repurposing"

    lowered_task = task.lower()
    if "ai content repurposing" in lowered_task or "content repurposing" in lowered_task:
        return "ai-content-repurposing"

    return "marketing-landing"


def create_dylan_node(
    generate_astro_site_tool: BaseTool,
    scaffold_client_site_tool: Optional[BaseTool] = None,
) -> Callable:
    def node(state: dict) -> dict:
        decision = state.get("route_decision")
        payload = _payload_from_decision(decision)
        task = _task_from_state(state)
        client_id = str(payload.get("client_id") or state.get("client_id") or "default-client")
        brand_voice = str(
            payload.get("brand_voice_summary")
            or payload.get("brand_voice")
            or state.get("brand_voice_summary")
            or "Professional, modern, and conversion-focused"
        )
        site_name = _site_name_from_payload(payload, task)
        content = str(
            payload.get("source_content")
            or payload.get("content")
            or payload.get("task")
            or task
        )

        use_client_playbook = bool(
            payload.get("parlayvu_client_site")
            or (payload.get("domain") and (payload.get("contact_to") or payload.get("contact_from")))
        )

        if use_client_playbook and scaffold_client_site_tool is not None:
            domain = str(payload.get("domain") or "")
            contact_to = str(payload.get("contact_to") or payload.get("contact_email") or "")
            contact_from = str(
                payload.get("contact_from")
                or payload.get("from_email")
                or (f"contact@{domain}" if domain else "")
            )
            logger.info(
                "Dylan scaffolding ParlayVU client site | slug=%s domain=%s",
                client_id,
                domain,
            )
            tool_output = scaffold_client_site_tool.invoke(
                {
                    "client_slug": payload.get("client_slug") or client_id,
                    "domain": domain,
                    "contact_to": contact_to,
                    "contact_from": contact_from,
                    "brand_name": payload.get("brand_name") or payload.get("brand"),
                    "pages_project": payload.get("pages_project"),
                    "deploy": bool(payload.get("deploy")),
                }
            )
        else:
            logger.info("Dylan generating local Astro site | client_id=%s site_name=%s", client_id, site_name)
            tool_output = generate_astro_site_tool.invoke(
                {
                    "content": content,
                    "site_name": site_name,
                    "client_id": client_id,
                    "brand_voice": brand_voice,
                }
            )
        message = tool_output.get("message", "Dylan generated an Astro site locally.")
        response = AIMessage(content=message)
        logger.info("Dylan generated local Astro site | path=%s", tool_output.get("site_path"))

        return {
            "messages": state.get("messages", []) + [response],
            "client_id": state.get("client_id"),
            "project_id": state.get("project_id"),
            "project_context": state.get("project_context"),
            "brand_voice_summary": state.get("brand_voice_summary"),
            "route_decision": decision,
            "final_output": {
                "agent": "dylan",
                "content": message,
                "tool_output": tool_output,
            },
        }

    return node


def create_specialist_node(
    name: str,
    system_prompt: str,
    llm: BaseChatModel,
) -> Callable:
    def node(state: dict) -> dict:
        task = _task_from_state(state)
        decision = state.get("route_decision")

        messages = [SystemMessage(content=system_prompt), HumanMessage(content=task or "No task provided.")]
        response = llm.invoke(messages)
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(response))

        return {
            "messages": state.get("messages", []) + [response],
            "client_id": state.get("client_id"),
            "project_id": state.get("project_id"),
            "project_context": state.get("project_context"),
            "brand_voice_summary": state.get("brand_voice_summary"),
            "route_decision": decision,
            "final_output": {"agent": name, "content": response.content},
        }

    return node


def initialize_registry(llm_or_map) -> Dict[str, Callable]:
    """Initialize the agent registry.

    Accepts either a single BaseChatModel (all agents share it) or a dict
    mapping agent names to individual models.  The Nathan entry in the map
    is stored as _bound_llm so graph.py's get_bound_llm() returns the right
    model for routing.
    """
    global _registry, _bound_llm, _model_map

    if isinstance(llm_or_map, dict):
        model_map = llm_or_map
        nathan_llm = model_map.get("nathan") or next(iter(model_map.values()))
    else:
        nathan_llm = llm_or_map
        model_map = {"default": llm_or_map}

    _model_map = model_map

    if _registry and _bound_llm is nathan_llm:
        return _registry

    _bound_llm = nathan_llm
    _registry = {}

    _registry["nathan"] = lambda state: state

    for name, prompt in SPECIALIST_PROMPTS.items():
        agent_llm = model_map.get(name) or model_map.get("default") or nathan_llm

        if name == "dylan":
            try:
                from app.agents.tools.dylan_tools import (
                    generate_astro_site,
                    scaffold_parlayvu_client_site,
                )
                _registry[name] = create_dylan_node(
                    generate_astro_site,
                    scaffold_parlayvu_client_site,
                )
                logger.info("Dylan local generator loaded")
                continue
            except Exception as e:
                logger.warning("Dylan tools load failed: %s", e)

        _registry[name] = create_specialist_node(name, prompt, agent_llm)

    logger.info("Registry initialized with %s agents", len(_registry))
    return _registry


def get_registry(llm: Optional[BaseChatModel] = None) -> Dict[str, Any]:
    if llm is None:
        if _bound_llm is None:
            raise RuntimeError("Registry not initialized")
        return _registry
    return initialize_registry(llm)