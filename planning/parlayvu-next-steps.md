# ParlayVU Core — Planning Document (May 2026)

**Status:** Initial exploration complete. In planning mode.  
**Repo:** C:\Users\DavidBaker\projects\parlayvu-core (cloned 2026-05-28)  
**Explorer:** Grok (planning mode)  
**Goal:** Identify the highest-value next work, evaluate approaches, and produce an approved, concrete implementation plan.

---

## 1. Current State Snapshot (Post-Exploration)

### Strengths (what the codebase does very well)
- **Documentation culture** is exceptional: ROADMAP.md, ARCHITECTURE.md, DECISIONS.md, AGENTS.md, scoped docs under `docs/`, client-specific runbooks. Decisions are recorded with "why", rejected alternatives, and revisit triggers.
- **Safety & auditability first**: Approvals system is a first-class primitive. Almost every client-facing or destructive action (site deploy, email draft, meeting note publish) goes through request → human decision → record.
- **Explicit context everywhere**: `client_id` + `project_id` are threaded pervasively and intentionally. Per-client `client_artifacts/<id>/config.yaml` + Tavus persona + Teams bindings + brand voice is a strong multi-tenant foundation (recent Track 2 win).
- **Pragmatic architecture choices** are well justified (document-dumping vs RAG today, one Nathan brain across surfaces, Tavus CVI choice, no premature LangGraph complexity).
- **Multi-surface design** (Tavus /v1/chat/completions + Teams Bot Framework + HeyGen scaffold + future) with thin adapters on top of shared logic.
- **Windows-friendly tooling**: Many PowerShell setup scripts, good for the primary dev environment.

### Current Architecture (condensed)
- FastAPI + LangGraph (very thin one-hop router today: Nathan → specialist or END).
- SQLAlchemy 2.0 models for project memory (Client → Project → SourceAsset / GeneratedOutput / Approval / AgentEvent / TeamsChannelBinding).
- Database currently bootstrapped with `Base.metadata.create_all()` (explicitly marked as scaffold; Alembic called out repeatedly as required for prod).
- No conversational memory / turn history today. `AgentEvent` is audit log only.
- Dylan (site generation) is special-cased and calls out to Node + Wrangler subprocesses.
- Most specialist agents are one-shot LLM calls; only Dylan has real "tools".
- Graph is stateless per request (`ainvoke` with fresh state each time).

### Open / High-Signal Items from ROADMAP.md (as of 2026-05-27)
- **Track 4.5** — Default to bound `client_id` in Nathan tool calls (small correctness fix, partially validated).
- **Track 5 Phase A** — Cross-session conversation memory for Teams (schema sketched, integration points in `_handle_teams_message` identified, ~2hr estimate). Phase B for Tavus deferred.
- **Track 6** — Phoenix-4 avatar upgrade (blocked on Tavus GA).
- Deferred items with clear triggers: RAG, native Teams video + screen share (4-5wk scoping doc exists), per-agent avatars, action-item dispatch pipeline, Planner integration, etc.
- Hardening / identity hygiene items (CORS, secret rotation, `nathan@parlayvu.ai` Global Admin awkwardness).

---

## 2. Highest-Value Planning Candidates

After code + doc exploration, these four tracks stand out as the most impactful places to invest planning effort right now. They are ordered roughly by "readiness to plan + leverage".

### Candidate A: Cross-Session Conversation Memory (Track 5 Phase A — Teams)
**Why now:** Explicitly the next committed item. Schema and rough integration points already written in ROADMAP. Directly improves Nathan's "I asked you a question last turn" problem in real Teams channels. Unblocks better coaching and continuity.

**Rough scope**
- New `ConversationTurn` model (or reuse/extend AgentEvent).
- `app/conversation_memory.py` with `load_recent_turns` + `append_turn`.
- Wire into Teams message path (and optionally the generic `_run_nathan_request`).
- Test updates + a cross-naming regression test.
- TTL / cleanup strategy.
- Consideration: surface-specific rules (Teams vs Tavus) for what gets stored.

**Effort estimate (from roadmap):** ~2 hours for Phase A.
**Risk / unknowns:** How much history to inject (token budget), summarization vs raw turns, deduping user answers to prior questions.

**Recommended approach if chosen:** Start with a minimal append-only turns table scoped by `(client_id, conversation_id)`. Keep the injection simple (last N turns as "Recent conversation context" in the system prompt for that surface). Make it opt-in via env flag initially.

### Candidate B: Proper Database Migrations + Production Data Safety
**Why now:** Mentioned in almost every major doc as a hard prerequisite before real client data or production. Current `initialize_database()` + `create_all()` is a known temporary scaffold. Adding tables for conversation memory (Candidate A) makes this more urgent.

**Rough scope**
- Introduce Alembic (or SQLAlchemy-Alembic integration).
- Initial migration for existing models + any new ones.
- Update all seeding / demo scripts and `initialize_database` call sites (or deprecate it).
- Guidance / guardrails in docs for "local vs prod" DB usage.
- Optional: lightweight migration test or CI check.

**Effort estimate:** 4–8 hours (mostly one-time setup + docs).
**Risk / unknowns:** Existing demo data in Neon instances; coordination with Azure Container App deploys.

**Recommended approach if chosen:** Standard Alembic setup with `alembic init`, autogenerate for the current models, a "bootstrap" migration, and clear instructions in SETUP.md + README for both local Postgres and Neon.

### Candidate C: Local Developer Experience Overhaul
**Why now:** Onboarding a new person (or yourself on a new machine) to this sophisticated system is still quite manual. The gap between "clone" and "I can run a full Nathan simulation with memory" is large. This would dramatically increase velocity for future work.

**Rough scope (pick 2–3 of these)**
- `docker-compose.yml` that brings up a local Postgres + the API (with volume mounts).
- One-command local setup script / Makefile / taskfile (`dev:up`, `seed`, `test`, `migrate`).
- Better `.env` handling + validation on startup (pydantic-settings or similar).
- Test database isolation + fixtures for the heavy integration tests.
- Improved Dylan local dev (avoid full npm/wrangler every time?).
- Documentation: "Day 0" contributor guide that actually works end-to-end on Windows.

**Effort estimate:** 1–3 days depending on depth.
**Risk / unknowns:** Docker Desktop on the primary machine, Windows path / permission issues with Node + Wrangler in containers.

**Recommended approach if chosen:** Prioritize a working `docker compose up` that gives a hot-reloading API + seeded local DB. Keep the existing PowerShell Azure scripts as the prod path.

### Candidate D: Nathan Tool-Calling & Client Context Hardening (Track 4.5 + related)
**Why now:** Small surface area, high correctness impact. Nathan still occasionally leaks across clients in edge cases. The surface-rules prompt work is the current mitigation.

**Rough scope**
- Strengthen `NATHAN_*_SURFACE_RULES` (and specialist prompts) with explicit "you are operating inside client_id=X" language at the very top.
- Add regression tests that cross-name clients while in a bound channel.
- Possibly a lightweight "client context guard" wrapper around tool calls or the router.
- Audit all places that call `get_project_context`, `read_client_file`, etc. for client leakage.

**Effort estimate:** 1–3 hours.
**Risk / unknowns:** Low. Mostly prompt + test work.

---

## 3. Other Notable Areas (Lower Priority for Immediate Planning)

- RAG over client knowledge (only when >30 files or >10 notes per client — not yet triggered).
- Native Teams media bot + screen sharing (large 4–5 week scoped project; excellent scoping doc already exists).
- Dylan / Astro site generation improvements or better local preview story.
- Action item extraction + dispatch pipeline to the 12 specialist agents (big vision item, needs Track 4/5 solid first).
- Security / identity hygiene pass (important, but mostly operational + one-off scripts).

---

## 4. Recommendation & Decision Needed

**My current lean (based on exploration):** Start with a combination of **A + B** (conversation memory + migrations) if the goal is to improve the core "Nathan feels like a real ongoing teammate" experience quickly. These two are tightly coupled and both have very clear existing design notes.

**Alternative:** If the immediate pain is "I want to hack on this thing comfortably every day," then **C** (local dev experience) has the highest day-to-day ROI.

**Please choose (or propose your own direction):**

1. **Focus on Track 5 Phase A (Cross-session memory) + migrations as a paired effort.**
2. **Focus on Local Developer Experience overhaul.**
3. **Focus on the small Track 4.5 client context hardening + surrounding prompt/tool discipline.**
4. **Something else** (e.g., a specific new capability for Nathan/Dylan, work on the `sites/` Astro layer, RAG pilot, Teams media bot next phase, etc. — describe it).

Once you pick, I will expand the chosen candidate(s) into a full, detailed, step-by-step implementation plan (architecture choices, file changes, tests, docs, rollout, risks, success criteria) and present it for final approval via exit_plan_mode.

---

**Next action:** Reply with your choice (or new direction). I can also dive deeper into any candidate or specific file before deciding.

---

*This document lives at `planning/parlayvu-next-steps.md` so it can be version-controlled with the project.*