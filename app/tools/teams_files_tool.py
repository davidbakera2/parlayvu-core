# app/tools/teams_files_tool.py
"""
Microsoft Teams file access for Nathan's live meeting tool set.

Nathan can list and read files shared in any Teams channel he has access to,
including project documents, briefs, strategy decks, and client materials.

This module borrows authentication from `app.microsoft365.MicrosoftGraphClient`,
which is the single source of truth for Graph credentials. There are no env var
lookups here — if you need to change which credentials are used, change them in
`app/microsoft365.py` and the change flows here automatically.

Graph permissions required on the Microsoft 365 app registration:
  - Files.Read.All   (read files across all teams)
  - Sites.Read.All   (read SharePoint sites backing Teams channels)
"""

import logging
from typing import Any

import httpx

from app.microsoft365 import MicrosoftGraphClient

logger = logging.getLogger("parlayvu.tools.teams_files")

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_MAX_FILE_CHARS = 10_000  # spoken context cap


async def _get_graph_token() -> str:
    """Borrow auth from the canonical MicrosoftGraphClient. No env vars here."""
    return await MicrosoftGraphClient().get_access_token()


async def list_teams_files(
    team_id: str,
    channel_id: str,
    *,
    max_items: int = 30,
) -> dict[str, Any]:
    """
    List files available in a Microsoft Teams channel.

    Returns file names, sizes, modification dates, and download URLs.
    Use this to discover what project documents are available before
    reading a specific file.

    Args:
        team_id: The Teams group/team ID (GUID)
        channel_id: The Teams channel ID
        max_items: Maximum files to return (default 30)
    """
    try:
        token = await _get_graph_token()
    except RuntimeError as exc:
        return {"error": str(exc), "files": []}

    url = f"{_GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/filesFolder"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 403:
                return {
                    "error": "Permission denied. Add Files.Read.All and Sites.Read.All to the "
                             "ParlayVU app registration and grant admin consent.",
                    "files": [],
                }
            resp.raise_for_status()
            folder = resp.json()

            drive_id = folder.get("parentReference", {}).get("driveId")
            item_id = folder.get("id")
            if not drive_id or not item_id:
                return {"error": "Could not locate Teams channel drive.", "files": []}

            children_url = (
                f"{_GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children"
                f"?$top={max_items}&$select=id,name,size,lastModifiedDateTime,file,folder,webUrl,@microsoft.graph.downloadUrl"
            )
            children_resp = await client.get(children_url, headers=headers)
            children_resp.raise_for_status()
            children = children_resp.json()

        files = []
        for item in children.get("value", []):
            entry: dict[str, Any] = {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": "folder" if "folder" in item else "file",
                "size_bytes": item.get("size"),
                "modified": item.get("lastModifiedDateTime"),
                "web_url": item.get("webUrl"),
            }
            if "file" in item:
                entry["mime_type"] = item["file"].get("mimeType")
                entry["download_url"] = item.get("@microsoft.graph.downloadUrl")
            files.append(entry)

        return {
            "team_id": team_id,
            "channel_id": channel_id,
            "folder_name": folder.get("name"),
            "total_items": len(files),
            "files": files,
        }

    except httpx.HTTPStatusError as exc:
        logger.warning("Graph files list failed: %s", exc)
        return {"error": f"Graph API error {exc.response.status_code}: {exc.response.text[:300]}", "files": []}
    except Exception as exc:
        logger.exception("Unexpected error listing Teams files")
        return {"error": str(exc), "files": []}


async def read_teams_file(
    drive_item_id: str,
    *,
    drive_id: str | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """
    Read the content of a specific file from Microsoft Teams.

    Works with text files, Word documents (.docx), PowerPoint (.pptx),
    Excel (.xlsx), PDFs, and plain text. Office documents are exported
    as plain text via Graph conversion.

    Args:
        drive_item_id: The file's Graph item ID (from list_teams_files)
        drive_id: The SharePoint drive ID (optional — improves lookup speed)
        file_name: Optional display name for context
    """
    try:
        token = await _get_graph_token()
    except RuntimeError as exc:
        return {"error": str(exc), "content": ""}

    headers = {"Authorization": f"Bearer {token}"}

    if drive_id:
        item_url = f"{_GRAPH_BASE}/drives/{drive_id}/items/{drive_item_id}"
    else:
        item_url = f"{_GRAPH_BASE}/drive/items/{drive_item_id}"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            meta_resp = await client.get(
                item_url,
                headers=headers,
                params={"$select": "name,file,size,@microsoft.graph.downloadUrl"},
            )
            if meta_resp.status_code == 404:
                return {"error": f"File not found: {drive_item_id}", "content": ""}
            meta_resp.raise_for_status()
            meta = meta_resp.json()

            name = file_name or meta.get("name", "unknown")
            mime = meta.get("file", {}).get("mimeType", "")

            is_office = any(
                t in mime for t in [
                    "officedocument", "wordprocessingml", "presentationml",
                    "spreadsheetml", "msword", "vnd.ms-"
                ]
            ) or name.lower().endswith((".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls"))

            if is_office:
                convert_url = f"{item_url}/content?format=txt"
                content_resp = await client.get(convert_url, headers=headers)
                if content_resp.status_code == 200:
                    raw = content_resp.text
                else:
                    download_url = meta.get("@microsoft.graph.downloadUrl")
                    if not download_url:
                        return {"error": "Could not get download URL for Office file.", "content": "", "name": name}
                    content_resp = await client.get(download_url)
                    raw = content_resp.text
            else:
                download_url = meta.get("@microsoft.graph.downloadUrl")
                if not download_url:
                    content_resp = await client.get(f"{item_url}/content", headers=headers)
                    content_resp.raise_for_status()
                    raw = content_resp.text
                else:
                    content_resp = await client.get(download_url)
                    raw = content_resp.text

        content = raw[:_MAX_FILE_CHARS]
        return {
            "name": name,
            "drive_item_id": drive_item_id,
            "mime_type": mime,
            "content": content,
            "truncated": len(raw) > _MAX_FILE_CHARS,
            "char_count": len(content),
        }

    except httpx.HTTPStatusError as exc:
        logger.warning("Graph file read failed: %s", exc)
        return {"error": f"Graph API error {exc.response.status_code}", "content": "", "name": file_name or drive_item_id}
    except Exception as exc:
        logger.exception("Unexpected error reading Teams file %s", drive_item_id)
        return {"error": str(exc), "content": "", "name": file_name or drive_item_id}
