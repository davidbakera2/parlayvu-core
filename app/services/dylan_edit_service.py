"""Dylan's targeted-edit service.

Reads the client's currently-active homepage from
`client_artifacts/<client>/03_Deliverables/sites/active/index.html`, applies a
plain-English change to that single file via the LLM, writes the result to
`.../sites/edits/edit-<timestamp>/index.html`, and deploys it to the client's
preview Pages project for review. Promotion (replacing active/ and pushing to
prod) is handled by app/services/client_deploy.promote_to_production once the
edit is approved in Teams.

This is the ongoing-edit workflow primitive — same spine as variations, just a
different Dylan action. Both feed into the same preview→approval→promote flow.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import anthropic

from app.agents.prompts import DYLAN_EDIT_PROMPT_TEMPLATE
from app.client_config import ClientConfigError, load_client_config
from app.project_memory import record_agent_event, record_generated_output
from app.services.client_deploy import (
    SITES_SUBPATH,
    client_active_dir,
    client_sites_root,
    deploy_preview,
)

logger = logging.getLogger("parlayvu.services.dylan_edit")

EDITS_SUBDIR = "edits"
MAX_HTML_CHARS = 200_000  # cap so we never blow the context window on a bizarre file
SONNET_MODEL = "claude-sonnet-4-6"
SONNET_MAX_TOKENS = 8_000


def _timestamp_slug(now: Optional[datetime] = None) -> str:
    """ISO-ish UTC slug safe for filesystems: 2026-05-27T184523Z."""
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H%M%SZ")


async def _apply_edit_with_llm(
    *,
    client_display_name: str,
    change_description: str,
    current_html: str,
) -> str:
    """One LLM call: take current HTML + change description, return edited HTML."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required for Dylan edit generation")
    client = anthropic.AsyncAnthropic(api_key=api_key)

    prompt = DYLAN_EDIT_PROMPT_TEMPLATE.format(
        client_display_name=client_display_name,
        change_description=change_description.strip(),
        current_html=current_html,
    )
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=SONNET_MAX_TOKENS,
        temperature=0.2,  # surgical edit — low temperature, predictability matters
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [block.text for block in response.content if hasattr(block, "text")]
    raw = "".join(parts).strip()
    # Sonnet occasionally wraps in code fences despite the instruction.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    return raw.strip()


async def edit_active_site(
    *,
    client_id: str,
    change_description: str,
    deploy: bool = True,
) -> dict[str, Any]:
    """Apply a targeted edit to the client's active homepage and stage a preview.

    Args:
        client_id: ParlayVU client id (must have an active config + an
            active/ folder — i.e. a variant has been promoted at least once).
        change_description: Plain-English description of the change to make.
        deploy: If True (default), pushes the edit preview to the client's
            preview Pages project so reviewers can see it before approving.

    Returns:
        {
          "status": "generated" | "deployed",
          "client_id": str,
          "change_description": str,
          "edit_slug": str,                 # "edit-2026-05-27T184523Z"
          "edit_dir": str,                  # repo-relative path to the edit dir
          "edit_html_path": str,            # repo-relative path to index.html
          "preview_url": str | None,        # the preview project URL (deploys all edits + variations)
          "deploy": {... raw deploy result ...} | None,
          "memory_output_id": str | None,
          "event_id": str | None,
        }

    Raises:
        ClientConfigError: if the client_id isn't onboarded.
        FileNotFoundError: if there's no active/index.html to edit.
    """
    config = load_client_config(client_id)

    if not change_description or not change_description.strip():
        raise ValueError("change_description is required")

    active_index = client_active_dir(client_id) / "index.html"
    if not active_index.is_file():
        raise FileNotFoundError(
            f"No active site to edit for {client_id!r}. Expected "
            f"{active_index}. Promote a homepage variation first so there's "
            f"a live source to edit from."
        )

    current_html = active_index.read_text(encoding="utf-8")
    if len(current_html) > MAX_HTML_CHARS:
        raise ValueError(
            f"Active HTML for {client_id} is {len(current_html):,} chars — "
            f"exceeds the {MAX_HTML_CHARS:,} cap. Likely not a single-file site; "
            f"this edit path only supports single-file homepages today."
        )

    logger.info(
        "Editing active site | client=%s change=%r",
        client_id, change_description[:80],
    )
    edited_html = await _apply_edit_with_llm(
        client_display_name=config.display_name,
        change_description=change_description,
        current_html=current_html,
    )

    # Write the edit to a timestamped folder under sites/edits/.
    slug = f"edit-{_timestamp_slug()}"
    edit_dir = client_sites_root(client_id) / EDITS_SUBDIR / slug
    edit_dir.mkdir(parents=True, exist_ok=True)
    edit_index = edit_dir / "index.html"
    edit_index.write_text(edited_html, encoding="utf-8")

    # Repo-relative paths for the result payload (forward slashes for cross-platform consistency).
    def _repo_rel(p: Path) -> str:
        try:
            return str(p.relative_to(Path.cwd())).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    edit_dir_rel = _repo_rel(edit_dir)
    edit_html_rel = _repo_rel(edit_index)

    # Optional deploy through the canonical spine so the preview project name
    # comes from config, not a hardcode.
    deploy_result: Optional[dict[str, Any]] = None
    preview_url: Optional[str] = None
    if deploy:
        try:
            # Deploy the whole sites/ tree so the existing variations index
            # still links work — the edit just appears as an additional folder
            # at /edits/<slug>/.
            deploy_result = deploy_preview(client_id=client_id)
            preview_url = deploy_result.get("url")
            if preview_url:
                # Surface the direct URL to this edit (not just the project root).
                preview_url = preview_url.rstrip("/") + f"/{EDITS_SUBDIR}/{slug}/"
        except Exception as exc:
            logger.exception("Dylan edit deploy step failed")
            deploy_result = {"status": "error", "message": str(exc)}

    status = (
        "deployed"
        if (deploy and deploy_result and deploy_result.get("status") in {"success", "deployed"})
        else "generated"
    )

    memory_output_id = record_generated_output(
        client_id=client_id,
        project_id=None,
        agent_name="dylan",
        output_type="homepage_edit",
        title=f"{config.display_name} — edit: {change_description[:80]}",
        content=None,
        uri=preview_url,
        status=status,
        metadata={
            "change_description": change_description,
            "edit_slug": slug,
            "edit_dir": edit_dir_rel,
            "edit_html_path": edit_html_rel,
            "preview_url": preview_url,
            "deploy": deploy_result,
        },
    )
    event_id = record_agent_event(
        agent_name="dylan",
        client_id=client_id,
        event_type="homepage_edit_generated",
        channel="api",
        summary=f"Generated edit for {config.display_name}: {change_description[:120]}",
        payload={
            "edit_slug": slug,
            "preview_url": preview_url,
            "memory_output_id": memory_output_id,
        },
    )

    return {
        "status": status,
        "client_id": client_id,
        "change_description": change_description,
        "edit_slug": slug,
        "edit_dir": edit_dir_rel,
        "edit_html_path": edit_html_rel,
        "preview_url": preview_url,
        "deploy": deploy_result,
        "memory_output_id": memory_output_id,
        "event_id": event_id,
    }
