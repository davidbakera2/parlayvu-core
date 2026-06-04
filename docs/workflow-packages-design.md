# Workflow Packages for parlayvu.ai (like viktor.com)

**Date:** 2026-06-03
**Status:** Draft design — this document is the *target*, not a description of what's built.
**Related:** PODCAST_PARLAY_FULL_WORKFLOW.md (example package), ARCHITECTURE.md, DECISIONS.md, app/nathan_llm.py, client_artifacts/*/config.yaml, video_parlay_tools.py

> **Build status (2026-06-03):** What actually exists today is the foundation in
> `app/workflow_packages/__init__.py` (`WorkflowPackage` dataclass, `KNOWN_PACKAGES`
> registry, `inject_package_context`) plus the `active_workflows` config flag. The
> `registry.py`, `base.py`, and per-package directories named below were **not**
> created — that logic was inlined into `__init__.py`. Conditional tool registration
> and the `/workflows/*` endpoints are **not** built; prompt injection is currently
> unconditional and surface-agnostic. See DECISIONS.md #11 "Status as built" for the
> authoritative gap list. Treat the file names and roadmap below as the plan to grow
> into, not a map of the current tree.

## Goal
Make parlayvu.ai the platform where teams "hire" Nathan (the AI coworker in Teams/Slack/Tavus) and activate different **pre-packaged workflows** ("packages") for recurring business processes.

Inspired by viktor.com:
- Conversational activation: "@Nathan run the Podcast Parlay for last week's interview" or "set up the Ad Audit package for this client".
- Packages are self-contained, repeatable, with their own steps, gates (approvals), artifacts, specialists.
- Examples of packages (current + future):
  - `podcast-parlay`: Riverside interview → longform + clips production (current MD spec + tools + Resolve).
  - `client-site-generation`: Brief + assets → Astro site scaffold + Dylan edits + deploy (via /dylan, sites/ template).
  - `meeting-notes-and-actions`: Auto from Tavus/Teams → structured notes + follow-ups + CRM update.
  - `ad-spend-audit`: Connect ads accounts → analysis + PDF report + recommendations.
  - `content-repurposing`: Longform video/transcript → clips, social posts, emails (Dylan + specialists).
  - Future: lead research, proposal generation, performance reporting, etc.
- "Different packages of workflows": Marketplace/catalog in parlayvu.ai, per-client activation/config, versioned, upgradable.
- Execution: Nathan orchestrates using the package's spec, tools, state. Human gates via existing approvals. Real outputs (files, deploys, posts).
- No heavy visual graph editor for end users (aligns with viktor.com's "the workflow is the prompt" + our experience).

## Why NOT LangGraph Studio (or heavy LangGraph graphs) for the package system

From our experience building the first package (Podcast Parlay) and explicit docs:

- **Editability & ownership**: The core of a package is a living, human-readable spec (Markdown with Mermaid + tables for phases, actors, artifacts, approvals). Users (us + clients) edit in editor at 2am, commit, Nathan picks it up. LangGraph Studio locks logic in nodes/edges/state that require dev + Studio to inspect/edit. Small changes become "broken" in Studio per past feedback.

- **Viktor.com alignment**: Viktor deliberately has "No workflow builder. No graph editor. The workflow is the prompt." Packages are activated conversationally. Our Nathan + tool loop + spec loading does exactly that. Introducing Studio would be the opposite of what makes viktor successful and what our users (from history) want.

- **Version control & collaboration**: MD + Python tools + git = diffs, branches, PR reviews, A/B per client (branch the spec). Studio graphs are not first-class in git in the same ergonomic way; deployment to LangGraph Cloud adds infra we don't need for most packages.

- **Integration with existing primitives**: Our approvals system, project memory (client_artifacts + DB), Teams cards, parlay_state FSM, Nathan's single brain are already the "durable human gate + revision loop" mechanism. LangGraph persistence/human-in-loop would duplicate or conflict unless we rebuild everything on top of it (premature complexity we rejected in DECISIONS/ARCHITECTURE).

- **Current LangGraph usage (thin, good)**: We use LangGraph lightly for:
  - Thin router (app/graph.py): Nathan routes to specialist or END.
  - Small internal graphs (e.g. meeting_strategy.py: Blake analysis → Nathan strategy).
  This is fine for *internal specialist coordination*. Not for defining customer-facing "packages of workflows".

- **When LangGraph/Studio could be used**:
  - For a *specific complex package* that needs branching state machines (e.g. a multi-step engineering calc package from the other viktor.ai). Even then, wrap it behind a "package" facade (MD spec + tools that invoke the graph).
  - Dev-time debugging of a sub-graph.
  - But the *platform* of packages stays spec-driven, not graph-studio-driven.

**Decision (to record in DECISIONS.md):** Workflow packages are defined as (spec MD + prompt additions + tool bindings + optional state machine + UI/config). Nathan loads active packages per client/context and follows the spec. LangGraph used only for thin routing or encapsulated sub-logic inside a package. No LangGraph Studio as the authoring/deploy surface for packages.

**Revisit triggers:**
- A package genuinely requires visual branching that can't be expressed clearly in MD + code.
- LangGraph Cloud/Studio adds unique deployment/scaling value we can't match with our FastAPI + Azure.
- User demand for a "canvas" editor (unlikely given viktor feedback and our history).

## Package Anatomy (generalizing the Podcast Parlay example)

A package lives in `app/workflow_packages/<package_id>/` or referenced via paths:

- `spec.md`: The living doc (like PODCAST_PARLAY_FULL_WORKFLOW.md). Sections for phases, approvals, iteration, roles. Top Mermaid for overview. "How to develop/modify" section.
- `prompt_additions.txt` or in nathan_llm: Instructions for Nathan: "When this package is active for client X, load and follow `.../spec.md`. Use these tools: ..."
- `tools.py`: LangChain tools (or our tool schema) specific to the package (e.g. init_podcast_parlay_project, generate_video_draft, request_video_approval). Registered conditionally.
- `state.py` (optional): Per-package state machine or extensions to parlay_state (e.g. episode stages, iterations with previews).
- `config.schema.json`: For per-client activation params (e.g. "youtube_playlist_id", "default_broll_folder").
- `ui/`: Dashboard cards, approval templates, config forms (for parlayvu.ai frontend).
- `tests/`: Example episodes or smoke tests.

Activation:
- In `client_artifacts/<client>/config.yaml`: `active_workflows: ["podcast-parlay", "meeting-notes"]`
- Or via command: "@Nathan activate the Podcast Parlay package for RamAir, with show=Straight_From_The_Hart"
- Nathan's context includes active packages; tools/prompts are filtered/added accordingly.
- Registry in `app/workflow_packages/registry.py` discovers and loads them (similar to agents/registry.py).

Execution flow (Nathan):
1. User mentions package or context implies it.
2. Load spec (file read tool or pre-cached in prompt).
3. Use package tools for actuation (scaffolding, render triggers, approvals).
4. Coordinate specialists (Alex for visuals).
5. Gate with approvals (existing system).
6. Update memory/artifacts.
7. Upgrade the package spec after real use.

## Implementation Roadmap (execute now)

1. **Foundation (this session)**:
   - Create `app/workflow_packages/` with `__init__.py`, `registry.py` (load from config + discover specs), `base.py` (PackageSpec dataclass).
   - Extract/generalize the Podcast Parlay as first package (move tools to `workflow_packages/podcast_parlay/tools.py`, keep spec where it is or symlink).
   - Add "meeting-notes" as second simple package (reuse existing meeting_notes_service).
   - Update nathan_llm.py system prompt + tool registration to be package-aware (load active from client config).
   - Add to client config schema.

2. **Platform surface (parlayvu.ai)**:
   - Backend endpoints: `/workflows/packages` (list), `/clients/{id}/workflows` (activate/deactivate/configure).
   - Simple dashboard (extend existing /parlays/dashboard or new Astro/TSX under sites or new frontend).
   - Per-package "install" creates the client_artifacts scaffolding + config entry.

3. **More packages**:
   - "client-site": Dylan + sites/ template.
   - "ad-audit": web tools + report gen + PDF.
   - "content-repurpose": from longform to clips/social.

4. **Polish**:
   - Versioning for packages (git tags or in spec).
   - "Heartbeat"/scheduled for proactive packages (like viktor).
   - Approval templates per package.
   - Docs: update AGENTS.md, ARCHITECTURE, this file.

5. **LangGraph policy**:
   - Keep thin router.
   - For a new package that needs complex state, implement its internal logic as a small LangGraph (like meeting_strategy) *inside* the package, exposed via tools. Never surface the graph to package authors/users.

## Comparison to viktor.com

- Same: Conversational (in chat), real execution + deliverables, approvals, integrations (M365 focus for us), packages/capabilities for different work, proactive, team context, no user graph editing.
- Our differentiation: Deep vertical in marketing/video production for agencies (Podcast Parlay + sites + Nathan avatar in meetings), tight MS365/Teams integration, existing approvals + memory + client artifacts model, Resolve for creative video, Astro for sites. "Packages" are production-grade (with Resolve, Cloudflare, etc.).
- Tech: We stay Python/FastAPI + Claude tool loops + custom durable state (easier than full LangGraph for our scale and editability needs). Add LangGraph subgraphs only where branching payoff is high.

## Next Actions (use todo)

- [ ] Implement basic registry + package awareness in Nathan.
- [ ] Scaffold 2-3 packages.
- [ ] Add UI endpoints + update investor pitch narrative for "workflow packages".
- [ ] Record this decision in DECISIONS.md.
- [ ] Test end-to-end with existing Podcast Parlay on a client.

This keeps us aligned with "easy to develop/view/manage/upgrade this workflow" (user requirement from history) while scaling to a full platform like viktor.

## References
- viktor.com/product: conversational, no builder, real work across tools, packages via categories + automations.
- Our PODCAST_PARLAY... : the template for what a package looks like.
- Current thin LangGraph use.
