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
    *,
    project: str | None = None,
    meeting_date_time: str | None = None,
    attendees: list[str] | None = None,
    decisions: list[str] | None = None,
    action_items: list[dict[str, str]] | None = None,
    questions: list[str] | None = None,
    next_steps: list[str] | None = None,
    source_material: list[str] | None = None,
) -> dict[str, Any]:
    """
    File a structured meeting record to the client's Teams channel.

    Returns a Nathan-friendly dict Claude can read to confirm the save
    to participants. On failure we return a structured error instead of
    raising - Claude needs to be able to say "I couldn't save those"
    gracefully without the turn blowing up.

    All structured fields are optional. When provided, the template
    renderer populates the matching section (bulleted list, or the
    action items table) of the meeting notes DOCX. Anything Nathan
    leaves out is simply absent from the rendered document.

    Args:
        title: Short meeting title used as the filename stem.
        summary: 2-4 paragraph plain-prose summary of the discussion.
        client_id: e.g. "ramair". Must match a client directory or DB row.
        project: Project display name (e.g. "RamAir Straight From The Hart").
        meeting_date_time: Free-form date/time string. Defaults to the
            current UTC time if omitted.
        attendees: People who participated in the meeting.
        decisions: Key decisions made or announced during the call.
        action_items: List of {owner, action, due_date} dicts.
        questions: Open questions or concerns raised during the meeting.
        next_steps: Agreed next steps to move the project forward.
        source_material: References to key docs, sites, reports cited.

    Returns:
        On success: {"status": "saved", "title", "client_id",
                     "markdown_url", "docx_url", "memory_output_id",
                     "message"}
        On failure: {"status": "failed", "error", "message"}
    """
    try:
        result = await publish_meeting_notes_to_teams(
            title=title,
            summary=summary,
            client_id=client_id,
            project_name=project,
            meeting_date_time=meeting_date_time,
            attendees=attendees,
            decisions=decisions,
            action_items=action_items,
            questions=questions,
            next_steps=next_steps,
            source_material=source_material,
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
