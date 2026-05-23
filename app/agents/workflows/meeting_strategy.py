import json
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

logger = logging.getLogger("parlayvu.meeting_strategy")

BLAKE_ANALYSIS_PROMPT = """You are Blake Quinn, Intelligence & Insights specialist at ParlayVU.ai.

Analyze the meeting transcript and return ONLY valid JSON matching this schema exactly — no markdown, no extra text:

{
  "meeting_summary": "2-3 paragraph narrative summary",
  "key_themes": ["theme1", "theme2"],
  "decisions_made": ["decision1", "decision2"],
  "action_items": [
    {"item": "description", "owner": "person or role", "priority": "high|medium|low"}
  ],
  "open_questions": ["question1", "question2"],
  "strategic_opportunities": ["opportunity1", "opportunity2"]
}

Be specific and evidence-based. Only include what was explicitly discussed or clearly implied in the transcript."""

NATHAN_STRATEGY_PROMPT = """You are Nathan Ellis, Lead Orchestrator at ParlayVU.ai.

Based on the meeting analysis provided, devise a clear implementation strategy and operational plan.
Use these exact section headers:

## Executive Summary
[1-2 paragraph high-level summary of strategic direction]

## Implementation Strategy
[3-5 paragraphs covering the strategic approach, rationale, and key initiatives]

## Prioritized Next Steps
[Numbered list — each step: what, who, and when]
1. [Step] — Owner: [name/role] — Timeline: [timeframe]

## Risks & Mitigations
- Risk: [description] → Mitigation: [approach]

## Agent Assignments
- [Agent name]: [specific task and rationale]

Be concrete and actionable. Reference specific decisions and opportunities from the analysis."""


class MeetingStrategyState(BaseModel):
    transcript: str
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    meeting_title: str = "Meeting"
    project_context: Optional[dict] = None
    blake_analysis: Optional[dict] = None
    nathan_strategy: Optional[str] = None
    error: Optional[str] = None


def _llms():
    from app.agents.registry import get_agent_llm
    return get_agent_llm("blake"), get_agent_llm("nathan")


def blake_node(state: MeetingStrategyState) -> dict:
    blake_llm, _ = _llms()

    context_block = ""
    if state.project_context:
        context_block = f"\nProject context:\n{json.dumps(state.project_context, default=str)[:2000]}\n"

    try:
        response = blake_llm.invoke([
            SystemMessage(content=BLAKE_ANALYSIS_PROMPT),
            HumanMessage(content=f"{context_block}\nTranscript:\n{state.transcript}"),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.lower().startswith("json"):
                raw = raw[4:]
        analysis = json.loads(raw.strip())
    except json.JSONDecodeError:
        logger.warning("Blake returned non-JSON — using raw text as summary")
        analysis = {
            "meeting_summary": response.content,
            "key_themes": [],
            "decisions_made": [],
            "action_items": [],
            "open_questions": [],
            "strategic_opportunities": [],
        }
    except Exception as exc:
        logger.exception("Blake analysis node failed")
        return {"error": f"Blake analysis failed: {exc}"}

    logger.info(
        "Blake analysis complete | themes=%d actions=%d opportunities=%d",
        len(analysis.get("key_themes", [])),
        len(analysis.get("action_items", [])),
        len(analysis.get("strategic_opportunities", [])),
    )
    return {"blake_analysis": analysis}


def nathan_node(state: MeetingStrategyState) -> dict:
    if state.error:
        return {}

    _, nathan_llm = _llms()

    analysis_text = json.dumps(state.blake_analysis, indent=2, default=str) if state.blake_analysis else "No analysis available."
    context_block = ""
    if state.project_context:
        context_block = f"\nProject context:\n{json.dumps(state.project_context, default=str)[:2000]}\n"

    try:
        response = nathan_llm.invoke([
            SystemMessage(content=NATHAN_STRATEGY_PROMPT),
            HumanMessage(content=f"Meeting: {state.meeting_title}{context_block}\n\nMeeting Analysis:\n{analysis_text}"),
        ])
        strategy = response.content.strip()
    except Exception as exc:
        logger.exception("Nathan strategy node failed")
        return {"error": f"Nathan strategy failed: {exc}"}

    logger.info("Nathan strategy complete | chars=%d", len(strategy))
    return {"nathan_strategy": strategy}


_graph = None


def get_strategy_graph():
    global _graph
    if _graph is None:
        workflow = StateGraph(MeetingStrategyState)
        workflow.add_node("blake", blake_node)
        workflow.add_node("nathan", nathan_node)
        workflow.set_entry_point("blake")
        workflow.add_edge("blake", "nathan")
        workflow.add_edge("nathan", END)
        _graph = workflow.compile()
    return _graph


async def run_meeting_strategy(
    *,
    transcript: str,
    project_id: Optional[str] = None,
    client_id: Optional[str] = None,
    meeting_title: str = "Meeting",
    project_context: Optional[dict] = None,
) -> dict:
    graph = get_strategy_graph()
    initial = MeetingStrategyState(
        transcript=transcript,
        project_id=project_id,
        client_id=client_id,
        meeting_title=meeting_title,
        project_context=project_context,
    )
    result = await graph.ainvoke(initial)
    return result if isinstance(result, dict) else result.model_dump()
