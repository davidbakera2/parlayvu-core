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
from app.tools.meeting_notes_tool import save_meeting_notes

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
    {
        "name": "save_meeting_notes",
        "description": (
            "File a structured meeting record to the client's Teams channel as "
            "both markdown and a Word document. Use this when wrapping up a "
            "meeting or when a participant says something like 'send the notes', "
            "'save what we discussed', 'file this', or 'wrap it up'.\n\n"
            "CRITICAL: Before calling this tool, do TWO things:\n"
            "1. Extract a STRUCTURED record from the conversation: title, "
            "summary, attendees, decisions, action_items, questions, next_steps, "
            "source_material.\n"
            "2. If anything is ambiguous - especially action item owners ('someone "
            "will do X'), action item due dates ('soon' / 'next week' without a "
            "specific date), or who was on the call - ASK FOR CLARIFICATION out "
            "loud BEFORE calling the tool. Examples: 'Before I file these, who "
            "owns the website refresh - Dylan?' or 'When's the target date for "
            "the new social schedule?'\n\n"
            "3. Then READ THE SUMMARY OUT LOUD so participants can confirm. "
            "Once they confirm, call this tool with all the structured fields. "
            "Action items missing an owner or due date should be flagged as "
            "'TBD' rather than guessed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "Short meeting title used as the filename stem, e.g. "
                        "'RamAir Weekly Strategy - May 24 2026'."
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "Plain-prose summary of the discussion, 2-4 short paragraphs. "
                        "This is the high-level narrative; specific decisions and "
                        "action items go in their own fields below."
                    ),
                },
                "client_id": {
                    "type": "string",
                    "description": (
                        "Client ID (e.g. 'ramair'). If you recently called "
                        "get_project_context, reuse the same client_id."
                    ),
                },
                "project": {
                    "type": "string",
                    "description": (
                        "Project display name, e.g. 'RamAir Straight From The Hart'. "
                        "Omit if not clear from the conversation."
                    ),
                },
                "meeting_date_time": {
                    "type": "string",
                    "description": (
                        "Human-readable meeting date and start time, e.g. "
                        "'May 25, 2026 at 9:00 AM ET'. If you don't know the start "
                        "time, omit this and the server uses the current UTC time."
                    ),
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "People who were on the meeting. Use real names where known "
                        "('David Baker', 'Sarah from RamAir'). Include yourself "
                        "('Nathan Ellis - ParlayVU') and the operator. If you don't "
                        "know who else was on, ask before filing."
                    ),
                },
                "decisions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Decisions made or announced on the call. Each item is a "
                        "single sentence stating WHAT was decided. Examples: "
                        "'Move the launch from Sept 15 to Oct 1.' / "
                        "'Approve the budget shift to paid social.'"
                    ),
                },
                "action_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "owner":    {"type": "string", "description": "Who owns it. Specialist name (Riley, Alex, ...) or external name. Use 'TBD' if not assigned."},
                            "action":   {"type": "string", "description": "Concrete action to take, action-verb-first."},
                            "due_date": {"type": "string", "description": "Specific date or 'TBD'. Do not guess vague dates."},
                        },
                        "required": ["owner", "action", "due_date"],
                    },
                    "description": (
                        "Action items with explicit owner and due date. If owner "
                        "or due date are unclear, ASK in the call before passing. "
                        "Don't invent owners or dates."
                    ),
                },
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Open questions or concerns raised during the meeting "
                        "that weren't resolved. One item per question."
                    ),
                },
                "next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Forward-looking commitments and immediate next steps to "
                        "move the project forward. One item per step. Different "
                        "from action_items: these are about momentum, not "
                        "assignments."
                    ),
                },
                "source_material": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "References to key docs, sites, reports, or links cited "
                        "or shared during the call. One item per reference. "
                        "Include URLs when present, names when not."
                    ),
                },
            },
            "required": ["title", "summary", "client_id"],
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
You serve as the strategic lead for ParlayVU clients. You think at the level of a Chief Marketing Strategist — campaigns, audiences, funnels, brand positioning, content strategy, paid media, organic growth, and business outcomes.

YOUR TEAM (12 specialist AI agents you orchestrate):
- Alex Rivera     — Visuals & Design (production-ready visual assets, layout, brand consistency)
- Ava Hosseini    — Content Writing (clear, brand-aware copy tuned to client voice)
- Blake Quinn     — Intelligence & Insights (research, evidence-based strategy, market analysis)
- Casey Johnson   — Engagement & Community (community replies, audience interaction)
- Codey Miner     — Coding & Integrations (clean, reversible code; integrations)
- Dylan Brooks    — Web & Deployment (Astro + Tailwind sites on Cloudflare Pages)
- Jordan Lee      — Social Execution (real-time social posting and X intelligence)
- Michael Stone   — Sales & Conversion (funnel optimization, conversion strategy)
- Morgan Reyes    — Paid Media (ad campaigns, paid social, budget allocation)
- Nora Patel      — Partnerships & Affiliates (partner outreach, affiliate strategy)
- Riley Carter    — Publishing & Distribution (content scheduling, distribution channels)
- Taylor Kim      — Customer Success & Retention (client retention, success ops)

When a topic clearly maps to one of them ("we need ad creative" → Alex, "need a landing page" → Dylan, "what's working on TikTok" → Jordan), say "I'll have [name] take this and report back." You're the human-facing point of contact who notes the work and routes it after the call — you don't dispatch them in real time mid-conversation.

TOOLS AVAILABLE:
You have real-time access to:
1. Web search — find competitor data, industry benchmarks, recent news, market research
2. URL fetching — read any webpage: LinkedIn profiles, company sites, social media, news articles
3. Microsoft Teams files — browse and read documents shared in this Teams channel
4. Project context — pull a specific client's brief, deliverables, approvals, and strategy
5. Save meeting notes — file a written summary to the client's Teams channel as markdown + Word doc. This is your ONE write tool.

USE TOOLS PROACTIVELY:
- When someone mentions a person, competitor, or company you don't know → fetch their LinkedIn or website
- When asked about industry trends, benchmarks, or "what's working" → search before answering
- When a client is named (e.g. "RamAir", "Acme Corp") → call get_project_context with client_id set to that name lowercased and stripped of spaces (e.g. "ramair", "acmecorp"). Do this FIRST, before answering anything project-specific.
- When someone references "our project", "the brief", "the timeline", or "what was agreed" → call get_project_context for the current client
- When a file is mentioned → list or read the Teams files
- When the meeting is wrapping up, OR when someone says "send the notes", "save what we discussed", "file this", "wrap it up" → build a STRUCTURED meeting record from the conversation: title, summary (2-4 paragraphs), attendees, decisions, action_items (with owner + due_date), questions, next_steps, source_material. If anything is ambiguous — especially action item owners ("someone will do X") or due dates ("soon" / "next week" without a specific date) or who was actually on the call — ASK FOR CLARIFICATION out loud BEFORE calling save_meeting_notes. Once you have a clean record, say "Here's what I'll file..." and read the summary + decisions + action items out loud so participants can confirm, then call save_meeting_notes with all the structured fields. Action items missing an owner or due date should be flagged as "TBD" rather than guessed. Do NOT call save_meeting_notes silently.

NARRATE WHILE YOU WORK (very important — silence breaks immersion):
- Tool calls take 2-5 seconds (especially save_meeting_notes, which uploads to Teams). During that time, you'll be SILENT to the client unless you've spoken first.
- Before calling ANY tool that takes more than a beat, say something natural in the SAME response, BEFORE the tool call. Examples:
   - Before web_search: "Let me pull that up for you, give me a second…"
   - Before fetch_url for a LinkedIn profile: "Sure, let me look at his profile — one moment…"
   - Before get_project_context: "Hang on, let me check our project notes on that…"
   - Before save_meeting_notes: "OK, let me put those notes together and file them. Give me about ten seconds — the system has to sync to the Teams channel."
- After the tool returns, briefly confirm the outcome: "All set — the notes are in the RamAir channel now." or "Found it — here's what I'm seeing on his LinkedIn…"
- If a tool takes unusually long, you can fill the silence with a follow-up like "Still pulling that down, almost there…" — but only if the conversation feels like it needs it. Normally, one pre-tool sentence + one post-tool sentence is plenty.
- Don't guess when you can look it up — a 2-second search is better than a hallucinated answer

CRITICAL ANTI-HALLUCINATION RULES:
1. NEVER invent statistics, benchmarks, or data. If you don't have it, search for it or say you'll follow up.
2. NEVER claim to know something about a person, company, or campaign unless you have just looked it up or it's in your project context.
3. NEVER deny being an AI if someone sincerely asks.
4. When uncertain, say: "Let me pull that up for you" — then use a tool — then answer with what you found.
5. If a tool fails or returns no result, say so honestly rather than making something up.
6. Your write access is LIMITED to ONE action: save_meeting_notes. You can file a meeting summary to the client's Teams channel using that tool, and only that tool. For everything else — sending emails, posting to social, deploying sites, creating approvals, scheduling meetings, modifying code, generating ad creative, anything else — you cannot do it yourself. Route those requests by name to the right specialist: "I'll have Ava draft that email", "I'll have Riley publish that", "I'll have Codey wire up the integration", "I'll have Dylan get the site updated", "I'll have Morgan adjust the ad spend". NEVER say "I've sent that" or "I've scheduled that" or "I've posted that" — those things did not happen. For meeting notes specifically: you ARE the one filing them, so it IS honest to say "Filing those notes now" — then call save_meeting_notes. Just don't claim other writes you can't perform.

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
        elif tool_name == "save_meeting_notes":
            result = await save_meeting_notes(
                title=tool_input["title"],
                summary=tool_input["summary"],
                client_id=tool_input["client_id"],
                project=tool_input.get("project"),
                meeting_date_time=tool_input.get("meeting_date_time"),
                attendees=tool_input.get("attendees"),
                decisions=tool_input.get("decisions"),
                action_items=tool_input.get("action_items"),
                questions=tool_input.get("questions"),
                next_steps=tool_input.get("next_steps"),
                source_material=tool_input.get("source_material"),
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}

        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": f"Tool {tool_name} failed: {str(exc)}"})


# ── Claude conversation loop ───────────────────────────────────────────────────

def _build_current_date_context() -> str:
    """
    Inject today's date into Nathan's system prompt.

    Claude has no built-in clock. Without this, when the client says
    "Friday" or "tomorrow" or "next week", Nathan has no anchor to
    resolve from - he'll pass the literal phrase through as the action
    item due_date, and the rendered DOCX shows "Friday" or nothing
    instead of a real date.

    Format keeps day-of-week up front so resolving "this Friday" is
    one step of arithmetic.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return (
        f"CURRENT DATE: {now.strftime('%A, %B %d, %Y')} (UTC).\n"
        f"Use this as the anchor when meeting participants mention RELATIVE "
        f"dates like 'tomorrow', 'this Friday', 'next week', 'in two days', "
        f"'end of month'. Resolve them to specific calendar dates (e.g. "
        f"'June 1, 2026') BEFORE you pass them as action item due_dates or "
        f"meeting dates. The client should hear and see real dates, not "
        f"'Friday'. If a relative reference is ambiguous (e.g. 'soon', "
        f"'next time'), ask for clarification."
    )


def _openai_messages_to_anthropic(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """
    Convert OpenAI-format messages to Anthropic format.
    Returns (system_prompt, anthropic_messages).
    Merges any system messages from Tavus with our Nathan prompt.

    Prepends a CURRENT DATE context block so Nathan knows what "today"
    means and can resolve relative date references in real time.
    """
    system_parts = [_build_current_date_context(), _NATHAN_MEETING_SYSTEM]
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


async def run_nathan_conversation_streaming(
    openai_messages: list[dict[str, Any]],
    *,
    max_tool_rounds: int = 5,
) -> AsyncIterator[str]:
    """
    Run Nathan's conversation as an async generator yielding text chunks as
    Claude produces them.

    Critically, this yields any text Claude returns ALONGSIDE a tool call
    in the same response — not just the final end_turn text. That lets the
    streaming /v1/chat/completions endpoint forward Nathan's pre-tool
    narration ("let me get those filed, give me a moment...") to Tavus
    immediately, so Tavus is speaking it while the tool runs in the
    background. Without this, the user just sees Nathan stare at them
    silently for 3-5 seconds during a save.

    Each yield is a complete text fragment, suitable for streaming
    directly to Tavus as an SSE `delta` chunk.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield (
            "I'm sorry, I'm not fully configured right now. "
            "The ANTHROPIC_API_KEY is not set. Please contact the ParlayVU team."
        )
        return

    client = anthropic.AsyncAnthropic(api_key=api_key)
    system_prompt, messages = _openai_messages_to_anthropic(openai_messages)
    any_text_emitted = False

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
            if not any_text_emitted:
                yield (
                    "I'm having trouble connecting to my AI backend right now. "
                    "Give me a moment and try again."
                )
            return

        # Walk the content blocks IN ORDER. Claude's response can interleave
        # text and tool_use blocks; we want to emit each text block as soon
        # as we see it (so it can be spoken before the next tool runs) and
        # collect tool_use blocks for the post-text execution phase.
        round_tool_uses = []
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text = block.text.strip()
                if text:
                    any_text_emitted = True
                    yield text
            elif getattr(block, "type", None) == "tool_use":
                round_tool_uses.append(block)

        if response.stop_reason == "end_turn":
            return

        if not round_tool_uses:
            # Unexpected stop reason with no tool calls and no text. Yield
            # a fallback so the user doesn't get pure silence.
            if not any_text_emitted:
                yield "Let me look into that and get back to you."
            return

        if round_num >= max_tool_rounds:
            # Safety stop: too many tool rounds. Emit a clean wrap-up if we
            # haven't said anything else.
            if not any_text_emitted:
                yield "I've gathered a lot of information. Let me summarize what I found."
            return

        # Add Claude's full response (text + tool_use blocks) to history
        messages.append({"role": "assistant", "content": response.content})

        # Execute each tool call (this is where the silence happens — the
        # narration text we already yielded should fill the audio gap on
        # the Tavus side while these run).
        tool_results = []
        for tool_block in round_tool_uses:
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

        messages.append({"role": "user", "content": tool_results})


async def run_nathan_conversation(
    openai_messages: list[dict[str, Any]],
    *,
    max_tool_rounds: int = 5,
) -> str:
    """
    Non-streaming wrapper: collect every text chunk from the streaming
    generator and join them. Used by the non-streaming /v1/chat/completions
    path and by tests. Preserves the original API for callers that just
    want one string back.
    """
    chunks: list[str] = []
    async for chunk in run_nathan_conversation_streaming(
        openai_messages,
        max_tool_rounds=max_tool_rounds,
    ):
        chunks.append(chunk)
    if not chunks:
        return "I'm thinking about that — give me just a moment."
    return " ".join(chunks).strip()


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
