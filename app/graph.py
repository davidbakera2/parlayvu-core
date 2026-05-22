# parlayvu-core/app/graph.py
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from app.agents.registry import get_bound_llm, get_registry
from app.agents.nathan_router import route_message
from app.agents.router import RouteDecision

logger = logging.getLogger("parlayvu.graph")

SPECIALIST_NAMES = [
    "alex", "ava", "blake", "casey", "codey", "dylan",
    "jordan", "michael", "morgan", "nora", "riley", "taylor",
]


class ParlayVuState(BaseModel):
    messages: list = Field(default_factory=list)
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    project_context: Optional[Dict[str, Any]] = None
    brand_voice_summary: Optional[str] = None
    route_decision: Optional[RouteDecision] = None
    final_output: Optional[Dict[str, Any]] = None


def _latest_human_message(state: ParlayVuState) -> Optional[str]:
    for message in reversed(state.messages):
        if isinstance(message, HumanMessage):
            return message.content
        content = getattr(message, "content", None)
        if content:
            return str(content)
    return None


def nathan_node(state: ParlayVuState) -> ParlayVuState:
    if state.route_decision:
        return state

    message = _latest_human_message(state)
    if not message:
        state.final_output = {"error": "Nathan could not route because no user message was provided."}
        return state

    llm = get_bound_llm()
    if llm is None:
        state.final_output = {"error": "Agent registry is not initialized; Nathan cannot route this request."}
        return state

    try:
        state.route_decision = route_message(message, llm, client_id=state.client_id)
    except Exception as exc:
        logger.exception("Nathan failed to route request")
        state.final_output = {
            "agent": "nathan",
            "error": "Nathan failed to route this request.",
            "detail": str(exc),
        }
        return state

    if state.brand_voice_summary:
        state.route_decision.payload["brand_voice_summary"] = state.brand_voice_summary
    if state.project_id:
        state.route_decision.payload["project_id"] = state.project_id
    if state.project_context:
        state.route_decision.payload["project_context"] = state.project_context
    logger.info("Nathan routed request to %s", state.route_decision.target_agent.value)
    return state


def specialist_node(agent_name: str):
    def node(state: ParlayVuState) -> ParlayVuState:
        registry = get_registry()
        agent_func = registry.get(agent_name)
        
        if not agent_func:
            state.final_output = {"error": f"Agent {agent_name} not found"}
            return state

        try:
            result = agent_func(
                {
                    "messages": state.messages,
                    "client_id": state.client_id,
                    "project_id": state.project_id,
                    "project_context": state.project_context,
                    "brand_voice_summary": state.brand_voice_summary,
                    "route_decision": state.route_decision,
                    "final_output": state.final_output,
                }
            )
        except Exception as exc:
            logger.exception("Agent node failed | agent=%s", agent_name)
            state.final_output = {
                "agent": agent_name,
                "error": f"Agent {agent_name} failed while executing.",
                "detail": str(exc),
            }
            return state

        if not isinstance(result, dict):
            state.final_output = {"error": f"Agent {agent_name} returned an invalid result."}
            return state
        
        state.messages = result.get("messages", state.messages)
        state.client_id = result.get("client_id", state.client_id)
        state.project_id = result.get("project_id", state.project_id)
        state.project_context = result.get("project_context", state.project_context)
        state.brand_voice_summary = result.get("brand_voice_summary", state.brand_voice_summary)
        state.route_decision = result.get("route_decision", state.route_decision)
        state.final_output = result.get("final_output", state.final_output)
        return state
    return node


def route_from_nathan(state: ParlayVuState) -> str:
    if not state.route_decision:
        return END

    target_agent = state.route_decision.target_agent.value
    if target_agent not in SPECIALIST_NAMES:
        return END

    return f"{target_agent}_node"


def build_parlayvu_graph():
    workflow = StateGraph(ParlayVuState)

    workflow.add_node("nathan_node", nathan_node)

    for name in SPECIALIST_NAMES:
        workflow.add_node(f"{name}_node", specialist_node(name))

    workflow.set_entry_point("nathan_node")

    conditional_map = {f"{name}_node": f"{name}_node" for name in SPECIALIST_NAMES}
    conditional_map[END] = END
    workflow.add_conditional_edges("nathan_node", route_from_nathan, conditional_map)

    for name in SPECIALIST_NAMES:
        workflow.add_edge(f"{name}_node", END)

    return workflow.compile()


# Global graph
parlayvu_graph = None

def get_graph():
    global parlayvu_graph
    if parlayvu_graph is None:
        parlayvu_graph = build_parlayvu_graph()
    return parlayvu_graph