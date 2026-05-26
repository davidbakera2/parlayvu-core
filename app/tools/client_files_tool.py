"""Client-file access for Nathan's live tools.

Nathan calls `list_client_files(client_id, folder=...)` to see what's in a
client's Teams channel Files area, then `read_client_file(client_id, path)`
to pull the contents of a specific file. PDFs, Word docs, and markdown all
come back as plain text — Nathan never sees binary garbage.

Per-client Teams binding (team_id, channel_id) is resolved from
client_artifacts/<client_id>/config.yaml via app.client_config.

Supported file types:
  .md / .txt — decoded as UTF-8
  .pdf       — text extracted via pypdf
  .docx      — text extracted via python-docx (already in requirements.txt)

Output is capped at MAX_FILE_CHARS so a 100-page report doesn't blow Nathan's
context budget. Use list_client_files first to inventory; read_client_file is
for the specific file you decided to read.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.client_config import ClientConfigError, load_client_config
from app.microsoft365 import MicrosoftGraphClient
from app.tools.text_extractors import (
    decode_text as _decode_text,
    detect_extractor as _detect_extractor,
    extract_docx_text as _extract_docx_text,
    extract_pdf_text as _extract_pdf_text,
)

logger = logging.getLogger("parlayvu.tools.client_files")

# Cap so a long PDF doesn't drown Nathan's context window. The same cap
# pattern is used elsewhere (get_project_context, web_tools.fetch_url).
MAX_FILE_CHARS = 30_000


def _ok_text(content: str) -> tuple[str, bool]:
    """Cap content; return (capped_content, truncated)."""
    if len(content) > MAX_FILE_CHARS:
        return content[:MAX_FILE_CHARS], True
    return content, False


async def list_client_files(
    client_id: str,
    folder: str | None = None,
) -> dict[str, Any]:
    """List files and subfolders in a client's Teams channel Files area.

    Args:
        client_id: ParlayVU client id. Resolved to a Teams channel via
            client_artifacts/<client_id>/config.yaml.
        folder: Optional subfolder path relative to the channel's Files root
            (e.g. "Reports" or "03_Deliverables/Meeting Notes"). When omitted,
            lists the root.

    Returns:
        {client_id, folder, items: [{name, kind, size, last_modified, web_url, path}, ...]}
        or {error, items: []} on failure (404, auth, etc.).
        `kind` is "file" or "folder" so the agent can recurse if needed.
    """
    try:
        config = load_client_config(client_id)
    except ClientConfigError as exc:
        return {"error": str(exc), "items": []}

    graph = MicrosoftGraphClient()
    try:
        items = await graph.list_channel_files(
            team_id=config.teams.team_id,
            channel_id=config.teams.channel_id,
            folder_path=folder,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            return {
                "error": f"Folder not found in {config.display_name}'s Teams channel: {folder!r}",
                "items": [],
            }
        return {"error": f"Graph API error {status}", "items": []}
    except Exception as exc:
        logger.exception("list_client_files failed for %s/%s", client_id, folder)
        return {"error": str(exc), "items": []}

    return {
        "client_id": client_id,
        "client_display_name": config.display_name,
        "folder": folder or "",
        "items": items,
    }


async def read_client_file(
    client_id: str,
    relative_path: str,
) -> dict[str, Any]:
    """Read a file from a client's Teams channel and return its text content.

    Args:
        client_id: ParlayVU client id.
        relative_path: File path relative to the channel's Files root
            (e.g. "Reports/Q3-2026.pdf").

    Returns on success:
        {client_id, path, file_type, content, char_count, truncated}
    On failure:
        {client_id, path, error}
    """
    if not relative_path or not relative_path.strip():
        return {"client_id": client_id, "path": "", "error": "relative_path is required"}
    relative_path = relative_path.strip().lstrip("/")

    extractor = _detect_extractor(relative_path)
    if extractor is None:
        return {
            "client_id": client_id,
            "path": relative_path,
            "error": (
                f"Unsupported file type for {relative_path!r}. "
                f"Supported: .md, .txt, .pdf, .docx."
            ),
        }

    try:
        config = load_client_config(client_id)
    except ClientConfigError as exc:
        return {"client_id": client_id, "path": relative_path, "error": str(exc)}

    graph = MicrosoftGraphClient()
    try:
        data = await graph.download_teams_channel_file(
            file_path=relative_path,
            team_id=config.teams.team_id,
            channel_id=config.teams.channel_id,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            return {
                "client_id": client_id,
                "path": relative_path,
                "error": f"File not found in {config.display_name}'s Teams channel.",
            }
        logger.warning("Graph download failed for %s/%s: %s", client_id, relative_path, exc)
        return {
            "client_id": client_id,
            "path": relative_path,
            "error": f"Graph API error {status}",
        }
    except Exception as exc:
        logger.exception("download_teams_channel_file failed for %s/%s", client_id, relative_path)
        return {"client_id": client_id, "path": relative_path, "error": str(exc)}

    try:
        raw_text = extractor(data)
    except Exception as exc:
        logger.warning("Extraction failed for %s/%s: %s", client_id, relative_path, exc)
        return {
            "client_id": client_id,
            "path": relative_path,
            "error": f"Could not extract text: {exc}",
        }

    content, truncated = _ok_text(raw_text)
    file_type = relative_path.lower().rsplit(".", 1)[-1] if "." in relative_path else ""
    return {
        "client_id": client_id,
        "path": relative_path,
        "file_type": file_type,
        "content": content,
        "char_count": len(content),
        "truncated": truncated,
    }
