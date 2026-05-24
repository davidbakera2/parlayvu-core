# app/tools/meeting_notes_tool.py
"""
Nathan's save_meeting_notes tool for Tavus live conversations.

This is Nathan's ONE write tool. When a meeting is wrapping up and a
participant says something like "send the notes" or "save what we
discussed," Nathan drafts a 2-4 paragraph summary, confirms it verbally,
then calls this tool. The summary lands in the client's Teams channel
as both a markdown file and a Word document.

The actual upload work lives in app.services.meeting_notes_service so
this tool and the HTTP endpoint POST /m365/files/meeting-notes share
the exact same code path. No drift.
"""

import logging
from typing import Any

from app.services.meeting_notes_service import publish_meeting_notes_to_teams

logger = logging.getLogger("parlayvu.tools.meeting_notes")


async def save_meeting_notes(
    title: str,
    summary: str,
    client_id: str,
) -> dict[str, Any]:
    """
    File a meeting summary to the client's Teams channel.

    Returns a Nathan-friendly dict that Claude can use to confirm the
    save to the participants. On failure we return a structured error
    instead of raising - Claude needs to be able to say "I couldn't
    save those, let me have someone follow up" without the whole turn
    blowing up.

    Args:
        title: Short meeting title used as the filename stem.
        summary: 2-4 paragraph summary written by Nathan.
        client_id: e.g. "ramair". Must match a client directory or DB row.

    Returns:
        On success:
            {
                "status": "saved",
                "title": str,
                "client_id": str,
                "markdown_url": str | None,
                "docx_url": str | None,
                "memory_output_id": str | None,
                "message": "Meeting notes filed in the {client_id} Teams channel.",
            }
        On failure:
            {
                "status": "failed",
                "error": str,
                "message": "Could not file the meeting notes...",
            }
    """
    try:
        result = await publish_meeting_notes_to_teams(
            title=title,
            summary=summary,
            client_id=client_id,
            channel="tavus_meeting",
            agent_name="nathan",
        )
    except ValueError as exc:
        # Title or summary was empty
        logger.warning("save_meeting_notes refused: %s", exc)
        return {
            "status": "failed",
            "error": str(exc),
            "message": f"I can't save those notes - {exc}. Want me to try again with a different title or summary?",
        }
    except Exception as exc:
        # Graph upload failed, template errored, DB blew up, etc.
        logger.exception("save_meeting_notes upload failed")
        return {
            "status": "failed",
            "error": str(exc),
            "message": (
                "I drafted the notes but couldn't file them to the Teams channel "
                "just now. I'll have someone on the team follow up after the call."
            ),
        }

    files = result.get("files") or {}
    markdown_file = files.get("markdown") or {}
    docx_file = files.get("docx") or {}

    return {
        "status": "saved",
        "title": title,
        "client_id": client_id,
        "markdown_url": markdown_file.get("webUrl"),
        "docx_url": docx_file.get("webUrl"),
        "memory_output_id": result.get("memory_output_id"),
        "message": (
            f"Meeting notes filed in the {client_id} Teams channel "
            f"(both markdown and a Word doc). The team will see them shortly."
        ),
    }
