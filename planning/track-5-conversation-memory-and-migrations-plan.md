# Detailed Implementation Plan: Complete Track 5 (Conversation Memory) + Introduce Alembic Migrations

**Track:** ROADMAP Track 5 Phase A (Teams) completion + foundational migrations work  
**Date:** 2026-05-28  
**Status:** Ready for review / approval  
**Owner:** TBD (user + implementer)  
**Related Docs:** ROADMAP.md, ARCHITECTURE.md, app/nathan_llm.py, app/main.py, app/project_memory.py, tests/test_conversation_memory.py

---

## Executive Summary

**Good news:** A large portion of Track 5 Phase A is already implemented and well-tested in isolation:

- `ConversationTurn` model (models.py)
- Full persistence layer: `save_conversation_turn`, `load_conversation_history`, `reset_conversation_history` (project_memory.py)
- Comprehensive unit tests exercising caps (turns/chars/age), client isolation, reset behavior, and disabled-by-default safety
- Reset phrase detector wired in Teams path (`is_conversation_reset_request` in teams.py)
- History loading + saving already active inside `_handle_teams_message` (main.py)
- History is passed through to Claude via the existing `run_nathan_conversation` path and `_openai_messages_to_anthropic`

**Remaining work (the actual "completion" of the track):**

1. **Prompt / UX polish** — Make the replayed history clearly labeled so Nathan treats it as prior context rather than the current conversation. Add light guidance in the Teams surface rules.
2. **Broader surface coverage** — Ensure the generic `/nathan` API path and (optionally) Tavus path can also benefit from explicit history injection where appropriate.
3. **Replace the temporary migration script** with proper Alembic. This is the higher-value, longer-term deliverable that unblocks all future schema work.
4. **Documentation, ROADMAP, and enablement** updates so the feature is no longer "planned" but "shipped for Teams".
5. **Small hardening** around error cases, token budgeting visibility, and observability.

Pairing the memory completion with the introduction of Alembic is the natural and highest-leverage move — adding the table via `create_all` was always intended as a stopgap.

**Estimated effort:** 6–10 focused hours (mostly migrations setup + docs + prompt tweaks + verification). Mostly low-risk.

---

## Current State Details (Post Deep Exploration)

### What Already Works Well
- History is loaded **before** the current user message in the Teams handler.
- Reset commands are detected early and short-circuit with a clean ack.
- Persistence is best-effort and gated by `PROJECT_MEMORY_ENABLED`.
- Excellent test coverage for the storage layer (including nasty edge cases like cross-client isolation on shared conversation_id).
- The `nathan_messages = history + [current]` shape is already correct for chronological replay.

### Gaps & Polish Items
- No explicit "Previous turns in this thread:" wrapper/label around the replayed messages when they reach Claude. Nathan may or may not realize some messages are old.
- The `NATHAN_TEAMS_CHAT_SURFACE_RULES` does not yet mention conversation history or how to reference it.
- The one-off `scripts/migrate_conversation_turns.py` + repeated `initialize_database()` calls across scripts and tests are the exact anti-pattern repeatedly called out in ROADMAP/SETUP/README.
- No Alembic `alembic/` directory or migration history exists yet.
- `run_nathan_conversation` (used by both Teams and the direct API path) receives history, but the Tavus `/v1/chat/completions` path receives whatever Tavus sends (which is correct by design for that surface).
- No observability (logging/metrics) around history length or truncation.

---

## Recommended Approach & Architecture Decisions

### 1. Conversation Memory Polish (small)
- Add a short, stable header block when prepending history in the Teams path (or inside the LLM assembler).
- Extend `NATHAN_TEAMS_CHAT_SURFACE_RULES` with 2–3 sentences on using prior turns.
- Consider a very lightweight `conversation_context` field or just a well-formatted string prefix. Keep it simple — no new summarization step yet.

### 2. Alembic Migrations (the durable foundation)
**Decision:** Use standard Alembic with async-friendly setup if possible, but synchronous is acceptable since the rest of the app is sync SQLAlchemy.

**Conventions we will follow (to match existing high-quality codebase):**
- `alembic.ini` + `alembic/` directory at repo root.
- `script.py.mako` customized lightly if needed.
- One initial migration that creates the full current schema (or a series of small ones that match model evolution).
- `alembic/env.py` that imports `Base` from `app.models` and uses `target_metadata = Base.metadata`.
- Keep `initialize_database()` for tests and very early local bootstrapping, but mark it clearly as "development only".
- Add a `alembic upgrade head` step to the Azure Container App startup or as a documented one-time command.
- Update all call sites (scripts/seed_demo.py, ramair_channel_pilot.py, various tests) to prefer migrations where a real DB is present.

**Alternative considered:** Stay with `create_all()` forever for simplicity.  
**Rejected because:** Every major doc calls this out as unsustainable before real client data. Future schema changes (more memory types, RAG metadata, agent long-term memory, etc.) will become painful.

### 3. Scope Boundaries for This Plan
- **In scope:** Teams conversation memory polish + full Alembic introduction + docs/ROADMAP/test cleanup.
- **Out of scope (future tracks):** Phase B Tavus memory strategy, RAG over conversation history, automatic summarization of old turns, per-agent memory, action item extraction from history.

---

## Detailed Implementation Steps

### Phase 0 — Preparation & Inventory (30–45 min)
1. Create `planning/track-5-conversation-memory-and-migrations-plan.md` (this document) — done.
2. Run the existing conversation memory tests to establish a clean baseline: `python -m pytest tests/test_conversation_memory.py -q`.
3. Inventory every call site of `initialize_database` (already partially done via grep).
4. Read the full current `ConversationTurn` model + all functions in `project_memory.py` that touch it.

### Phase 1 — Prompt & History UX Polish (1–2 hours)
1. In `app/main.py` (or a new small helper in `project_memory.py`), when building `nathan_messages` for Teams, wrap the history with a clear delimiter:
   ```python
   if history:
       history_block = [{"role": "system", "content": "RECENT CONVERSATION HISTORY (most recent last). Use this for continuity. The next message is the current user turn."}]
       + history
       nathan_messages = history_block + [{"role": "user", "content": ...}]
   ```
   (Or do this inside `_openai_messages_to_anthropic` so both surfaces benefit.)
2. Add 3–4 sentences to `NATHAN_TEAMS_CHAT_SURFACE_RULES` explaining:
   - Prior turns may be included.
   - How to reference them naturally ("As we discussed earlier...").
   - That the user sees only the current reply (history is private context).
3. Add a small unit test that the history messages reach the LLM assembler with the expected labels.
4. Optional: Add a log line at INFO level showing `len(history)` turns loaded for a Teams request.

### Phase 2 — Introduce Alembic (3–5 hours — biggest piece)
1. Install Alembic (add to requirements.txt if not present: `alembic>=1.13`).
2. Run `alembic init alembic` at repo root.
3. Edit `alembic/env.py`:
   - Import `from app.models import Base`
   - Set `target_metadata = Base.metadata`
   - Ensure it can run with `DATABASE_URL` from env (same pattern as the rest of the app).
4. Generate the initial migration:
   ```bash
   alembic revision --autogenerate -m "initial schema: clients, projects, conversation_turns, etc."
   ```
   Review the generated migration carefully (it should create all current tables + indexes + the `conversation_turns` table).
5. Create a follow-up tiny migration (or include in the first) that adds any missing indexes/constraints discovered during review.
6. Update `app/database.py`:
   - Keep `initialize_database()` but add a clear docstring: "Development / test helper only. Production uses Alembic."
   - Add a new helper `ensure_migrations_applied()` or simply document the expectation.
7. Update callers:
   - `scripts/seed_demo.py`, `scripts/ramair_channel_pilot.py`, `scripts/migrate_conversation_turns.py` (deprecate or make it a no-op that prints "use alembic now").
   - All test files that call `initialize_database(engine)` — these can stay (in-memory SQLite is perfect for tests).
8. Add a `Makefile` or PowerShell helper (or just document in README) for:
   - `alembic upgrade head`
   - `alembic revision --autogenerate -m "..."` (dev workflow)
9. Update docs:
   - README.md (Local Setup section)
   - SETUP.md (production Azure path)
   - ROADMAP.md (mark Track 5 Phase A complete, note the migration foundation)
   - Add a short "Database Migrations" section in a new or existing doc.

### Phase 3 — Verification & Cleanup (1–2 hours)
1. End-to-end manual test:
   - Fresh local DB (or docker Postgres).
   - Run `alembic upgrade head`.
   - Enable `PROJECT_MEMORY_ENABLED=true`.
   - Send 3–4 messages via the Teams simulator or direct `/teams/messages` endpoint.
   - Verify Nathan correctly references prior turns.
   - Issue a reset command and confirm history is cleared for that conversation only.
2. Run the full test suite (`pytest tests/test_conversation_memory.py` + memory-related tests).
3. Delete or heavily deprecate `scripts/migrate_conversation_turns.py` (or turn it into a thin wrapper that calls `alembic upgrade head`).
4. Update any investor demo runbooks or release checklists that mention DB setup.
5. Add a note in `DECISIONS.md` under the migrations decision (new entry).

### Phase 4 — Optional Nice-to-Haves (if time)
- Lightweight metrics / logging of history token cost or turn count.
- A small admin endpoint or CLI to inspect recent turns for a conversation.
- Better error messages when the `conversation_turns` table is missing but memory is enabled.

---

## Files Expected to Change

**High confidence:**
- `app/main.py` (minor — history wrapper + comments)
- `app/nathan_llm.py` (minor — possible history labeling in assembler)
- `requirements.txt`
- `alembic/env.py` (new)
- `alembic/versions/*.py` (new initial migration(s))
- `app/database.py`
- `README.md`
- `ROADMAP.md`
- `scripts/migrate_conversation_turns.py` (deprecate)
- `scripts/seed_demo.py` and `ramair_channel_pilot.py` (small updates)
- `planning/` docs (this plan + updates)

**Test files:** Mostly no changes needed (already good), possible small additions for prompt labels.

---

## Risks, Mitigations & Trade-offs

| Risk | Likelihood | Mitigation | Owner |
|------|------------|------------|-------|
| Generated Alembic migration has subtle differences from current `create_all()` on Postgres | Medium | Review diff carefully; run against a throwaway Neon branch or local Postgres; keep the one-off script as emergency fallback for one release | Implementer |
| Existing deployed Container Apps have no migration runner in startup | High | Document one-time `az containerapp exec` command + add a startup probe or init container recommendation in SETUP.md | Implementer + ops |
| Prompt changes accidentally make Nathan more verbose on Teams | Low | Test with real sample conversations; keep the added rules concise | Implementer |
| Tests start failing because some test DBs don't have the new table | Low | Tests already use `initialize_database()` which will still create it | — |

**Trade-off:** We are accepting a small increase in operational complexity (Alembic) in exchange for long-term schema safety and the ability to ship future memory features cleanly.

---

## Success Criteria (Definition of Done)

- [ ] `alembic upgrade head` creates a clean, complete schema matching current models on both SQLite and Postgres.
- [ ] A fresh clone + `alembic upgrade head` + `PROJECT_MEMORY_ENABLED=true` + a few Teams-style messages results in Nathan correctly using prior-turn context.
- [ ] Reset command works and only affects the target conversation.
- [ ] All existing tests pass.
- [ ] ROADMAP.md no longer lists Track 5 Phase A as "planned".
- [ ] README and SETUP docs accurately describe the migration workflow for local and prod.
- [ ] The temporary `migrate_conversation_turns.py` is either deleted or clearly marked deprecated.
- [ ] No regressions in the Tavus/live-avatar or generic `/nathan` paths.

---

## Rollout Plan

1. Land the changes in a feature branch.
2. Merge to main.
3. On the next Container App revision deployment, run the one-time `alembic upgrade head` via `az containerapp exec`.
4. Monitor logs for the first few real client Teams threads.
5. Update any internal runbooks / investor demo scripts.

---

## Open Questions for the User (before implementation starts)

1. Do you want the history labeling / prompt guidance to be **Teams-only** or should we also improve the experience when history is passed via the generic API path?
2. Preferred Alembic template style? (Keep it minimal, or add nice headers / down_revision comments?)
3. Any preference on keeping `initialize_database` as a public API for tests forever, or should we make a private `_create_all_for_tests` variant?
4. Should we add a CI step (or just a docs note) that fails if model changes are not accompanied by a new migration?

---

**Ready to implement once approved.** Reply with "approved" + answers to the open questions (or requested changes to this plan), and I can begin execution (or spawn the implementation work).