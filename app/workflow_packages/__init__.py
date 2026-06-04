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


def get_active_packages(client_id: str) -> List[WorkflowPackage]:
    """Return packages active for this client based on its config.yaml."""
    try:
        cfg = load_client_config(client_id)
        active_ids = getattr(cfg, "active_workflows", []) or []
    except Exception:
        active_ids = []

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
            "generate_video_draft",
            "request_video_approval",
            "record_parlay_decision",
            "get_parlay_status",
        ],
        prompt_additions=(
            "PODCAST PARLAY & VIDEO PRODUCTION WORKFLOW: Load and follow exactly the spec at "
            "`video_system/docs/PODCAST_PARLAY_FULL_WORKFLOW.md` when the user mentions an interview, "
            "episode, podcast video production, clips, or Riverside. The review gates are the stages "
            "longform_draft → longform_captioned → clips (action_types video_longform_draft, "
            "video_longform_captioned, video_clip_package); request_video_approval derives the "
            "action_type from the stage. Iterate via changes_requested, coordinate with Alex + Resolve "
            "tools. Captioned long-form approval is the hard gate before publishing."
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
        tool_names=["save_meeting_notes", "list_teams_files", "read_teams_file"],
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
        tool_names=["dylan_generate", "dylan_edit", "deploy_client_site"],
        prompt_additions=(
            "CLIENT SITE PACKAGE: Use Dylan's tools (generate variations, edit with direct patch + hardened LLM, "
            "deploy via Cloudflare) for client marketing sites. Follow sites/PARLAYVU_CLIENT_SITES.md and AGENTS.md. "
            "Always produce previews and use approvals before live deploy. Reference client_artifacts for brief/brand."
        ),
    )
)


def get_package(id: str) -> Optional[WorkflowPackage]:
    return KNOWN_PACKAGES.get(id)


# Example: how Nathan or a service would use it
def inject_package_context(client_id: str, base_prompt: str) -> str:
    """Append active packages' prompt_additions + loaded specs to Nathan's prompt."""
    active = get_active_packages(client_id)
    if not active:
        return base_prompt

    additions = []
    for pkg in active:
        additions.append(f"\n\n### ACTIVE PACKAGE: {pkg.name} ({pkg.id})")
        additions.append(pkg.prompt_additions)
        spec = load_spec(pkg)
        if spec:
            # In practice, Nathan is told to load the file via tools rather than embedding whole MD every time
            # (token + freshness). For small packages or key sections we can embed summaries.
            additions.append(f"Primary spec reference: {pkg.spec_path}. Load and follow it for any work in this package.")
    return base_prompt + "\n".join(additions)
