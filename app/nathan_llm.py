# app/nathan_llm.py
"""
Nathan's conversational intelligence — OpenAI-compatible LLM endpoint.

Tavus CVI supports a "custom LLM" feature where you configure the persona to
call YOUR endpoint (must follow OpenAI chat completions format) instead of
Tavus's built-in model. This gives Nathan:

  - Claude Opus 4.7 as his brain
  - Full tool use: web search, URL fetch (LinkedIn/social/sites), Teams files, project context
  - Grounded project knowledge from ParlayVU memory
  - Anti-hallucination rules enforced at every response

HOW IT WORKS:
  1. Nathan's Tavus persona has custom_llm.base_url pointing to this FastAPI app
  2. When someone speaks in the Teams meeting, Tavus transcribes it
  3. Tavus POSTs the conversation history to POST /v1/chat/completions
  4. This module runs Claude Opus 4.7 with Nathan's system prompt + tools
  5. Claude calls tools (web search, etc.) as needed in a loop
  6. We return the final text response in OpenAI format
  7. Tavus makes Nathan's avatar speak the response

SETUP:
  See scripts/Update-NathanPersonaLLM.ps1 to configure the Tavus persona.

Environment variables:
  ANTHROPIC_API_KEY        — already set (required)
  TAVILY_API_KEY           — get free key at https://tavily.com (web search)
  NATHAN_LLM_API_KEY       — optional bearer token Tavus will send us for auth
  NATHAN_DEFAULT_CLIENT_ID — default client context injected if not in messages (e.g. "ramair")
  NATHAN_DEFAULT_PROJECT_ID — default project context
"""

import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator

import anthropic

from app.tools.web_tools import fetch_url, web_search
from app.tools.teams_files_tool import list_teams_files, read_teams_file
from app.tools.project_tools import get_project_context

logger = logging.getLogger("parlayvu.nathan_llm")

# ── Tool definitions (Anthropic format) ───────────────────────────────────────

NATHAN_TOOLS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "Search the web for current information. Use for market research, "
            "competitor analysis, industry benchmarks, campaign performance data, "
            "finding a company's recent news, or any real-time information you "
            "don't have in your context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A specific, well-formed search query.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Fetch and read the content of any public URL as clean text. "
            "Use for: LinkedIn profiles (pass the full linkedin.com/in/name URL), "
            "company websites, social media pages, news articles, competitor landing pages, "
            "industry publications, or any publicly accessible webpage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch, e.g. https://www.linkedin.com/in/johndoe",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "list_teams_files",
        "description": (
            "List files available in a Microsoft Teams channel. "
            "Use to discover what project documents, briefs, strategies, "
            "or client materials are available before reading a specific file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "string",
                    "description": "The Teams group/team ID (GUID).",
                },
                "channel_id": {
                    "type": "string",
                    "description": "The Teams channel ID.",
                },
            },
            "required": ["team_id", "channel_id"],
        },
    },
    {
        "name": "read_teams_file",
        "description": (
            "Read the content of a specific file in Microsoft Teams. "
            "Works with Word documents, PowerPoint, Excel, PDFs, and text files. "
            "Use list_teams_files first to get the file ID."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "drive_item_id": {
                    "type": "string",
                    "description": "The file's Graph item ID (from list_teams_files).",
                },
                "drive_id": {
                    "type": "string",
                    "description": "Optional SharePoint drive ID for faster lookup.",
                },
                "file_name": {
                    "type": "string",
                    "description": "Optional display name for context.",
                },
            },
            "required": ["drive_item_id"],
        },
    },
    {
        "name": "get_project_context",
        "description": (
            "Get the project brief, brand voice, deliverables, and context "
            "for the current client engagement. Always call this at the start "
            "of a meeting or when asked about the project, client goals, "
            "budget, timeline, or approved content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The client ID, e.g. 'ramair'.",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional specific project ID.",
                },
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Specific sections to return: brief, source_material, "
                        "planning, deliverables, approvals, performance. "
                        "Omit to get all sections."
                    ),
                },
            },
            "required": ["client_id"],
        },
    },
]

# ── System prompt for live meeting conversations ───────────────────────────────

_NATHAN_MEETING_SYSTEM = """You are Nathan Ellis, Lead Orchestrator at ParlayVU.ai — a senior digital marketing strategist and client partner.

You are currently in a LIVE Microsoft Teams meeting with the client team. You are speaking out loud through your avatar, so your responses will be read aloud. This means:
- Keep responses conversational and spoken-word natural (2-4 sentences typically)
- Avoid bullet lists, markdown formatting, numbered lists, or headers — speak in flowing sentences
- For complex topics, break your answer into a few short spoken paragraphs rather than a list
- Never say "Bullet point one..." — speak as a human executive would
- If you need to enumerate things, use "First... then... and finally..." style

YOUR ROLE:
You lead a 12-person AI agent team (Alex, Ava, Blake, Casey, Codey, Dylan, Jordan, Michael, Morgan, Nora, Riley, Taylor) and serve as the strategic lead for ParlayVU clients. You think at the level of a Chief Marketing Strategist — campaigns, audiences, funnels, brand positioning, content strategy, paid media, organic growth, and business outcomes.

TOOLS AVAILABLE:
You have real-time access to:
1. Web search — find competitor data, industry benchmarks, recent news, market research
2. URL fetching — read any webpage: LinkedIn profiles, company sites, social media, news articles
3. Microsoft Teams files — browse and read documents shared in this Teams channel
4. Project context — your full knowledge of this client's brief, deliverables, approvals, and strategy

USE TOOLS PROACTIVELY:
- When someone mentions a person, competitor, or company you don't know → fetch their LinkedIn or website
- When asked about industry trends, benchmarks, or "what's working" → search before answering
- When asked about our project, timeline, or deliverables → pull the project context
- When a file is mentioned → list or read the Teams files
- When asked about social performance or campaign metrics → search or check project context
- Don't guess when you can look it up — a 2-second search is better than a hallucinated answer

CRITICAL ANTI-HALLUCINATION RULES:
1. NEVER invent statistics, benchmarks, or data. If you don't have it, search for it or say you'll follow up.
2. NEVER claim to know something about a person, company, or campaign unless you have just looked it up or it's in your project context.
3. NEVER deny being an AI if someone sincerely asks.
4. When uncertain, say: "Let me pull that up for you" — then use a tool — then answer with what you found.
5. If a tool fails or returns no result, say so honestly rather than making something up.

STYLE:
- Warm, confident, executive tone — not robotic, not over-formal
- Direct and action-oriented — "I'd recommend..." not "One might consider..."
- When you have good data, lead with the insight, then the source
- Acknowledge what you don't know and offer to find out
"""

# ── Tool execution ─────────────────────────────────────────────────────────────

async def _execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool call and return the result as a JSON string."""
    try:
        if tool_name == "web_search":
            result = await web_search(tool_input["query"])
        elif tool_name == "fetch_url":
            result = await fetch_url(tool_input["url"])
        elif tool_name == "list_teams_files":
            result = await list_teams_files(
                tool_input["team_id"],
                tool_input["channel_id"],
            )
        elif tool_name == "read_teams_file":
            result = await read_teams_file(
                tool_input["drive_item_id"],
                drive_id=tool_input.get("drive_id"),
                file_name=tool_input.get("file_name"),
            )
        elif tool_name == "get_project_context":
            result = await get_project_context(
                tool_input["client_id"],
                tool_input.get("project_id"),
                sections=tool_input.get("sections"),
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": f"Tool {tool_name} failed: {str(exc)}"})


# ── Claude conversation loop ───────────────────────────────────────────────────

def _openai_messages_to_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Convert OpenAI-format messages to Anthropic format.
    Returns (system_prompt, anthropic_messages).
    Merges any system messages from Tavus with our Nathan prompt.
    """
    system_parts = [_NATHAN_MEETING_SYSTEM]
    anthropic_msgs: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            # Tavus injects the persona's system_prompt as a system message
            # Append it after our base prompt so persona context is preserved
            if content and content.strip():
                system_parts.append(f"\n\n[ADDITIONAL CONTEXT FROM PERSONA SETUP]\n{content}")
            continue

        if role == "user":
            anthropic_msgs.append({"role": "user", "content": str(content)})
        elif role == "assistant":
            anthropic_msgs.append({"role": "assistant", "content": str(content)})
        # Skip tool-related roles in pass-through (we handle tool loop ourselves)

    # Anthropic requires at least one user message
    if not anthropic_msgs:
        anthropic_msgs.append({"role": "user", "content": "Hello"})

    # Anthropic requires alternating user/assistant roles; fix consecutive same-roles
    fixed: list[dict[str, Any]] = []
    for msg in anthropic_msgs:
        if fixed and fixed[-1]["role"] == msg["role"]:
            # Merge consecutive same-role messages
            fixed[-1]["content"] = fixed[-1]["content"] + "\n\n" + msg["content"]
        else:
            fixed.append(msg)

    return "\n\n".join(system_parts), fixed


async def run_nathan_conversation(
    openai_messages: list[dict[str, Any]],
    *,
    max_tool_rounds: int = 5,
) -> str:
    """
    Run Nathan's conversation through Claude Opus 4.7 with tool use.

    Accepts OpenAI-format messages, returns Nathan's final text response.
    Tool calls are executed automatically in a loop until Claude produces
    a final text response (no more tool calls).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return (
            "I'm sorry, I'm not fully configured right now. "
            "The ANTHROPIC_API_KEY is not set. Please contact the ParlayVU team."
        )

    client = anthropic.AsyncAnthropic(api_key=api_key)
    system_prompt, messages = _openai_messages_to_anthropic(openai_messages)

    for round_num in range(max_tool_rounds + 1):
        try:
            response = await client.messages.create(
                model="claude-opus-4-7",
                max_tokens=1024,
                system=system_prompt,
                tools=NATHAN_TOOLS,
                messages=messages,
            )
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            return (
                "I'm having trouble connecting to my AI backend right now. "
                "Give me a moment and try again."
            )

        # If no tool calls — return the text response
        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return " ".join(text_blocks).strip() or "I'm thinking about that — give me just a moment."

        # Collect tool calls from this response
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_use_blocks:
            # stop_reason was something else, return whatever text we have
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return " ".join(text_blocks).strip() or "Let me look into that and get back to you."

        if round_num >= max_tool_rounds:
            # Safety: too many tool rounds — return what we have
            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return (
                " ".join(text_blocks).strip()
                or "I've gathered a lot of information. Let me summarize what I found."
            )

        # Add Claude's response (with tool use) to message history
        messages.append({"role": "assistant", "content": response.content})

        # Execute all tool calls in this round
        tool_results = []
        for tool_block in tool_use_blocks:
            logger.info(
                "Nathan tool call: %s(%s)",
                tool_block.name,
                json.dumps(tool_block.input, default=str)[:200],
            )
            result_str = await _execute_tool(tool_block.name, tool_block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": result_str,
            })

        # Add tool results as a user message
        messages.append({"role": "user", "content": tool_results})

    return "I've done some research on that. Let me give you the key takeaways."


# ── OpenAI-compatible response builders ───────────────────────────────────────

def build_chat_completion_response(
    text: str,
    model: str = "nathan-opus",
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build an OpenAI-format chat completion response."""
    return {
        "id": f"chatcmpl-{request_id or uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text,
                },
                "finish_reason": "stop",
                "logprobs": None,
            }
        ],
        "usage": {
            "prompt_tokens": -1,   # Anthropic billing is separate
            "completion_tokens": -1,
            "total_tokens": -1,
        },
    }


def build_models_response() -> dict[str, Any]:
    """Build an OpenAI-format /v1/models response."""
    return {
        "object": "list",
        "data": [
            {
                "id": "nathan-opus",
                "object": "model",
                "created": 1_700_000_000,
                "owned_by": "parlayvu",
                "permission": [],
                "root": "nathan-opus",
                "parent": None,
            }
        ],
    }
