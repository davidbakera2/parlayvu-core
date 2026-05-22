# parlayvu-core/app/agents/nathan_router.py
"""Nathan structured routing — shared by FastAPI and LangGraph."""

import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from app.agents.prompts import NATHAN_SYSTEM_PROMPT
from app.agents.router import RouteDecision, enrich_default_payload

logger = logging.getLogger("parlayvu.nathan")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
def route_message(message: str, llm: BaseChatModel, client_id: Optional[str] = None) -> RouteDecision:
    """Return a validated RouteDecision with retry on transient LLM failures."""
    structured_llm = llm.with_structured_output(RouteDecision)

    try:
        decision = structured_llm.invoke(
            [
                SystemMessage(content=NATHAN_SYSTEM_PROMPT),
                HumanMessage(content=message),
            ]
        )
    except Exception:
        logger.exception("Structured output failed; retrying via JSON parser fallback")
        from langchain_core.output_parsers import PydanticOutputParser

        parser = PydanticOutputParser(pydantic_object=RouteDecision)
        raw = llm.invoke(
            [
                SystemMessage(
                    content=NATHAN_SYSTEM_PROMPT + "\n\n" + parser.get_format_instructions()
                ),
                HumanMessage(content=message),
            ]
        )
        decision = parser.parse(raw.content)

    if isinstance(decision, dict):
        decision = RouteDecision.model_validate(decision)

    decision.payload["task"] = decision.payload.get("task") or message
    if client_id:
        decision.payload["client_id"] = client_id

    decision = enrich_default_payload(decision)
    logger.info(
        "Route decision | target=%s confidence=%.2f review=%s",
        decision.target_agent.value,
        decision.confidence,
        decision.needs_human_review,
    )
    return decision
