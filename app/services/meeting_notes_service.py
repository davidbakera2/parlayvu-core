# app/services/meeting_notes_service.py
"""
Meeting notes publishing service.

This module owns the actual work of taking a meeting title + summary and
producing two artifacts (markdown and DOCX) in a Teams channel folder,
plus the project-memory and audit-log bookkeeping that accompanies it.

It is called from two places:

  1. The HTTP endpoint POST /m365/files/meeting-notes, via
     main._publish_files_meeting_note (which is now a thin wrapper).

  2. Nathan's save_meeting_notes Tavus tool in
     app.tools.meeting_notes_tool, so Nathan can file notes himself at the
     end of a live meeting.

Keeping the logic here (with no FastAPI, no Pydantic dependencies) means
both callers share the same code path: same template handling, same
fallback, same memory recording, same event log. No drift.
"""

import logging
from typing import Any

import httpx

from app.microsoft365 import (
    MicrosoftGraphClient,
    build_meeting_notes_docx,
    build_meeting_notes_markdown,
    build_meeting_notes_template_placeholders,
    render_meeting_notes_template_docx,
    sanitize_file_stem,
)
from app.project_memory import (
    get_project_context as memory_get_project_context,
    list_clients,
    record_agent_event,
    record_generated_output,
)

logger = logging.getLogger("parlayvu.services.meeting_notes")


def _client_display_name(
    *,
    client_name: str | None,
    client_id: str | None,
) -> str | None:
    """Display name used in DOCX placeholders. Prefer explicit name, fall back to id."""
    if client_name and client_name.strip():
        return client_name.strip()
    return client_id


def _client_full_name(
    *,
    client_id: str | None,
    project_id: str | None,
    fallback: str | None = None,
) -> str | None:
    """
    Resolve the client's full display name by checking project memory and
    the clients table. Used in DOCX placeholders. Quiet on failure - we
    fall back to whatever was passed in rather than blowing up the save.
    """
    if project_id:
        try:
            project_context = memory_get_project_context(project_id)
        except Exception as exc:
            logger.warning("Project context lookup skipped for client full name: %s", exc)
        else:
            client = (project_context or {}).get("client") or {}
            if client.get("name"):
                return client["name"]

    if client_id:
        try:
            for client in list_clients():
                if client.get("id") == client_id and client.get("name"):
                    return client["name"]
        except Exception as exc:
            logger.warning("Client lookup skipped for client full name: %s", exc)
        return fallback or client_id

    return fallback


def _template_fallback_reason(exc: Exception) -> str:
    """Human-readable reason for falling back to the generated DOCX."""
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 404:
            return "Template file was not found at the configured SharePoint path"
        return f"SharePoint template download failed with HTTP {status_code}"
    return str(exc)


async def publish_meeting_notes_to_teams(
    *,
    title: str,
    summary: str,
    client_id: str,
    project_id: str | None = None,
    project_name: str | None = None,
    client_name: str | None = None,
    source_conversation_id: str | None = None,
    team_id: str | None = None,
    channel_id: str | None = None,
    folder_path: str | None = None,
    channel: str = "api",
    agent_name: str = "nathan",
) -> dict[str, Any]:
    """
    Publish a meeting summary to a Teams channel folder as markdown + DOCX.

    Args:
        title: Meeting title (used as filename stem and DOCX heading).
        summary: The meeting summary text (rendered into both artifacts).
        client_id: ParlayVU client id (e.g. "ramair").
        project_id: Optional project id within the client.
        project_name: Optional display name for the project.
        client_name: Optional explicit display name for the client.
        source_conversation_id: Optional id of the originating conversation
            (Teams thread, Tavus session, etc.). Stored in audit metadata.
        team_id: Optional Teams group id. Falls back to M365_FILES_TEAM_ID.
        channel_id: Optional Teams channel id. Falls back to M365_FILES_CHANNEL_ID.
        folder_path: Optional folder path within the channel. Falls back to
            the configured default Meeting Notes folder.
        channel: Originating channel for the audit event ("api", "tavus_meeting",
            "teams", etc.). Pure metadata.
        agent_name: Which agent is recorded as the publisher. Defaults to nathan.

    Returns:
        {
            "status": "published",
            "files": {"markdown": {...}, "docx": {...}},
            "docx_template": {"status": "template"|"fallback", ...},
            "memory_output_id": str | None,
            "event_id": str | None,
        }

    Raises:
        ValueError if title or summary is empty (after stripping).
        Any exception from MicrosoftGraphClient (network, auth, etc.) is
        propagated - callers decide how to surface it.
    """
    title = title.strip()
    summary = summary.strip()
    if not title:
        raise ValueError("Meeting note title is required")
    if not summary:
        raise ValueError("Meeting note summary is required")

    markdown = build_meeting_notes_markdown(
        title=title,
        summary=summary,
        client_id=client_id,
        project_id=project_id,
    )
    stem = sanitize_file_stem(title)
    graph_client = MicrosoftGraphClient()
    template_path = graph_client.settings.files_meeting_notes_template_path
    expected_template_location = f"Teams channel Files root/{template_path.strip('/')}"

    # Try the templated DOCX first, fall back to the generated DOCX if the
    # template can't be downloaded or rendered. Either way we end up with
    # bytes we can upload.
    docx_template_info: dict[str, Any] = {
        "status": "template",
        "path": template_path,
        "expected_location": expected_template_location,
        "fallback_reason": None,
    }
    try:
        template_docx = await graph_client.download_teams_channel_file(
            file_path=template_path,
            team_id=team_id,
            channel_id=channel_id,
        )
        display = _client_display_name(client_name=client_name, client_id=client_id)
        docx = render_meeting_notes_template_docx(
            template_docx,
            build_meeting_notes_template_placeholders(
                title=title,
                summary=summary,
                client_id=client_id,
                client_name=display,
                client_full_name=_client_full_name(
                    client_id=client_id,
                    project_id=project_id,
                    fallback=display,
                ),
                project_id=project_id,
            ),
        )
    except Exception as exc:
        fallback_reason = _template_fallback_reason(exc)
        logger.warning(
            "Using generated meeting notes DOCX fallback; template_path=%s expected_location=%s reason=%s",
            template_path,
            expected_template_location,
            fallback_reason,
        )
        docx = build_meeting_notes_docx(
            title=title,
            summary=summary,
            client_id=client_id,
            project_id=project_id,
        )
        docx_template_info = {
            "status": "fallback",
            "path": template_path,
            "expected_location": expected_template_location,
            "fallback_reason": fallback_reason,
        }

    markdown_file = await graph_client.upload_teams_channel_file(
        filename=f"{stem}.md",
        content=markdown.encode("utf-8"),
        content_type="text/markdown; charset=utf-8",
        team_id=team_id,
        channel_id=channel_id,
        folder_path=folder_path,
    )
    docx_file = await graph_client.upload_teams_channel_file(
        filename=f"{stem}.docx",
        content=docx,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        team_id=team_id,
        channel_id=channel_id,
        folder_path=folder_path,
    )

    files = {"markdown": markdown_file, "docx": docx_file}
    memory_output_id = record_generated_output(
        client_id=client_id or "ramair",
        project_id=project_id,
        project_name=project_name,
        agent_name=agent_name,
        output_type="teams_files_meeting_notes",
        title=title,
        content=markdown,
        uri=docx_file.get("webUrl") or markdown_file.get("webUrl"),
        status="published",
        metadata={
            "files": files,
            "source_of_truth": "ParlayVU project memory",
            "source_conversation_id": source_conversation_id,
            "team_id": team_id,
            "channel_id": channel_id,
            "folder_path": folder_path,
            "docx_template": docx_template_info,
        },
    )
    event_id = record_agent_event(
        client_id=client_id,
        project_id=project_id,
        project_name=project_name,
        agent_name=agent_name,
        event_type="teams_files_meeting_notes_published",
        channel=channel,
        summary=f"Published Teams Files meeting notes: {title}",
        payload={
            "files": files,
            "memory_output_id": memory_output_id,
            "source_conversation_id": source_conversation_id,
            "team_id": team_id,
            "channel_id": channel_id,
            "folder_path": folder_path,
            "docx_template": docx_template_info,
        },
    )
    return {
        "status": "published",
        "files": files,
        "docx_template": docx_template_info,
        "memory_output_id": memory_output_id,
        "event_id": event_id,
    }
