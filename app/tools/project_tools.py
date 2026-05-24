# app/tools/project_tools.py
"""
ParlayVU project context tool for Nathan's live meeting conversations.

Nathan can pull in the current client's project brief, source assets,
deliverables, approvals, and performance snapshots during any meeting.
This grounds him in real project facts without him having to hallucinate.

Falls back to flat-file client artifacts (client_artifacts/<client_id>/*)
when the database is not available or the client/project is not found there.
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("parlayvu.tools.project")

_ARTIFACTS_ROOT = Path("client_artifacts")
_MAX_FILE_CHARS = 6_000


def _read_artifact(path: Path, max_chars: int = _MAX_FILE_CHARS) -> str:
    """Read a file, returning truncated content with a note if truncated."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + f"\n... [truncated at {max_chars} chars]"
        return text
    except Exception as exc:
        return f"[Could not read {path.name}: {exc}]"


def _flat_file_context(client_id: str, project_id: str | None) -> dict[str, Any]:
    """
    Load context from client_artifacts/<client_id>/ flat files.
    This is the fallback when the database is unavailable or empty.
    """
    client_dir = _ARTIFACTS_ROOT / client_id
    if not client_dir.exists():
        return {"source": "flat_files", "found": False, "client_id": client_id}

    sections: dict[str, str] = {}

    # Standard artifact folders in the ParlayVU client structure
    folder_map = {
        "00_Client_Brief": "brief",
        "01_Source_Material": "source_material",
        "02_Planning": "planning",
        "03_Deliverables": "deliverables",
        "04_Approvals": "approvals",
        "05_Performance": "performance",
    }

    for folder, section_key in folder_map.items():
        folder_path = client_dir / folder
        if not folder_path.exists():
            continue
        folder_texts = []
        for f in sorted(folder_path.rglob("*.md"))[:3]:  # top 3 .md per folder
            folder_texts.append(f"### {f.name}\n{_read_artifact(f, 3000)}")
        if folder_texts:
            sections[section_key] = "\n\n".join(folder_texts)

    # Also grab any standalone .md files in the root
    root_mds = [
        f for f in client_dir.glob("*.md")
        if f.name not in ("README.md",)
    ]
    for f in sorted(root_mds)[:2]:
        sections[f.stem] = _read_artifact(f, 2000)

    return {
        "source": "flat_files",
        "found": True,
        "client_id": client_id,
        "project_id": project_id,
        "sections": sections,
    }


async def get_project_context(
    client_id: str,
    project_id: str | None = None,
    *,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """
    Get the project brief, deliverables, and context for a ParlayVU client.

    Returns the client's brand voice summary, project objectives, source
    materials, current deliverables, approvals, and performance data.

    Grounds Nathan in real project facts so he never has to guess about
    what's been agreed, what's in scope, or what the client cares about.

    Args:
        client_id: e.g. "ramair"
        project_id: optional specific project ID within the client
        sections: optional list of specific sections to return
                  (brief, planning, deliverables, approvals, performance)
                  defaults to all sections
    """
    # Try database first
    try:
        from app.project_memory import get_project_context as db_get
        from app.database import session_scope

        with session_scope() as db_session:
            db_result = db_get(
                db_session,
                client_id=client_id,
                project_id=project_id,
            )
        if db_result and db_result.get("client"):
            # Filter to requested sections if specified
            if sections:
                db_result = {k: v for k, v in db_result.items() if k in sections or k in ("client", "project")}
            db_result["source"] = "database"
            return db_result
    except Exception as exc:
        logger.debug("Database project context unavailable: %s", exc)

    # Flat-file fallback
    result = _flat_file_context(client_id, project_id)
    if sections and "sections" in result:
        result["sections"] = {k: v for k, v in result["sections"].items() if k in sections}
    return result
