# app/tools/teams_files_tool.py
"""
Microsoft Teams file access for Nathan's live meeting tool set.

Nathan can list and read files shared in any Teams channel he has access to,
including project documents, briefs, strategy decks, and client materials.

Uses the same Microsoft Graph app registration as the rest of ParlayVU.
Requires Graph application permissions:
  - Files.Read.All   (to read files across all teams)
  - Sites.Read.All   (to read SharePoint sites backing Teams channels)

Environment variables (already set in Azure for the parlayvu-api Container App):
    TEAMS_TENANT_ID       — Azure AD tenant ID
    TEAMS_CLIENT_ID       — App registration client ID
    TEAMS_CLIENT_SECRET   — App registration client secret
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("parlayvu.tools.teams_files")

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_LOGIN_BASE = "https://login.microsoftonline.com"
_MAX_FILE_CHARS = 10_000  # spoken context cap

# Simple in-process token cache — tokens live ~3600 s
_token_cache: dict[str, Any] = {}


def _graph_creds() -> tuple[str, str, str]:
    tenant = os.getenv("TEAMS_TENANT_ID", "") or os.getenv("TEAMS_MEDIA_BOT_TENANT_ID", "")
    client_id = os.getenv("TEAMS_CLIENT_ID", "") or os.getenv("TEAMS_MEDIA_BOT_APP_ID", "")
    secret = os.getenv("TEAMS_CLIENT_SECRET", "") or os.getenv("TEAMS_MEDIA_BOT_APP_SECRET", "")
    return tenant, client_id, secret


async def _get_graph_token() -> str:
    """Obtain a Microsoft Graph application token (cached)."""
    import time

    cached = _token_cache.get("token")
    expires_at = _token_cache.get("expires_at", 0)
    if cached and time.time() < expires_at - 60:
        return cached

    tenant, client_id, secret = _graph_creds()
    if not all([tenant, client_id, secret]):
        raise RuntimeError(
            "Teams Graph credentials not configured. "
            "Set TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET in Azure."
        )

    token_url = f"{_LOGIN_BASE}/{tenant}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": secret,
        "grant_type": "client_credentials",
        "scope": "https://graph.microsoft.com/.default",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=data)
        resp.raise_for_status()
        payload = resp.json()

    token = payload["access_token"]
    expires_in = payload.get("expires_in", 3600)
    import time as _time
    _token_cache["token"] = token
    _token_cache["expires_at"] = _time.time() + expires_in
    return token


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

    # Get the channel's SharePoint folder
    url = f"{_GRAPH_BASE}/teams/{team_id}/channels/{channel_id}/filesFolder"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Get the folder info first
            resp = await client.get(url, headers=headers)
            if resp.status_code == 403:
                return {
                    "error": "Permission denied. Add Files.Read.All and Sites.Read.All to the "
                             "ParlayVU app registration and grant admin consent.",
                    "files": [],
                }
            resp.raise_for_status()
            folder = resp.json()

            # Get children of the folder
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

    # Build the item URL
    if drive_id:
        item_url = f"{_GRAPH_BASE}/drives/{drive_id}/items/{drive_item_id}"
    else:
        item_url = f"{_GRAPH_BASE}/drive/items/{drive_item_id}"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Get item metadata to check file type
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

            # For Office documents, use Graph's text-conversion endpoint
            is_office = any(
                t in mime for t in [
                    "officedocument", "wordprocessingml", "presentationml",
                    "spreadsheetml", "msword", "vnd.ms-"
                ]
            ) or name.lower().endswith((".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls"))

            if is_office:
                # Export as plain text
                convert_url = f"{item_url}/content?format=txt"
                content_resp = await client.get(convert_url, headers=headers)
                if content_resp.status_code == 200:
                    raw = content_resp.text
                else:
                    # Fall back to direct download
                    download_url = meta.get("@microsoft.graph.downloadUrl")
                    if not download_url:
                        return {"error": "Could not get download URL for Office file.", "content": "", "name": name}
                    content_resp = await client.get(download_url)
                    raw = content_resp.text
            else:
                # Plain text / PDF / other — direct download
                download_url = meta.get("@microsoft.graph.downloadUrl")
                if not download_url:
                    # Try content endpoint
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
