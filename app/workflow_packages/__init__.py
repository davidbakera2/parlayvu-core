"""
Workflow Packages for parlayvu.ai

This is the foundation for "different packages of workflows" (like viktor.com's capabilities for
outreach, automations, reports, app building, etc.).

A "package" is a reusable, versioned, conversational workflow definition that Nathan (or other
orchestrators) can activate per client. Packages are defined primarily as editable specs (MD)
+ tools + prompts + optional state, not as opaque graphs.

See docs/workflow-packages-design.md for full rationale and comparison to LangGraph Studio.

Current packages (evolving):
- podcast-parlay: video production from Riverside (see video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md)
- meeting-notes: analysis + strategy + follow-ups
- client-site: generation + deploys (Dylan)

Activation: via client_artifacts/<client>/config.yaml `active_workflows: [...]` or runtime commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.client_config import load_client_config


@dataclass
class WorkflowPackage:
    """Definition of one workflow package."""
    id: str
    name: str
    description: str
    spec_path: Optional[Path] = None  # Primary human-editable spec (MD with Mermaid/tables)
    tool_names: List[str] = field(default_factory=list)  # Tools to expose to Nathan when active
    prompt_additions: str = ""  # Text injected into Nathan's system when package active for the context
    state_class: Optional[Any] = None  # Optional custom state (e.g. parlay_state extension)
    config_schema: Optional[Dict[str, Any]] = None  # JSON schema for per-client config
    # Future: ui_component, schedule_handlers, etc.


# Registry of known packages. Populated at import / startup.
# In production this could be dynamic (DB + file discovery) or plugin-loaded.
KNOWN_PACKAGES: Dict[str, WorkflowPackage] = {}


def register_package(pkg: WorkflowPackage) -> None:
    if pkg.id in KNOWN_PACKAGES:
        raise ValueError(f"Duplicate package id: {pkg.id}")
    KNOWN_PACKAGES[pkg.id] = pkg


def get_active_packages(client_id: Optional[str]) -> List[WorkflowPackage]:
    """Return the packages active for this client based on its config.yaml.

    Backward-compatibility rule: a client whose config omits `active_workflows`
    entirely (active_workflows is None) is treated as "all packages active", so
    migrating to the package model never silently removes a capability a client
    already relied on. An explicit empty list means "no packages". A client_id we
    can't resolve (None / no config) also falls back to all packages.
    """
    active_ids: Optional[List[str]] = None
    if client_id:
        try:
            active_ids = load_client_config(client_id).active_workflows
        except Exception:
            active_ids = None

    if active_ids is None:
        return list(KNOWN_PACKAGES.values())
    return [KNOWN_PACKAGES[i] for i in active_ids if i in KNOWN_PACKAGES]


def load_spec(pkg: WorkflowPackage) -> Optional[str]:
    """Load the primary spec for a package (for Nathan to follow exactly)."""
    if not pkg.spec_path or not pkg.spec_path.exists():
        return None
    return pkg.spec_path.read_text(encoding="utf-8")


# --- Built-in package registrations (examples; expand here or via discovery) ---

# Podcast Parlay - the canonical example. Spec is the living MD; tools registered separately
# in nathan_llm when context matches (see video_parlay_tools + prompt in nathan_llm).
register_package(
    WorkflowPackage(
        id="podcast-parlay",
        name="Podcast Parlay",
        description="Turn raw Riverside 3-track interviews + b-roll into professional long-form video + 5-10 clips with approvals, captions gate, YouTube publish.",
        spec_path=Path("video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md"),
        tool_names=[
            "init_podcast_parlay_project",
            "generate_video_plan",
            "generate_video_draft",
            "request_video_approval",
            "record_parlay_decision",
            "get_parlay_status",
        ],
        prompt_additions=(
            "PODCAST PARLAY & VIDEO PRODUCTION WORKFLOW (Long-form interviews + clips):\n"
            "You are the persistent orchestrator for turning raw Riverside interviews (host + 1-2 guests) "
            "+ client-identified b-roll into polished, branded long-form video + 5-10 short clips.\n"
            "**Primary reference (load and follow exactly when a client mentions an interview, episode, "
            "podcast video, clips, or 'the video we just recorded'):** "
            "`video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md` — the full step-by-step, the Mermaid "
            "flow, roles (you + Alex for visuals, Resolve for execution), and where the approval gates "
            "and revision loops live.\n"
            "Key principles:\n"
            "- Assets and plan live in `video_system/projects/<Client>/<Show_EpXX>/`. Use file tools + "
            "project context to inspect planning/video_plan.json, assets/, renders/, PROJECT_README.md.\n"
            "- You do NOT edit yourself. You coordinate: scaffold, trigger draft generation, call Resolve "
            "tools (once wired), produce previews, and gate everything client-facing with approvals.\n"
            "- The review gates (stages you call generate_video_draft + request_video_approval on) are "
            "exactly: longform_draft → longform_captioned → clips. request_video_approval derives the "
            "approval action_type from the stage (longform_draft → video_longform_draft, "
            "longform_captioned → video_longform_captioned, clips → video_clip_package). Don't invent "
            "other stage names — the tools validate against this list.\n"
            "- Planning first: once the project is initialized and the transcript + footage are in "
            "place, call generate_video_plan to draft planning/video_plan.json from the transcript "
            "(scenes, layouts, lower-thirds, b-roll). Show the user the scene list + assumed speaker "
            "map and let them adjust before rendering.\n"
            "- Flow: render longform_draft → request_video_approval. After approval, render "
            "longform_captioned → request_video_approval. Captioned approval is the hard gate that "
            "unlocks publishing the long-form. The clip package (stage='clips') follows the same pattern.\n"
            "- Iteration is the heart of it: 'changes_requested' + decision_notes come back from the "
            "client (Teams card decisions flow into the state machine automatically; in chat call "
            "record_parlay_decision yourself). On changes_requested you stay in the same stage — read the "
            "notes + plan + transcript, dispatch Alex or instruct Resolve, then re-render a new version "
            "(v2/v3...) and request approval again. Fully auditable.\n"
            "- After the captioned long-form is approved: prepare description + thumbnail + end card, then "
            "publish (YouTube unlisted). Publishing is hard-gated by the matching approved approval.\n"
            "- For visuals (cuts, layouts, b-roll, thumbnails, captions presentation) lean on Alex. You "
            "stay the client-facing single point of contact who files approvals and memory.\n"
            "- Tie video work to the correct client_id/project so approvals, memory, and files line up.\n"
            "- The workflow doc is upgraded after every real episode — propose edits when you learn "
            "something, rather than rebuilding graphs."
        ),
    )
)

# Meeting notes package (reuses existing services)
register_package(
    WorkflowPackage(
        id="meeting-notes",
        name="Meeting Notes & Actions",
        description="Process meeting transcripts into structured notes, strategy, action items, follow-ups, and CRM updates with approvals.",
        spec_path=Path("docs/MEETING-NOTES-TEMPLATE-GUIDE.md"),  # or dedicated spec
        # Only the genuinely meeting-notes-specific tool is gated here. Generic
        # file readers (list_teams_files / read_teams_file / list_client_files)
        # stay base tools — they're used across every workflow.
        tool_names=["save_meeting_notes"],
        prompt_additions=(
            "MEETING NOTES PACKAGE: When active, after Tavus or Teams meeting, use the meeting_notes_service "
            "and workflow to produce notes + strategy. Gate publishing with approvals. Reference client brief "
            "and previous notes for context."
        ),
    )
)

# Client site generation (Dylan)
register_package(
    WorkflowPackage(
        id="client-site",
        name="Client Site Generation",
        description="From brief + brand assets, generate, iterate, and deploy professional Astro marketing sites (Cloudflare Pages + Resend contact).",
        tool_names=["dylan_generate_variations", "dylan_edit_active_site"],
        prompt_additions=(
            "CLIENT SITE PACKAGE: Use Dylan's tools (generate variations, edit with direct patch + hardened LLM, "
            "deploy via Cloudflare) for client marketing sites. Follow sites/PARLAYVU_CLIENT_SITES.md and AGENTS.md. "
            "Always produce previews and use approvals before live deploy. Reference client_artifacts for brief/brand."
        ),
    )
)


def get_package(id: str) -> Optional[WorkflowPackage]:
    return KNOWN_PACKAGES.get(id)


def inject_package_context(client_id: Optional[str], base_prompt: str, surface: str = "teams_chat") -> str:
    """Append active packages' prompt guidance to Nathan's system prompt.

    Surface-aware (DECISIONS #7): on the Tavus voice surface we inject only a
    terse one-line pointer per package (the full markdown prose would violate the
    voice rules and bloat the low-latency path); on text surfaces we inject the
    full prompt_additions + a spec reference.
    """
    active = get_active_packages(client_id)
    if not active:
        return base_prompt

    additions: List[str] = []
    for pkg in active:
        if surface == "tavus":
            additions.append(
                f"\nActive workflow package: {pkg.name} ({pkg.id}). "
                f"Follow its spec ({pkg.spec_path}) when the work calls for it."
            )
        else:
            additions.append(f"\n\n### ACTIVE PACKAGE: {pkg.name} ({pkg.id})")
            additions.append(pkg.prompt_additions)
            if pkg.spec_path:
                additions.append(
                    f"Primary spec reference: {pkg.spec_path}. Load and follow it for any work in this package."
                )
    return base_prompt + "\n".join(additions)


# Tools owned by *some* package (gatable). Computed lazily so it always reflects
# the current registry. A tool not owned by any package is a base tool — always
# available regardless of which packages a client has active.
def _package_owned_tool_names() -> set:
    owned: set = set()
    for pkg in KNOWN_PACKAGES.values():
        owned.update(pkg.tool_names)
    return owned


def build_nathan_tools(client_id: Optional[str], all_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter Nathan's full tool list down to what this client should see.

    Base tools (not owned by any package) are always included. A package-owned
    tool is included only if a package that declares it is active for the client.
    Un-migrated clients (active_workflows omitted) get all packages active, so
    this is a no-op for them until they opt into a specific subset.
    """
    owned = _package_owned_tool_names()
    allowed = set()
    for pkg in get_active_packages(client_id):
        allowed.update(pkg.tool_names)
    return [t for t in all_tools if t.get("name") not in owned or t.get("name") in allowed]
