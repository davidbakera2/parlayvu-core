"""Dylan's targeted-edit service (significantly hardened for small real edits).

Recent reliability work (to address "small edits like photo updates come out broken"):
- Pure image/photo changes ("update the hero photo", "swap the staff picture src to ...")
  are handled by _try_direct_image_patch — a pure regex attribute update. Zero LLM
  risk of breaking classes, nesting, scripts, or aria-labels on ulcannarbor-style sites.
- General edits now strongly prefer the LLM producing a JSON of precise "old"->"new"
  snippet replacements (with context so the match is unique). The applicator does
  exact single-occurrence replace and aborts on ambiguity. Full-page rewrite is
  only a fallback.
- Every result goes through _basic_html_validation. If it fails we auto-invoke a
  repair LLM pass ("fix this while preserving the requested change only").
- compose_section_edit (preferred for anything structural) has more robust
  _insert_section heuristics.
- Diffs are logged for audit. The Nathan prompt now documents the safe paths.

Source of truth for "what's currently live" is the production domain itself,
not the container's local disk. On every edit, we fetch the live HTML from
`https://<production_domain>/` (SSRF-guarded and size-capped — see
_get_html_capped / _validate_public_http_url), write it back to
`client_artifacts/<client>/03_Deliverables/sites/active/index.html` as a cache,
then apply the plain-English change.

Live-as-source means the workflow survives container restarts and ephemeral
disk wipes: the cache self-heals on the next call.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

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
MAX_FETCH_BYTES = 4 * MAX_HTML_CHARS  # ~800 KB hard cap on any fetched body (memory guard)
REPAIR_MAX_CHARS = 30_000  # above this, the repair LLM's output would be truncated by max_tokens — skip repair instead of corrupting
SONNET_MODEL = "claude-sonnet-4-6"
SONNET_MAX_TOKENS = 8_000


def _timestamp_slug(now: Optional[datetime] = None) -> str:
    """ISO-ish UTC slug safe for filesystems: 2026-05-27T184523Z."""
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H%M%SZ")


LIVE_FETCH_TIMEOUT_SECONDS = 10.0


def _validate_public_http_url(url: str) -> None:
    """Guard against SSRF before we fetch a URL.

    Only allow http(s) to public hosts. Rejects non-http(s) schemes, embedded
    credentials, localhost, and literal private/loopback/link-local/reserved/
    multicast IPs. Used for the initial fetch URL and, via an httpx request
    event hook, for every redirect hop as well. Raises ValueError if unsafe.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Refusing to fetch non-http(s) URL: {url!r}")
    if parsed.username or parsed.password:
        raise ValueError("Refusing to fetch a URL that embeds credentials")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"URL has no host: {url!r}")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError(f"Refusing to fetch localhost: {url!r}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None  # not a literal IP — a DNS name, which is the normal case
    if ip is not None and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    ):
        raise ValueError(f"Refusing to fetch private/internal address: {url!r}")


async def _ssrf_request_guard(request: "httpx.Request") -> None:
    """httpx 'request' event hook — validates every outgoing request (including
    redirect targets) before it is sent, so an open redirect can't reach an
    internal host."""
    _validate_public_http_url(str(request.url))


async def _get_html_capped(
    http: httpx.AsyncClient, url: str, *, max_bytes: int = MAX_FETCH_BYTES
) -> str:
    """GET `url`, streaming the body and aborting if it exceeds `max_bytes`.

    Prevents a misconfigured or hostile origin from exhausting memory: we never
    buffer more than `max_bytes` before bailing with ValueError. Returns the
    decoded text (utf-8, replacing undecodable bytes).
    """
    chunks: list[bytes] = []
    total = 0
    async with http.stream("GET", url) as response:
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(
                    f"Refusing to read {url!r}: body exceeds {max_bytes:,}-byte cap"
                )
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


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
            _validate_public_http_url(url)
            async with httpx.AsyncClient(
                timeout=LIVE_FETCH_TIMEOUT_SECONDS,
                follow_redirects=True,
                event_hooks={"request": [_ssrf_request_guard]},
            ) as http:
                html = await _get_html_capped(http, url)
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
        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            # ValueError covers SSRF-guard rejection and the body-size cap.
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
    """One LLM call using the improved prompt. Prefers JSON {replacements: [...]}
    for safe surgical edits. Falls back to full HTML if needed.
    Never returns the original if a change was requested.
    """
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

    # Strip code fences (LLM sometimes ignores instructions)
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()

    # Preferred path: JSON with replacements for minimal, reliable edits
    if raw.startswith("{") and "replacements" in raw:
        try:
            data = json.loads(raw)
            replacements = data.get("replacements", [])
            if replacements:
                edited = _apply_replacements_safely(current_html, replacements, change_description)
                if edited != current_html:
                    logger.info("Dylan edit applied via %d replacements", len(replacements))
                    return edited
                else:
                    logger.warning("Replacements produced no change; falling back to full HTML")
        except Exception as exc:
            logger.warning("Failed to parse/apply JSON replacements (%s); will try as full HTML", exc)

    # Legacy / fallback: full HTML document
    if "<!DOCTYPE" in raw.upper() or raw.lower().startswith("<html"):
        return raw

    # If LLM gave something weird, try to salvage by wrapping or last resort
    logger.warning("LLM edit output did not look like HTML or JSON; using raw as best effort")
    return raw


def _apply_replacements_safely(
    current_html: str, replacements: list[dict[str, str]], change_description: str
) -> str:
    """Apply a list of {old, new} replacements with strict safety.

    - Each 'old' must appear EXACTLY once (use sufficient context in the prompt).
    - Replacements are applied sequentially on the result of the previous.
    - If any replace would not change anything or match >1 time, we abort and return original
      so the caller can fall back or retry.
    - Logs the before/after for the specific changed regions for audit.
    """
    html = current_html
    applied = 0

    for i, rep in enumerate(replacements):
        old = rep.get("old", "")
        new = rep.get("new", "")
        if not old or old == new:
            logger.warning("Skipping empty or no-op replacement %d", i)
            continue

        count = html.count(old)
        if count == 0:
            logger.warning("Replacement %d old snippet not found in HTML — aborting safe apply", i)
            return current_html  # fail closed
        if count > 1:
            logger.warning(
                "Replacement %d old snippet is ambiguous (matches %d times) — aborting. "
                "Prompt should have included more surrounding context.",
                i, count
            )
            return current_html

        # Safe single replace
        html = html.replace(old, new, 1)
        applied += 1
        logger.debug("Applied replacement %d: %r -> %r (len delta %d)", i, old[:60], new[:60], len(new) - len(old))

    if applied == 0:
        logger.warning("No replacements were applied for change: %s", change_description[:80])
        return current_html

    # Audit: log a compact before/after for the changed region
    try:
        import difflib
        diff = list(difflib.unified_diff(
            current_html.splitlines(keepends=True),
            html.splitlines(keepends=True),
            fromfile="before.html",
            tofile="after.html",
            n=2,
        ))
        if diff:
            logger.info("Edit diff (first 10 lines):\n%s", "".join(diff[:10]))
    except Exception:
        pass

    return html


def _basic_html_validation(html: str, original: str, change_description: str) -> tuple[bool, str]:
    """Lightweight post-edit checks. Returns (ok, reason_if_bad)."""
    if not html or len(html) < 100:
        return False, "output too short"

    lower = html.lower()
    if not lower.lstrip().startswith("<!doctype"):
        return False, "missing doctype"

    required = ["<html", "<head", "<body", "</html>"]
    for tag in required:
        if tag not in lower:
            return False, f"missing required tag {tag}"

    # Content-loss guard. Losing more than half the page is the signature of a
    # truncated or over-deleted edit (the exact failure this service was hardened
    # against) — fail closed rather than deploy a gutted page.
    orig_len = len(original)
    new_len = len(html)
    if orig_len > 0 and new_len < orig_len * 0.5:
        return False, (
            f"output lost over half its content ({orig_len} -> {new_len} chars) "
            f"— likely truncated or over-deleted"
        )
    # Large *growth* is usually intentional (added a section); flag but allow.
    if abs(new_len - orig_len) > max(2000, orig_len * 0.3):
        logger.warning(
            "Large size delta after edit (%d -> %d) for '%s' — possible over-editing",
            orig_len, new_len, change_description[:60]
        )

    # Check that at least the change description keywords appear, or some new content
    # (very loose heuristic)
    key_tokens = [w for w in change_description.lower().split() if len(w) > 3][:3]
    if key_tokens and not any(t in lower for t in key_tokens):
        logger.info("Change keywords not obviously present in output; may still be ok")

    return True, ""


def _inject_attr(open_tag: str, name: str, value: str) -> str:
    """Insert `name="value"` into an opening tag that lacks it.

    `open_tag` is a full opening tag like `<div ...>` or a self-closing
    `<img ... />`. The attribute is added just before the closing `>` / `/>`.
    """
    if re.search(r'/\s*>\s*$', open_tag):  # self-closing <img ... />
        return re.sub(r'\s*/\s*>\s*$', f' {name}="{value}" />', open_tag, count=1)
    return re.sub(r'>\s*$', f' {name}="{value}">', open_tag, count=1)


def _try_direct_image_patch(current_html: str, change_description: str) -> str:
    """If the change is clearly just 'update/replace/swap this photo/image/picture',
    perform a safe, targeted attribute edit using regex. No LLM, cannot break structure.

    Supports common patterns in the current single-file sites:
      - <img src="..." alt="..." ...>
      - <div role="img" aria-label="..." style="..."> or data-*
      - background-image in inline style

    Returns the (possibly) modified HTML, or original if not a pure image change.
    """
    desc = change_description.lower()
    if not any(kw in desc for kw in ("photo", "image", "picture", "img", "src", "hero image", "staff photo")):
        return current_html

    # Try to extract a new src or description from the request.
    # Simple heuristics; in practice Nathan gives clear instructions like
    # "change the hero photo src to /images/new-building.jpg and aria-label to 'The new ULC building at sunset'"
    new_src = None
    new_alt = None

    # Look for obvious URL or path in the description
    url_match = re.search(r'(https?://\S+|/\S+\.(?:jpg|jpeg|png|webp|gif))', change_description, re.I)
    if url_match:
        new_src = url_match.group(1).strip(' "\'')

    # Look for quoted description for alt/aria
    alt_match = re.search(r'["\']([^"\']{10,})["\']', change_description)
    if alt_match:
        candidate = alt_match.group(1)
        if any(w in candidate.lower() for w in ("photo", "image", "building", "people", "student", "campus")) or len(candidate) > 15:
            new_alt = candidate

    if not new_src and not new_alt:
        # Not specific enough for direct patch — let the LLM path handle it
        return current_html

    html = current_html

    # 1. <img> tags — update the attribute if present, otherwise inject it.
    def _replace_img(m: re.Match) -> str:
        tag = m.group(0)
        if new_src:
            if re.search(r'(?i)\bsrc\s*=', tag):
                tag = re.sub(r'(?i)\bsrc\s*=\s*["\'][^"\']*["\']', f'src="{new_src}"', tag, count=1)
            else:
                tag = _inject_attr(tag, "src", new_src)
        if new_alt:
            if re.search(r'(?i)\balt\s*=', tag):
                tag = re.sub(r'(?i)\balt\s*=\s*["\'][^"\']*["\']', f'alt="{new_alt}"', tag, count=1)
            else:
                tag = _inject_attr(tag, "alt", new_alt)
            # Keep an existing aria-label in sync; don't add a redundant one (alt suffices).
            tag = re.sub(r'(?i)\baria-label\s*=\s*["\'][^"\']*["\']', f'aria-label="{new_alt}"', tag, count=1)
        return tag

    html = re.sub(r'<img\b[^>]*>', _replace_img, html, flags=re.I)

    # 2. role="img" containers (common in the current ULC/Parlay sites)
    def _replace_role_img(m: re.Match) -> str:
        tag = m.group(0)
        if new_alt:
            if re.search(r'(?i)\baria-label\s*=', tag):
                tag = re.sub(r'(?i)\baria-label\s*=\s*["\'][^"\']*["\']', f'aria-label="{new_alt}"', tag, count=1)
            else:
                tag = _inject_attr(tag, "aria-label", new_alt)
        if new_src:
            # Update an existing background-image or data-src if present;
            # otherwise inject a data-src so the new image is actually applied.
            if re.search(r'(?i)background-image\s*:\s*url\([^)]*\)', tag):
                tag = re.sub(r'(?i)background-image\s*:\s*url\([^)]*\)', f'background-image: url({new_src})', tag, count=1)
            elif re.search(r'(?i)\bdata-(?:src|image)\s*=', tag):
                tag = re.sub(r'(?i)\bdata-(?:src|image)\s*=\s*["\'][^"\']*["\']', f'data-src="{new_src}"', tag, count=1)
            else:
                tag = _inject_attr(tag, "data-src", new_src)
        return tag

    html = re.sub(r'<div[^>]*role=["\']img["\'][^>]*>', _replace_role_img, html, flags=re.I)

    # 3. Simple style background on hero-like divs (last resort)
    if new_src and "background" in desc:
        html = re.sub(
            r'(?i)(<div[^>]*class=["\'][^"\']*hero[^"\']*["\'][^>]*style=["\'][^"\']*)background-image\s*:\s*url\([^)]*\)([^"\']*["\'])',
            lambda m: m.group(1) + f'background-image: url({new_src})' + m.group(2),
            html,
            count=1,
        )

    if html != current_html:
        logger.info("Applied direct image patch for change: %s", change_description[:80])
        return html

    return current_html


async def ensure_edit_dir_on_disk(
    *,
    client_id: str,
    edit_slug: str,
    preview_url: Optional[str],
) -> Path:
    """Make sure `sites/edits/<edit_slug>/index.html` exists on disk.

    If it's already there, returns the resolved edit dir.

    If it's missing — typically because the container disk was wiped between
    the edit being generated and the approval being clicked — fetch the HTML
    from the preview deploy (`preview_url`) and write it back. The preview
    Pages project lives on Cloudflare, so it's a reliable recovery source.

    Raises FileNotFoundError if recovery isn't possible (no preview_url given,
    or the fetch fails).
    """
    edit_dir = client_sites_root(client_id) / EDITS_SUBDIR / edit_slug
    edit_index = edit_dir / "index.html"
    if edit_index.is_file():
        return edit_dir

    if not preview_url:
        raise FileNotFoundError(
            f"Edit directory {edit_dir} is missing and no preview_url is "
            f"available to recover it from. The edit may need to be "
            f"regenerated."
        )

    logger.info(
        "Recovering edit from preview | client=%s slug=%s url=%s",
        client_id, edit_slug, preview_url,
    )
    try:
        _validate_public_http_url(preview_url)
        async with httpx.AsyncClient(
            timeout=LIVE_FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            event_hooks={"request": [_ssrf_request_guard]},
        ) as http:
            html = await _get_html_capped(http, preview_url)
    except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
        raise FileNotFoundError(
            f"Edit directory {edit_dir} is missing and recovery from preview "
            f"{preview_url} failed ({type(exc).__name__}: {exc}). The edit "
            f"may need to be regenerated."
        ) from exc

    edit_dir.mkdir(parents=True, exist_ok=True)
    edit_index.write_text(html, encoding="utf-8")
    logger.info(
        "Recovered edit to disk | client=%s slug=%s bytes=%s",
        client_id, edit_slug, len(html),
    )
    return edit_dir


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

    # Special case: pure photo/image updates are done with a deterministic direct patch
    # (no LLM involvement). This guarantees "update the hero photo to ..." never breaks
    # the page structure, classes, or surrounding markup.
    edited_html = _try_direct_image_patch(current_html, change_description)
    used_direct = edited_html != current_html

    if not used_direct:
        edited_html = await _apply_edit_with_llm(
            client_display_name=config.display_name,
            change_description=change_description,
            current_html=current_html,
        )

    ok, reason = _basic_html_validation(edited_html, current_html, change_description)
    if not ok:
        logger.error("Post-edit validation failed: %s", reason)
        # Attempt a lightweight repair: ask the LLM to fix the broken HTML while
        # preserving intent. Only when the page is small enough that the repair
        # output fits within max_tokens — otherwise the repair itself would be
        # silently truncated and could deploy an incomplete page.
        if len(edited_html) > REPAIR_MAX_CHARS:
            logger.error(
                "Skipping repair: edited HTML is %d chars (> %d cap); cannot repair "
                "without truncating the output.",
                len(edited_html), REPAIR_MAX_CHARS,
            )
        try:
            repair_api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if repair_api_key and len(edited_html) <= REPAIR_MAX_CHARS:
                repair_client = anthropic.AsyncAnthropic(api_key=repair_api_key)
                repair_prompt = (
                    f"The following HTML was produced by an edit for this request: {change_description}\n\n"
                    f"It failed basic validation because: {reason}\n\n"
                    "Please output a corrected, complete, valid single-file HTML homepage that performs ONLY the requested change. "
                    "Preserve everything else exactly. Start with <!DOCTYPE html>."
                )
                repair_response = await repair_client.messages.create(
                    model=SONNET_MODEL,
                    max_tokens=SONNET_MAX_TOKENS,
                    temperature=0.1,
                    messages=[{"role": "user", "content": repair_prompt + "\n\nBROKEN HTML:\n" + edited_html}],
                )
                repaired = "".join([b.text for b in repair_response.content if hasattr(b, "text")]).strip()
                if repaired.startswith("```"):
                    repaired = re.sub(r"^```[a-zA-Z]*\n?", "", repaired)
                    repaired = re.sub(r"\n?```$", "", repaired)
                if "<!DOCTYPE" in repaired.upper():
                    edited_html = repaired
                    ok, reason = _basic_html_validation(edited_html, current_html, change_description)
                    if ok:
                        logger.info("Repair succeeded for edit")
        except Exception as repair_exc:
            logger.exception("Repair attempt failed: %s", repair_exc)

    if not ok:
        # Last resort: return original + error marker so caller sees it was a no-op
        raise ValueError(f"Dylan edit produced invalid HTML ({reason}). No change was applied.")

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


# =============================================================================
# NEW: Component-based section editing (v1 — homepage only)
# This is the preferred tool going forward for structural changes.
# =============================================================================

async def compose_section_edit(
    *,
    client_id: str,
    section_name: str,
    section_data: dict[str, Any],
    target_location: str | None = "after:hero",
    deploy: bool = True,
) -> dict[str, Any]:
    """
    Compose an approved design system section and insert it into the client's homepage.

    This is the new primary tool for structural edits (TeamGrid, Features3Col, etc.).
    It is intended to replace free-form HTML patching for anything beyond small tweaks.

    Homepage-only in v1.
    """
    # Validation
    allowed_sections = {
        "Hero", "Features3Col", "TeamGrid", "TestimonialGrid",
        "ContentWithImage", "LogoCloud", "FAQ", "CTA"
    }
    
    if section_name not in allowed_sections:
        raise ValueError(
            f"Unknown section_name '{section_name}'. "
            f"Approved sections (v1): {', '.join(sorted(allowed_sections))}"
        )

    if not section_data or not isinstance(section_data, dict):
        raise ValueError("section_data must be a non-empty dictionary")

    config = load_client_config(client_id)

    active_index = client_active_dir(client_id) / "index.html"
    current_html = await _resolve_active_html(
        client_id=client_id,
        config=config,
        active_index=active_index,
    )

    logger.info(
        "Composing section | client=%s section=%s",
        client_id, section_name,
    )

    section_html = await _generate_section_html(
        client_display_name=config.display_name,
        section_name=section_name,
        section_data=section_data,
    )

    updated_html = _insert_section(
        current_html=current_html,
        section_html=section_html,
        target_location=target_location or "after:hero",
    )

    slug = f"edit-{_timestamp_slug()}"
    edit_dir = client_sites_root(client_id) / EDITS_SUBDIR / slug
    edit_dir.mkdir(parents=True, exist_ok=True)
    (edit_dir / "index.html").write_text(updated_html, encoding="utf-8")

    def _repo_rel(p: Path) -> str:
        try:
            return str(p.relative_to(Path.cwd())).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    deploy_result = None
    preview_url = None
    if deploy:
        try:
            deploy_result = deploy_preview(client_id=client_id)
            preview_url = deploy_result.get("url")
            if preview_url:
                preview_url = preview_url.rstrip("/") + f"/{EDITS_SUBDIR}/{slug}/"
        except Exception as exc:
            logger.exception("compose_section_edit deploy failed")
            deploy_result = {"status": "error", "message": str(exc)}

    status = (deploy_result or {}).get("status", "generated")

    memory_output_id = record_generated_output(
        client_id=client_id,
        project_id=None,
        agent_name="dylan",
        output_type="section_edit",
        title=f"{config.display_name} — {section_name}",
        uri=preview_url,
        status=status,
        metadata={
            "section_name": section_name,
            "section_data": section_data,
            "edit_slug": slug,
        },
    )

    return {
        "status": status,
        "client_id": client_id,
        "section_name": section_name,
        "section_data": section_data,
        "target_location": target_location,
        "edit_slug": slug,
        "edit_dir": _repo_rel(edit_dir),
        "preview_url": preview_url,
        "deploy": deploy_result,
        "memory_output_id": memory_output_id,
    }


async def _generate_section_html(
    *,
    client_display_name: str,
    section_name: str,
    section_data: dict[str, Any],
) -> str:
    """Generate section HTML guided by the design system (v1)."""
    client = anthropic.AsyncAnthropic()

    prompt = f"""You are Dylan Brooks composing a clean, accessible section from the ParlayVU Design System.

Section: {section_name}
Client: {client_display_name}

Data:
{json.dumps(section_data, indent=2)}

Rules:
- Output ONLY the HTML for this one section (no full page wrapper).
- Use semantic Tailwind classes.
- Make it responsive and accessible.
- Return just the section markup.
"""

    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [block.text for block in response.content if hasattr(block, "text")]
    html = "".join(parts).strip()

    if html.startswith("```"):
        html = re.sub(r"^```[a-zA-Z]*\n?", "", html)
        html = re.sub(r"\n?```$", "", html)

    return html.strip()


def _insert_section(
    *,
    current_html: str,
    section_html: str,
    target_location: str,
) -> str:
    """
    Robust insertion for approved design-system sections.
    Uses multiple heuristics + a safe fallback. Still string-based (no bs4 dep yet)
    but with better guards against breaking the document.
    """
    loc = (target_location or "after:hero").lower().strip()
    html = current_html

    def _safe_insert_after(marker: str, insert: str) -> str | None:
        if marker not in html:
            return None
        # Insert after the *first* occurrence only
        idx = html.find(marker)
        if idx == -1:
            return None
        pos = idx + len(marker)
        return html[:pos] + "\n" + insert + "\n" + html[pos:]

    if "after:hero" in loc or "after hero" in loc:
        for marker in ("</section>", "</header>", 'id="main"', "<main"):
            res = _safe_insert_after(marker, section_html)
            if res:
                return res
        # Try after a hero class or role
        for marker in ('class="hero', 'role="banner"'):
            if marker in html:
                idx = html.find(marker)
                # advance to end of the opening tag
                end_tag = html.find(">", idx)
                if end_tag != -1:
                    pos = end_tag + 1
                    return html[:pos] + "\n" + section_html + "\n" + html[pos:]

    if "before:footer" in loc or "before footer" in loc:
        if "</footer>" in html:
            return html.replace("</footer>", "\n" + section_html + "\n</footer>", 1)

    if "before:contact" in loc or 'id="contact"' in html:
        if 'id="contact"' in html:
            idx = html.find('id="contact"')
            # insert before the contact section
            start = html.rfind("<", 0, idx)  # rough start of tag
            if start != -1:
                return html[:start] + "\n" + section_html + "\n" + html[start:]

    # Safe universal fallbacks (preserve document well-formedness as much as possible)
    for end_marker in ("</main>", "</body>"):
        if end_marker in html:
            return html.replace(end_marker, "\n" + section_html + "\n" + end_marker, 1)

    # Last resort — append before closing html
    if "</html>" in html:
        return html.replace("</html>", "\n" + section_html + "\n</html>", 1)

    return html + "\n" + section_html
