"""One-shot migration: create the conversation_turns table.

Runs `Base.metadata.create_all(...)` which only creates missing tables —
idempotent for the existing schema, safe to run any time. The conversation
memory feature (load_conversation_history / save_conversation_turn /
reset_conversation_history in app/project_memory.py) silently no-ops when
the table doesn't exist, so until this migration runs the Teams flow keeps
working with no memory. After it runs, Nathan remembers Teams turns.

Usage:
    DATABASE_URL=postgresql://... python scripts/migrate_conversation_turns.py

Or from the Container App via az exec:
    az containerapp exec --name parlayvu-api \\
      --resource-group rg-parlayvu-prod \\
      --command "python scripts/migrate_conversation_turns.py"

When Alembic lands, delete this script and add a real migration revision.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import inspect

from app.database import get_engine, initialize_database


def main() -> int:
    if not os.getenv("DATABASE_URL"):
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 2

    engine = get_engine()
    inspector = inspect(engine)
    before = set(inspector.get_table_names())

    if "conversation_turns" in before:
        print("conversation_turns already exists — nothing to do.")
        return 0

    print(f"Creating missing tables (existing: {len(before)} table(s))...")
    initialize_database(engine)

    after = set(inspect(engine).get_table_names())
    new = after - before
    if "conversation_turns" not in after:
        print("ERROR: conversation_turns was not created.", file=sys.stderr)
        return 1

    print(f"Done. Created {len(new)} new table(s): {sorted(new)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
