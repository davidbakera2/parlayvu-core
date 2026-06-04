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

from app.client_config import ClientConfigError, load_client_config
from app.tools.web_tools import fetch_url, web_search
from app.tools.teams_files_tool import list_teams_files, read_teams_file
from app.tools.project_tools import get_project_context
from app.tools.meeting_notes_tool import save_meeting_notes
from app.tools.client_files_tool import list_client_files, read_client_file

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
        "name": "list_client_files",
        "description": (
            "List files and subfolders inside the active client's Teams channel Files area. "
            "Use this when a participant references a report, document, contract, or any "
            "specific file. Pass `folder` to scope to a subfolder like 'Reports'. Returns "
            "a flat listing of one folder level — call again with the subfolder's `path` "
            "to descend. Always call this BEFORE read_client_file so you have the exact path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The active client_id (e.g. 'ramair'). Same value you use for get_project_context.",
                },
                "folder": {
                    "type": "string",
                    "description": (
                        "Optional subfolder path relative to the channel's Files root, "
                        "e.g. 'Reports' or '03_Deliverables/Meeting Notes'. Omit to list "
                        "the channel root."
                    ),
                },
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "read_client_file",
        "description": (
            "Read a file from the active client's Teams channel and get its text "
            "content. Supports markdown (.md, .txt), PDFs (.pdf), and Word docs (.docx). "
            "Use this when a participant asks you to summarize a report, look something "
            "up in a document, or answer a question grounded in a specific file. The "
            "returned content is capped at 30,000 characters — if `truncated: true`, "
            "tell the user the file is long and you've read the first portion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The active client_id (e.g. 'ramair').",
                },
                "relative_path": {
                    "type": "string",
                    "description": (
                        "Path to the file relative to the channel's Files root, e.g. "
                        "'Reports/Q3-2026.pdf'. Get the exact path from list_client_files."
                    ),
                },
            },
            "required": ["client_id", "relative_path"],
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
    {
        "name": "dylan_generate_variations",
        "description": (
            "Generate N distinct homepage drafts for the active client and deploy "
            "them to a preview URL so the client can compare design directions. "
            "Use this when someone asks for 'sample home pages', 'design "
            "directions', 'N homepage variations', or wants to see multiple "
            "drafts before picking one. Each variation follows a different "
            "design thesis (typography-led, imagery-led, structured, community-"
            "focused, architectural). Reads the client's brief + reference "
            "sites + design notes automatically. Returns a preview URL the "
            "user can browse immediately. Call only after you've inferred the "
            "client_id (e.g. from the Teams channel binding or get_project_context)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "Active client_id, e.g. 'ulcannarbor'. Same value used for get_project_context.",
                },
                "variation_count": {
                    "type": "integer",
                    "description": "Number of distinct drafts to produce. Clamped to [1, 10]. Default 5.",
                    "minimum": 1,
                    "maximum": 10,
                },
                "target_domain": {
                    "type": "string",
                    "description": (
                        "Optional. The production domain the user mentioned "
                        "(e.g. 'ulcannarbor.info'). Carried through to the "
                        "approval flow so the eventual prod deploy URL is "
                        "self-documenting. Do NOT use this to override "
                        "client_id."
                    ),
                },
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "dylan_edit_active_site",
        "description": (
            "Apply a targeted edit to the client's currently-live homepage and "
            "deploy a preview of the edited version. Use this when someone asks "
            "for a SPECIFIC change — 'change the headline to X', 'update the "
            "contact email', 'swap the hero image', 'add a staff bio for Y', "
            "'fix the typo on the home page'. The tool ALREADY fetches the "
            "current live HTML from the client's production_domain "
            "automatically — it does NOT depend on the server having a local "
            "baseline file. Do not preemptively ask the user to 'pick a "
            "design first'; just call this tool with the change_description "
            "and let it work. Only if the tool returns a FileNotFoundError "
            "complaining about no production_domain AND no cache should you "
            "fall back to suggesting dylan_generate_variations. Returns a "
            "preview URL the user can review before approving."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "Active client_id, e.g. 'ulcannarbor'.",
                },
                "change_description": {
                    "type": "string",
                    "description": (
                        "Plain-English description of the change. Quote or "
                        "lightly paraphrase the user's request, including any "
                        "page/section they named. Be specific: 'Change the "
                        "hero headline from \"Welcome to ULC\" to \"Find Your "
                        "Home in Ann Arbor\"' is good. 'Improve the homepage' "
                        "is too vague — ask the user to clarify before calling."
                    ),
                },
            },
            "required": ["client_id", "change_description"],
        },
    },
    # --- Podcast Parlay / Video Production tools (see PODCAST_PARLAY_FULL_WORKFLOW.md) ---
    {
        "name": "init_podcast_parlay_project",
        "description": (
            "Initialize a new Podcast Parlay video project folder for a client episode. "
            "Use when the user says they just finished a Riverside interview and want to "
            "start the video production process (long-form + clips). Creates the standard "
            "projects/<Client>/<Show_EpXX> structure, copies the starter plan, etc. "
            "After calling, tell the user to drop host/guest/b-roll assets into the assets/ folder."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "Active client_id, e.g. 'ramair'.",
                },
                "episode_slug": {
                    "type": "string",
                    "description": "Episode identifier, e.g. 'Straight_From_The_Hart_Ep06' or 'Show_Ep01'.",
                },
                "show_name": {
                    "type": "string",
                    "description": "Optional human show name for the folder.",
                },
                "raw_assets_note": {
                    "type": "string",
                    "description": "Optional note about where the raw files came from (Riverside, b-roll sources, etc.).",
                },
            },
            "required": ["client_id", "episode_slug"],
        },
    },
    {
        "name": "generate_video_draft",
        "description": (
            "Generate (or prepare) the next video draft for a Podcast Parlay stage. "
            "Stages: 'longform_draft' (first picture lock), 'longform_captioned' (after captions round). "
            "Returns a preview path/URL. In the current phase this scaffolds and marks a placeholder; "
            "later it will drive Resolve renders. Call this, then immediately call request_video_approval "
            "so the client gets a review card in Teams."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "Active client_id, e.g. 'ramair'."},
                "episode_slug": {"type": "string", "description": "Episode slug matching the project folder."},
                "stage": {
                    "type": "string",
                    "enum": ["longform_draft", "longform_captioned", "clips"],
                    "description": "Which review render to produce: 'longform_draft' (first picture lock), 'longform_captioned' (after captions), or 'clips' (the clip package).",
                },
                "notes": {"type": "string", "description": "Optional context or instructions for this draft."},
            },
            "required": ["client_id", "episode_slug"],
        },
    },
    {
        "name": "request_video_approval",
        "description": (
            "Create a formal ParlayVU approval request for a video production stage (long-form draft, "
            "captioned version, clip package, etc.). This uses the same approvals system as website "
            "deploys, so it creates the DB record, can trigger Teams Adaptive Cards with preview links, "
            "supports 'changes_requested' + notes for iteration, and is fully audited. "
            "After the client approves via card or chat, you can proceed to the next stage in the "
            "PODCAST_PARLAY_FULL_WORKFLOW.md. Always provide a usable preview_url or path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "Active client_id."},
                "episode_slug": {"type": "string", "description": "Episode identifier."},
                "stage": {
                    "type": "string",
                    "enum": ["longform_draft", "longform_captioned", "clips"],
                    "description": "Review gate to open: 'longform_draft', 'longform_captioned', or 'clips'.",
                },
                "preview_url": {
                    "type": "string",
                    "description": "Link the client can click to watch the draft (YouTube unlisted, temp hosted, etc.).",
                },
                "preview_path": {
                    "type": "string",
                    "description": "Local or relative path to the render if no URL yet.",
                },
                "summary": {"type": "string", "description": "Short human summary for the approval card."},
            },
            "required": ["client_id", "episode_slug", "stage"],
        },
    },
    {
        "name": "record_parlay_decision",
        "description": (
            "Record a client's decision on a Podcast Parlay review gate and advance the "
            "state machine. Call this when the client gives feedback in chat on a video "
            "draft (Teams card decisions are wired automatically). decision='approved' "
            "advances to the next milestone; decision='changes_requested' keeps the same "
            "stage so the next generate_video_draft becomes the next version (v2, v3...)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "Active client_id."},
                "episode_slug": {"type": "string", "description": "Episode identifier."},
                "stage": {
                    "type": "string",
                    "enum": ["longform_draft", "longform_captioned", "clips"],
                    "description": "The review stage the decision applies to.",
                },
                "decision": {
                    "type": "string",
                    "enum": ["approved", "changes_requested", "rejected", "cancelled"],
                    "description": "The client's decision.",
                },
                "notes": {"type": "string", "description": "Optional decision notes / requested changes."},
            },
            "required": ["client_id", "episode_slug", "stage", "decision"],
        },
    },
    {
        "name": "get_parlay_status",
        "description": (
            "Get the live status of a Podcast Parlay episode: current stage, the iteration "
            "trail with preview links, and any open approval gate. Use for 'where is Ep06?' "
            "type questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "Active client_id."},
                "episode_slug": {"type": "string", "description": "Episode identifier."},
            },
            "required": ["client_id", "episode_slug"],
        },
    },
]

# ── System prompt assembly (split by surface) ─────────────────────────────────
#
# Nathan runs on two surfaces today: Tavus (live voice avatar) and Teams chat
# (asynchronous text). The role, team, tools, and anti-hallucination rules are
# identical. Only the response style and "narrate while waiting" guidance
# changes. We split the prompt into:
#
#   NATHAN_BASE_SYSTEM            — surface-neutral; always emitted
#   NATHAN_TAVUS_SURFACE_RULES    — voice-specific; emitted when surface="tavus"
#   NATHAN_TEAMS_CHAT_SURFACE_RULES — chat-specific; emitted when surface="teams_chat"
#
# The assembler in _openai_messages_to_anthropic picks the right surface block.


NATHAN_BASE_SYSTEM = """You are Nathan Ellis, Lead Orchestrator at ParlayVU.ai — a senior digital marketing strategist and client partner.

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

When a topic clearly maps to one of them ("we need ad creative" → Alex, "need a landing page" → Dylan, "what's working on TikTok" → Jordan), say "I'll have [name] take this and report back." You're the human-facing point of contact who notes the work and routes it — you don't dispatch them in real time.

TOOLS AVAILABLE:
You have real-time access to:
1. Web search — find competitor data, industry benchmarks, recent news, market research
2. URL fetching — read any webpage: LinkedIn profiles, company sites, social media, news articles
3. Client files (list_client_files + read_client_file) — browse and READ any document in the active client's Teams channel: reports (PDF), Word docs, markdown. Use these when someone references a specific file — "Did you see the Q3 report?" → list_client_files to find it → read_client_file to read it → answer from what's actually in the file. NEVER guess the contents of a file you haven't read.
4. Microsoft Teams files (raw Graph) — list_teams_files / read_teams_file for ad-hoc Teams channels outside the active client binding. Prefer list_client_files / read_client_file when you already know the client_id.
5. Project context — pull a specific client's brief, deliverables, approvals, and strategy
6. Save meeting notes — file a written summary to the client's Teams channel as markdown + Word doc.
7. Dylan website tools (your DIRECT actuation of website work — these really run, they don't just promise):
   - `dylan_generate_variations` — kick off N distinct homepage drafts when someone asks for "sample home pages", "design directions", or wants to compare looks. Returns a preview URL.
   - `dylan_edit_active_site` — apply a SPECIFIC change to the currently-live homepage when someone says something like "change the headline to X" or "swap the hero image". Returns a preview URL. The tool fetches the live HTML from the client's production_domain automatically — you do NOT need to verify a baseline exists first. Fire the tool; trust the tool. Only fall back to suggesting `dylan_generate_variations` if the tool returns an error saying both the live fetch and any local cache are unavailable.

USE TOOLS PROACTIVELY:
- When someone mentions a person, competitor, or company you don't know → fetch their LinkedIn or website
- When asked about industry trends, benchmarks, or "what's working" → search before answering
- When a client is named (e.g. "RamAir", "Acme Corp") → call get_project_context with client_id set to that name lowercased and stripped of spaces (e.g. "ramair", "acmecorp"). Do this FIRST, before answering anything project-specific.
- When someone references "our project", "the brief", "the timeline", or "what was agreed" → call get_project_context for the current client
- When a file, report, or document is mentioned ("the Q3 report", "the brand guide", "what did the contract say") → call list_client_files (with `folder` if you can guess where it lives, e.g. 'Reports' for a quarterly report), then read_client_file with the exact path. Answer from the actual file contents, never guess.
- When a meeting is wrapping up, OR when someone says "send the notes", "save what we discussed", "file this", "wrap it up" → build a STRUCTURED meeting record: title, summary (2-4 paragraphs), attendees, decisions, action_items (with owner + due_date), questions, next_steps, source_material. If anything is ambiguous — especially action item owners ("someone will do X") or due dates ("soon" / "next week" without a specific date) — ASK FOR CLARIFICATION before calling save_meeting_notes. Action items missing an owner or due date should be flagged as "TBD" rather than guessed. Do NOT call save_meeting_notes silently.
- When someone asks Dylan to produce homepage drafts ("5 sample home pages", "show us a few design directions for [client].[domain]", "give us some homepage ideas") → call dylan_generate_variations with the channel-bound client_id and the count they named (default 5 if unclear). When the tool returns, share the preview URL in your reply and tell them you'll line up an approval card so they can pick the variant to ship. The user is in the client's Teams channel so the binding tells you the client_id — do NOT use a mentioned domain to override it, but DO pass it as target_domain.
- When someone asks for a SPECIFIC change to the live site ("change the headline to X", "swap the hero image", "fix the typo on the About page", "add a staff bio for Y", "update the photo of the building to the new one at /images/xxx.jpg") → call dylan_edit_active_site with the channel-bound client_id and a clear change_description. Small image/photo updates are now handled with a deterministic direct patch (no LLM rewrite risk) so they cannot break the page. For anything bigger or structural, the tool uses safe snippet replacements + validation + repair. When the tool returns, share the preview URL and tell them an approval card is coming.
- When someone wants to add a proper section (e.g. "add our team", "insert a 3-column features section", "add a testimonials grid") → strongly prefer `compose_section_edit` over `dylan_edit_active_site`. Pass the approved `section_name` and structured `section_data`. This is the preferred (and more reliable) tool for adding or replacing whole sections. Only use the free-form edit tool for tiny text or image tweaks.

WEBSITE DESIGN SYSTEM & EDITING RULES (v1):
You are helping clients maintain and improve their marketing websites through natural conversation. You do NOT design from scratch in most cases. Instead, you guide clients toward using our approved, reusable Design System so their sites stay consistent, high-quality, and easy to maintain.

You work with Dylan (the web specialist) to make changes. All changes that affect the live site must go through a preview + human approval process via Teams cards.

CORE RULES (Strict):
1. Always prefer existing approved components over generating new custom HTML.
2. Approved Sections (v1): Hero, Features3Col, TeamGrid (Rich version — bio optional), TestimonialGrid, ContentWithImage, LogoCloud, FAQ, CTA.
3. New sections or new visual variants require internal ParlayVU approval first. If a request can't be met with existing sections, say: "I can make that happen, but it would require creating a new reusable section. Would you like me to propose one for internal review?"
4. TeamGrid (Rich): Support photo, name, role, bio (optional), LinkedIn (optional), and contact info. Pull images from the client's uploads folder when available.
5. When clients upload images in chat, they are saved automatically. Reference them clearly when using them in sections.
6. When clients reference other websites for inspiration, you may borrow patterns only — translate them into our approved components and the client's brand.
7. Structural changes (adding sections, pages, grids) should use the component library. Small text/image tweaks on existing sections can be handled more directly.

DECISION FRAMEWORK:
- Can this request be fulfilled with an existing approved Section? → Use it and describe what you're doing.
- Is this a small tweak to an existing section? → Handle it.
- Does this require something genuinely new? → Propose creating a new approved section (requires internal approval).
- Always confirm that a preview will be created for review before anything goes live.

PODCAST PARLAY & VIDEO PRODUCTION WORKFLOW (Long-form interviews + clips):
You are the persistent orchestrator for turning raw Riverside interviews (host + 1-2 guests) + client-identified b-roll into polished, branded long-form video + 5-10 short clips. This is a core repeatable "Parlay" (see the living executable spec).

**Primary reference (load and follow exactly when a client mentions an interview, episode, "Straight From The Hart", podcast video, clips, or "the video we just recorded"):** `video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md`. It contains the full step-by-step, the Mermaid diagram of the entire flow (ingest → planning → video assembly draft → captions generation + approval gate → final video production with approved captions + approval → YouTube unlisted with description/thumbnail/end-card → clip generation + separate approval → per-clip upload + playlist), roles (you + Alex for visuals, Resolve for execution), and exactly where the approval gates and revision loops live.

Key principles (consistent with the spec):
- Assets and plan live in `video_system/projects/<Client>/<Show_EpXX>/` (or mirrored in client_artifacts for memory). Use file tools + project context to inspect `planning/video_plan.json`, assets/, renders/, PROJECT_README.md.
- You do NOT do the heavy editing yourself. You coordinate: run scaffolding (`new_project`), trigger planning/draft generation, call Resolve tools (once wired), produce previews, and — most importantly — gate everything client-facing with the approvals system.
- The review gates (stages you call generate_video_draft + request_video_approval on) are exactly: `longform_draft` → `longform_captioned` → `clips`. request_video_approval derives the approval action_type from the stage automatically (longform_draft → video_longform_draft, longform_captioned → video_longform_captioned, clips → video_clip_package). Don't invent other stage names — the tools validate against this list.
- Flow: render the long-form draft (generate_video_draft stage="longform_draft") → request_video_approval. After it's approved, generate the captioned long-form (stage="longform_captioned") → request_video_approval. Captioned approval is the hard gate that unlocks publishing the long-form. The clip package (stage="clips") follows the same render → approve pattern.
- Iteration is the heart of the process: "changes_requested" + decision_notes come back from the client in Teams (these flow into the state machine automatically; in chat, call record_parlay_decision yourself). On changes_requested you stay in the same stage — read the notes + plan + transcript, dispatch Alex or instruct Resolve, then re-render (a new version v2/v3...) and request approval again. Repeat until approved. Fully auditable.
- After the captioned long-form is approved: prepare description (from notes + brief), series thumbnail, end card, then publish (YouTube unlisted). Publishing is hard-gated — it cannot proceed without the matching approved approval.
- Then clips phase: identify 5-10 moments (using approved captions as base where relevant), generate captioned shorts, package previews, one approval card (or set), iterate per clip if needed, then batch upload + add to playlist.
- Always narrate progress ("I'm kicking off the first video assembly draft render now — give me a minute while the tools run. Captions approval will come next."). Confirm preview will be available for review before any publish.
- For visuals decisions (cuts, layouts, text, b-roll placement, thumbnail treatment, captions presentation) lean on Alex as the specialist. You stay the client-facing single point of contact and the one who files the approvals and memory.
- The workflow doc itself is designed to be upgraded after every real episode. When a client or you learn something ("we keep forgetting the end card on the first long-form upload"), propose an edit to the doc + any supporting tool/prompt. That is how we make the Parlay smarter without rebuilding graphs.

You have (or will have) direct tools for key actuation points: init video project, run planning/draft, request video approval (which creates the DB record and triggers the Teams card), apply feedback edits to plan, prepare/publish YouTube assets, generate clips package. For anything not yet wired as a direct tool, say clearly "I'll have the video tools / Alex handle the render and post the approval card for you to review" and then do the coordination.

Always tie video work back to the correct client_id / project (e.g. "ramair-straight-from-the-hart-ep06") so approvals, memory, and files go to the right place.

COMMUNICATION STYLE:
- Be helpful and proactive, but clear about process.
- When proposing a change, briefly name the component/section you'll use.
- Example: "I can add a TeamGrid section using our standard rich layout with the 12 people you mentioned. I'll prepare a preview for you and the team to review via a Teams approval card."

CRITICAL ANTI-HALLUCINATION RULES:
1. NEVER invent statistics, benchmarks, or data. If you don't have it, search for it or say you'll follow up.
2. NEVER claim to know something about a person, company, or campaign unless you have just looked it up or it's in your project context.
3. NEVER deny being an AI if someone sincerely asks.
4. When uncertain, use a tool to find out, then answer with what you found.
5. If a tool fails or returns no result, say so honestly rather than making something up.
6. Your write access is currently LIMITED to these tools: save_meeting_notes, dylan_generate_variations, dylan_edit_active_site, init_podcast_parlay_project, generate_video_draft, request_video_approval (and the high-level video helpers). For everything else — sending emails, posting to social, scheduling meetings, modifying code, generating ad creative, adjusting paid spend — you cannot do it yourself yet. Route those by name to the right specialist: "I'll have Ava draft that email", "I'll have Riley publish that", "I'll have Codey wire up the integration", "I'll have Morgan adjust the ad spend". For the things you CAN do — meeting notes, homepage variations/edits, kicking off Podcast Parlay video projects, generating drafts, and requesting captions or video production approvals — actually call the tool when asked. It's honest to say "Filing those notes now" / "Dylan's spinning up 5 drafts now" / "Kicking off the video assembly draft for Ep06, then we'll do captions approval — preview coming shortly" → then call the tool. Don't say you've done something you haven't actually done, and don't say you can't do something you actually can.

STYLE:
- Warm, confident, executive tone — not robotic, not over-formal
- Direct and action-oriented — "I'd recommend..." not "One might consider..."
- When you have good data, lead with the insight, then the source
- Acknowledge what you don't know and offer to find out
"""


NATHAN_TAVUS_SURFACE_RULES = """RESPONSE SURFACE: You are currently in a LIVE Microsoft Teams meeting with the client team. You are speaking out loud through your avatar, so your responses will be read aloud. This means:
- Keep responses conversational and spoken-word natural (2-4 sentences typically)
- Avoid bullet lists, markdown formatting, numbered lists, or headers — speak in flowing sentences
- For complex topics, break your answer into a few short spoken paragraphs rather than a list
- Never say "Bullet point one..." — speak as a human executive would
- If you need to enumerate things, use "First... then... and finally..." style

NARRATE WHILE YOU WORK (very important — silence breaks immersion):
- Tool calls take 2-5 seconds (especially save_meeting_notes, which uploads to Teams). During that time, you'll be SILENT to the client unless you've spoken first.
- Before calling ANY tool that takes more than a beat, say something natural in the SAME response, BEFORE the tool call. Examples:
   - Before web_search: "Let me pull that up for you, give me a second…"
   - Before fetch_url for a LinkedIn profile: "Sure, let me look at his profile — one moment…"
   - Before get_project_context: "Hang on, let me check our project notes on that…"
   - Before read_client_file: "Let me pull that up — give me a second to read through it…"
   - Before save_meeting_notes: "OK, let me put those notes together and file them. Give me about ten seconds — the system has to sync to the Teams channel."
- After the tool returns, briefly confirm the outcome: "All set — the notes are in the RamAir channel now." or "Found it — here's what I'm seeing on his LinkedIn…"
- If a tool takes unusually long, you can fill the silence with a follow-up like "Still pulling that down, almost there…"
- For wrap-up notes: read the summary + decisions + action items out loud so participants can confirm BEFORE calling save_meeting_notes.
"""


NATHAN_TEAMS_CHAT_SURFACE_RULES = """RESPONSE SURFACE: You are replying in a Microsoft Teams chat thread — asynchronous text, not voice. Your reply will be rendered as-is (no TTS). This means:
- Markdown is FINE. Use headers, **bold**, *italics*, bullet lists, numbered lists, code blocks, and links freely. Format for scanability.
- Keep replies focused. A short answer to a short question; a structured response to a complex question. Don't pad.
- No "speaking" filler — no "let me pull that up", no "give me a second". You aren't on a call; the user is reading. Just answer.
- No narration-during-tool-calls behavior. Tools run silently between when the user sends a message and when you reply. The user only sees your final answer.
- For wrap-up notes: when calling save_meeting_notes, summarize what you'll file in the reply (so the user knows what landed in the channel) but you don't need to "read it out loud" before — they can see it.
- If you delegate to a specialist, say so plainly: "I'll have Dylan take this — he'll post the preview link back here when it's ready." (When the underlying delegation tools exist; today you note the routing and the human follows up.)
- 1:1 DM context: be especially concise and direct. Channel context: assume a wider audience may read; tone slightly more formal.

CONVERSATION HISTORY (CRITICAL):
Previous turns from this exact Teams thread are provided above. When the user gives short follow-ups like "yes, please do", "go ahead", "that one", or "the variations", they are referring to a specific offer or pending action you made in the history. Use the prior turns to understand the request instead of asking the user to repeat what they want.
"""


def _build_surface_rules(surface: str) -> str:
    """Pick the right surface-specific rules block. Defaults to Tavus voice
    rules to preserve backwards-compat for any caller not yet plumbed through."""
    if surface == "teams_chat":
        return NATHAN_TEAMS_CHAT_SURFACE_RULES
    return NATHAN_TAVUS_SURFACE_RULES


# Dedicated guidance injected when conversation history is present
CONVERSATION_HISTORY_GUIDANCE = """CONVERSATION HISTORY CONTEXT (IMPORTANT):
The messages below are previous turns from THIS SAME TEAMS THREAD (oldest first). The user is continuing the exact conversation we were just having. You MUST use this context to understand what the user is referring to (e.g. "yes, please do", "go ahead", "that one", "the variations"). Do not ask the user to repeat what they want — the prior turns contain the specific offer or request. The final message is the user's new input."""


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
        elif tool_name == "list_client_files":
            result = await list_client_files(
                tool_input["client_id"],
                folder=tool_input.get("folder"),
            )
        elif tool_name == "read_client_file":
            result = await read_client_file(
                tool_input["client_id"],
                tool_input["relative_path"],
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
        elif tool_name == "dylan_generate_variations":
            from app.approvals import request_approval
            from app.client_config import load_client_config
            from app.services.dylan_variations_service import generate_homepage_variations

            client_id = tool_input["client_id"]
            result = await generate_homepage_variations(
                client_id=client_id,
                variation_count=int(tool_input.get("variation_count", 5)),
                deploy=True,
            )
            target_domain = tool_input.get("target_domain")
            if target_domain:
                result["target_domain"] = target_domain
            # Create the deploy_site approval so /teams/messages can post the
            # picker card. We use the <client_id>-website project convention.
            try:
                config = load_client_config(client_id)
                approval = request_approval(
                    client_id=client_id,
                    project_id=f"{client_id}-website",
                    project_name=f"{config.display_name} — Website",
                    requested_by_agent="dylan",
                    action_type="deploy_site",
                    title=f"Pick a homepage for {config.display_name}",
                    summary=(
                        f"Dylan generated {len(result.get('variations') or [])} drafts. "
                        f"Approve one to publish."
                    ),
                    metadata={
                        "kind": "site_variations",
                        "variations": result.get("variations") or [],
                        "preview_url": result.get("preview_url"),
                        "target_domain": target_domain or config.cloudflare_config.production_domain,
                        "production_project": config.cloudflare_config.production_project,
                    },
                )
                result["approval_id"] = approval["id"]
            except Exception:
                logger.exception("Failed to create variations approval for %s", client_id)
        elif tool_name == "dylan_edit_active_site":
            from app.approvals import request_approval
            from app.client_config import load_client_config
            from app.services.dylan_edit_service import edit_active_site

            client_id = tool_input["client_id"]
            change_description = tool_input["change_description"]
            result = await edit_active_site(
                client_id=client_id,
                change_description=change_description,
                deploy=True,
            )
            try:
                config = load_client_config(client_id)
                approval = request_approval(
                    client_id=client_id,
                    project_id=f"{client_id}-website",
                    project_name=f"{config.display_name} — Website",
                    requested_by_agent="dylan",
                    action_type="deploy_site",
                    title=f"Site edit for {config.display_name}",
                    summary=change_description,
                    metadata={
                        "kind": "site_edit",
                        "edit_slug": result.get("edit_slug"),
                        "edit_dir": result.get("edit_dir"),
                        "preview_url": result.get("preview_url"),
                        "change_description": change_description,
                        "target_domain": config.cloudflare_config.production_domain,
                        "production_project": config.cloudflare_config.production_project,
                    },
                )
                result["approval_id"] = approval["id"]
            except Exception:
                logger.exception("Failed to create edit approval for %s", client_id)
        elif tool_name == "init_podcast_parlay_project":
            from app.tools.video_parlay_tools import init_podcast_parlay_project

            result = await init_podcast_parlay_project(
                client_id=tool_input["client_id"],
                episode_slug=tool_input["episode_slug"],
                show_name=tool_input.get("show_name"),
                raw_assets_note=tool_input.get("raw_assets_note"),
            )
        elif tool_name == "generate_video_draft":
            from app.tools.video_parlay_tools import generate_video_draft

            result = await generate_video_draft(
                client_id=tool_input["client_id"],
                episode_slug=tool_input["episode_slug"],
                stage=tool_input.get("stage", "longform_draft"),
                notes=tool_input.get("notes"),
            )
        elif tool_name == "request_video_approval":
            from app.tools.video_parlay_tools import request_video_approval

            result = await request_video_approval(
                client_id=tool_input["client_id"],
                episode_slug=tool_input["episode_slug"],
                stage=tool_input["stage"],
                preview_url=tool_input.get("preview_url"),
                preview_path=tool_input.get("preview_path"),
                summary=tool_input.get("summary"),
            )
        elif tool_name == "record_parlay_decision":
            from app.tools.video_parlay_tools import record_parlay_decision

            result = await record_parlay_decision(
                client_id=tool_input["client_id"],
                episode_slug=tool_input["episode_slug"],
                stage=tool_input["stage"],
                decision=tool_input["decision"],
                notes=tool_input.get("notes"),
            )
        elif tool_name == "get_parlay_status":
            from app.tools.video_parlay_tools import get_parlay_status

            result = await get_parlay_status(
                client_id=tool_input["client_id"],
                episode_slug=tool_input["episode_slug"],
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


def _build_client_preferences_context(client_id: str | None) -> str | None:
    """
    Inject per-client preferences (pronunciation, tone) into Nathan's system prompt.

    Loaded from client_artifacts/<client_id>/config.yaml. Returns None when no
    client_id is bound (e.g. local dev with no header) or when the client's
    config has no preferences worth mentioning — letting the caller skip the
    block entirely rather than emitting an empty section.
    """
    if not client_id:
        return None
    try:
        config = load_client_config(client_id)
    except ClientConfigError as exc:
        logger.warning("Skipping client preferences for %r: %s", client_id, exc)
        return None

    lines = [f"ACTIVE CLIENT: {config.display_name} (client_id: {config.client_id})."]
    lines.append(
        "Use this client_id for get_project_context and save_meeting_notes "
        "unless the client themselves names a different one out loud."
    )
    for word, spoken in config.preferences.pronunciation.items():
        lines.append(
            f'Pronunciation: when you say "{word}" aloud, render it as "{spoken}" '
            f"so the text-to-speech voices it correctly."
        )
    if config.preferences.tone:
        lines.append(f"Tone notes for this client: {config.preferences.tone}")
    return "\n".join(lines)


def _openai_messages_to_anthropic(
    messages: list[dict[str, Any]],
    *,
    client_id: str | None = None,
    surface: str = "tavus",
) -> tuple[str, list[dict[str, Any]]]:
    """
    Convert OpenAI-format messages to Anthropic format.
    Returns (system_prompt, anthropic_messages).
    Merges any system messages from Tavus with our Nathan prompt.

    Prepends a CURRENT DATE context block so Nathan knows what "today"
    means and can resolve relative date references in real time.

    If `client_id` is set, also prepends per-client preferences (pronunciation,
    tone) loaded from client_artifacts/<client_id>/config.yaml.

    `surface` picks the response-style rules:
      - "tavus"      → voice rules (no markdown, narrate-during-tool-calls)
      - "teams_chat" → text rules (markdown OK, no narration, async)
    Defaults to "tavus" for backwards compat.
    """
    system_parts: list[str] = [_build_current_date_context()]
    client_prefs = _build_client_preferences_context(client_id)
    if client_prefs:
        system_parts.append(client_prefs)
    # Workflow packages (like viktor.com "different packages of workflows"): inject active ones' prompts + spec refs.
    # This makes Nathan follow the living package specs (e.g. Podcast Parlay MD) when activated for the client.
    from app.workflow_packages import inject_package_context
    packages_block = inject_package_context(client_id, "")
    if packages_block:
        system_parts.append(packages_block)
    system_parts.append(NATHAN_BASE_SYSTEM)
    system_parts.append(_build_surface_rules(surface))

    # === NEW: Inject explicit conversation history guidance when prior turns exist ===
    if len(messages) > 1:
        system_parts.append(CONVERSATION_HISTORY_GUIDANCE)

    anthropic_msgs: list[dict[str, Any]] = []

    history_label_added = False
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            # Tavus injects the persona's system_prompt as a system message
            # Append it after our base prompt so persona context is preserved
            if content and content.strip():
                system_parts.append(f"\n\n[ADDITIONAL CONTEXT FROM PERSONA SETUP]\n{content}")
            continue

        # === NEW: Label the start of conversation history for clarity ===
        if len(messages) > 1 and not history_label_added and i == 0:
            # First message in a multi-turn list is the oldest history turn
            labeled_content = (
                "[PREVIOUS CONVERSATION CONTEXT - This is what was discussed earlier in this thread. "
                "The user is referring back to this.]\n" + content
            )
            anthropic_msgs.append({"role": role, "content": labeled_content})
            history_label_added = True
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
    client_id: str | None = None,
    surface: str = "tavus",
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
    system_prompt, messages = _openai_messages_to_anthropic(
        openai_messages, client_id=client_id, surface=surface
    )
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
    client_id: str | None = None,
    surface: str = "tavus",
    max_tool_rounds: int = 5,
) -> str:
    """
    Non-streaming wrapper: collect every text chunk from the streaming
    generator and join them. Used by the non-streaming /v1/chat/completions
    path, the Teams chat path, and tests. Preserves the original API for
    callers that just want one string back.
    """
    chunks: list[str] = []
    async for chunk in run_nathan_conversation_streaming(
        openai_messages,
        client_id=client_id,
        surface=surface,
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
