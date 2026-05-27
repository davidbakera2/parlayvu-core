"""Dylan's targeted-edit service.

Source of truth for "what's currently live" is the production domain itself,
not the container's local disk. On every edit, we fetch the live HTML from
`https://<production_domain>/`, write it back to
`client_artifacts/<client>/03_Deliverables/sites/active/index.html` as a cache,
then apply the plain-English change to that file via the LLM. The result lands
in `.../sites/edits/edit-<timestamp>/index.html` and gets deployed to the
client's preview Pages project for review. Promotion (replacing active/ and
pushing to prod) is handled by client_deploy.promote_to_production once the
edit is approved in Teams.

Live-as-source means the workflow survives container restarts, ephemeral disk
wipes, and the case where a different client's revision didn't promote
anything — onboarding is config-only: a client's `production_domain` in their
config.yaml is enough to make edits work. Falls back to the on-disk cache only
if the live fetch fails (offline, prod project not yet deployed, etc.) and the
cache exists.

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
import httpx

from app.agents.prompts import DYLAN_EDIT_PROMPT_TEMPLATE
from app.client_config import ClientConfig, ClientConfigError, load_client_config
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


LIVE_FETCH_TIMEOUT_SECONDS = 10.0


async def _resolve_active_html(
    *,
    client_id: str,
    config: ClientConfig,
    active_index: Path,
) -> str:
    """Get the current HTML for `client_id`'s homepage.

    Strategy:
      1. If config has a `production_domain`, fetch `https://<domain>/` via
         httpx. On success, write the body to active_index as a local cache
         and return it.
      2. If the fetch fails (network, 4xx, 5xx) or no domain is configured,
         fall back to reading active_index from disk.
      3. If neither path produces HTML, raise FileNotFoundError with a
         message that points to the underlying cause (no live site + no cache).

    Live-fetch is the source of truth because container disks are ephemeral —
    every revision roll wipes active/. The cache write makes the on-disk file
    self-healing for the next call.
    """
    domain = config.cloudflare_config.production_domain
    fetch_error: Optional[str] = None

    if domain:
        url = f"https://{domain}/"
        try:
            async with httpx.AsyncClient(
                timeout=LIVE_FETCH_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as http:
                response = await http.get(url)
                response.raise_for_status()
                html = response.text
            # Best-effort cache write — don't fail the edit if disk write fails.
            try:
                active_index.parent.mkdir(parents=True, exist_ok=True)
                active_index.write_text(html, encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "Live-fetch cache write skipped | client=%s path=%s err=%s",
                    client_id, active_index, exc,
                )
            logger.info(
                "Live-fetched active HTML | client=%s url=%s bytes=%s",
                client_id, url, len(html),
            )
            return html
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            fetch_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Live-fetch failed, will try disk cache | client=%s url=%s err=%s",
                client_id, url, fetch_error,
            )

    # Disk fallback (either no domain, or fetch failed).
    if active_index.is_file():
        logger.info(
            "Using cached active HTML | client=%s path=%s",
            client_id, active_index,
        )
        return active_index.read_text(encoding="utf-8")

    # Neither path produced HTML — fail with the most informative message we have.
    if domain and fetch_error:
        raise FileNotFoundError(
            f"No active site to edit for {client_id!r}. Live fetch of "
            f"https://{domain}/ failed ({fetch_error}) and the on-disk cache "
            f"at {active_index} doesn't exist either. Either the production "
            f"deploy hasn't happened yet (promote a variation first) or the "
            f"domain isn't reachable."
        )
    raise FileNotFoundError(
        f"No active site to edit for {client_id!r}. The client's config has "
        f"no production_domain set, and there's no on-disk cache at "
        f"{active_index}. Promote a homepage variation first so there's "
        f"a live source to edit from."
    )


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
    current_html = await _resolve_active_html(
        client_id=client_id,
        config=config,
        active_index=active_index,
    )
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
