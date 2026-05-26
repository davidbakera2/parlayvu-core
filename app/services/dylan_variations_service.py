"""Dylan's homepage-variation generation.

Reads a client's brief, design notes, and reference-sites index from their
client_artifacts folder, fetches the top reference URLs via Jina Reader,
then generates N visually-distinct single-file HTML+Tailwind homepage drafts
into client_artifacts/<client_id>/03_Deliverables/sites/variation-<i>/index.html.

Optionally deploys all variations under one Cloudflare Pages preview project
(<client_id>-previews.pages.dev) so the client can browse them via one link.

This is an HTTP-endpoint-driven orchestrator, NOT a Claude tool loop —
deterministic Python controls the file writes, audit, and deploy. The LLM is
called per-variation only to produce HTML.
"""
from __future__ import annotations

import asyncio
import html as html_module
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import anthropic

from app.agents.prompts import (
    DYLAN_VARIATION_PROMPT_TEMPLATE,
    DYLAN_VARIATION_THESES,
)
from app.client_config import ClientConfigError, load_client_config
from app.project_memory import record_agent_event, record_generated_output
from app.tools.web_tools import fetch_url

logger = logging.getLogger("parlayvu.services.dylan_variations")


CLIENT_ARTIFACTS_ROOT = Path("client_artifacts")
SITES_SUBPATH = Path("03_Deliverables") / "sites"
BRIEF_PATH = Path("00_Client_Brief") / "client-brief.md"
REFERENCES_PATH = Path("01_Source_Material") / "reference-sites.md"
DESIGN_NOTES_PATH = Path("01_Source_Material") / "design-notes.md"

MAX_FILE_CHARS = 6_000
MAX_FETCHED_REFERENCES = 5
MAX_VARIATIONS = 10
MIN_VARIATIONS = 1
SONNET_MODEL = "claude-sonnet-4-6"
SONNET_MAX_TOKENS = 8_000


# ─── safe writes ──────────────────────────────────────────────────────────────

def _write_site_file(client_id: str, relative_path: str, content: str) -> dict[str, Any]:
    """Write into client_artifacts/<client_id>/03_Deliverables/sites/, refusing
    anything that resolves outside that subtree.

    Returns {"path": "<repo-relative path>", "bytes": <int>}.
    """
    base = (CLIENT_ARTIFACTS_ROOT / client_id / SITES_SUBPATH).resolve()
    target = (base / relative_path).resolve()
    if target != base and not str(target).startswith(str(base) + os.sep):
        raise ValueError(
            f"Path escape attempt for client_id={client_id!r}: {relative_path!r}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    try:
        rel = target.relative_to(Path.cwd())
    except ValueError:
        rel = target
    return {"path": str(rel).replace("\\", "/"), "bytes": len(content.encode("utf-8"))}


# ─── reading client context ───────────────────────────────────────────────────

def _read_capped(path: Path) -> str:
    """Read a markdown file, cap at MAX_FILE_CHARS, return empty string if missing."""
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return ""
    if len(text) > MAX_FILE_CHARS:
        return text[:MAX_FILE_CHARS] + "\n\n[...truncated for prompt budget...]"
    return text


_URL_RE = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)


def _extract_reference_urls(references_md: str, limit: int = MAX_FETCHED_REFERENCES) -> list[str]:
    """Pull http/https URLs out of the reference-sites.md, preserving order and
    de-duplicating. Caps at `limit`."""
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_RE.findall(references_md):
        url = match.rstrip(".,);]")
        if url not in seen:
            seen.add(url)
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


async def _fetch_references(urls: list[str]) -> list[dict[str, Any]]:
    """Fetch reference URLs concurrently via Jina Reader. Failures are reported
    inline (each entry always has a `url`; on failure, `error` is set)."""
    if not urls:
        return []
    results = await asyncio.gather(*(fetch_url(u) for u in urls), return_exceptions=True)
    out: list[dict[str, Any]] = []
    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            out.append({"url": url, "error": str(result)})
        else:
            out.append(result)
    return out


def _format_fetched_references(fetched: list[dict[str, Any]]) -> str:
    """Render the fetched reference content as a single string block for the
    prompt. Each successful fetch becomes its own section with a header."""
    if not fetched:
        return "(no reference sites fetched)"
    sections: list[str] = []
    for entry in fetched:
        url = entry.get("url", "(unknown)")
        if "error" in entry:
            sections.append(f"### {url}\n[fetch failed: {entry['error']}]\n")
            continue
        content = entry.get("content", "").strip()
        if not content:
            sections.append(f"### {url}\n[no content returned]\n")
            continue
        sections.append(f"### {url}\n{content}\n")
    return "\n---\n".join(sections)


# ─── LLM call per variation ───────────────────────────────────────────────────

def _build_variation_prompt(
    *,
    client_display_name: str,
    variation_number: int,
    total: int,
    brief: str,
    references_index: str,
    fetched_references: str,
    design_notes: str,
) -> str:
    """Pick the right thesis for this variation index and assemble the prompt.

    For variation_number > len(THESES), cycle back through with a "+ unexpected
    twist" instruction so variations stay distinct when the caller asks for more
    than we have predefined theses for.
    """
    theses_count = len(DYLAN_VARIATION_THESES)
    thesis_idx = (variation_number - 1) % theses_count
    thesis = DYLAN_VARIATION_THESES[thesis_idx]
    cycle = (variation_number - 1) // theses_count
    twist_instruction = ""
    if cycle > 0:
        twist_instruction = (
            f"This is the {cycle + 1}{'nd' if cycle == 1 else 'rd' if cycle == 2 else 'th'} "
            f"variation built on this thesis — apply an unexpected twist (different layout "
            f"axis, contrarian content order, surprising hero treatment) so it doesn't look "
            f"like a re-skin of variation {thesis_idx + 1}.\n\n"
        )
    return DYLAN_VARIATION_PROMPT_TEMPLATE.format(
        variation_number=variation_number,
        total=total,
        thesis=thesis,
        twist_instruction=twist_instruction,
        client_display_name=client_display_name,
        brief=brief or "(no client brief on file)",
        references_index=references_index or "(no reference sites listed)",
        fetched_references=fetched_references,
        design_notes=design_notes or "(no design notes on file)",
    )


async def _generate_variation_html(
    *,
    client_display_name: str,
    variation_number: int,
    total: int,
    brief: str,
    references_index: str,
    fetched_references: str,
    design_notes: str,
    client: anthropic.AsyncAnthropic,
) -> str:
    """Call Sonnet 4.6 to produce the HTML for one variation. Returns the raw
    HTML string. Raises on API failure (caller decides how to surface)."""
    prompt = _build_variation_prompt(
        client_display_name=client_display_name,
        variation_number=variation_number,
        total=total,
        brief=brief,
        references_index=references_index,
        fetched_references=fetched_references,
        design_notes=design_notes,
    )
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=SONNET_MAX_TOKENS,
        temperature=0.7,  # diversity matters more than determinism here
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [block.text for block in response.content if hasattr(block, "text")]
    raw = "".join(parts).strip()
    # Strip any accidental markdown code fences Sonnet sometimes adds despite
    # the explicit "no code fences" instruction.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    return raw.strip()


# ─── variations index page ────────────────────────────────────────────────────

def _build_variations_index(
    *,
    client_display_name: str,
    variations: list[dict[str, Any]],
) -> str:
    """Render a simple landing page listing every variation with its thesis.
    This is what the client sees first when they open the preview URL."""
    cards = []
    for v in variations:
        n = v["variation_number"]
        thesis = html_module.escape(v["thesis"])
        cards.append(
            f"""    <a href="./variation-{n}/" class="block border border-gray-200 rounded-lg p-6 hover:border-gray-900 hover:shadow-md transition">
      <div class="text-sm text-gray-500 mb-2">Variation {n}</div>
      <div class="text-gray-900">{thesis}</div>
    </a>"""
        )
    cards_html = "\n".join(cards)
    safe_name = html_module.escape(client_display_name)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_name} — Homepage Variations</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white text-gray-900">
  <main class="max-w-3xl mx-auto px-6 py-16">
    <header class="mb-12">
      <div class="text-sm uppercase tracking-wide text-gray-500 mb-2">ParlayVU · Dylan</div>
      <h1 class="text-4xl font-bold mb-3">{safe_name} — Homepage Drafts</h1>
      <p class="text-gray-600">Each variation explores a distinct design thesis. Click into any direction to view the full draft, then tell us which threads are worth pulling on.</p>
    </header>
    <div class="grid gap-4">
{cards_html}
    </div>
    <footer class="mt-16 pt-6 border-t border-gray-200 text-sm text-gray-500">
      Generated by Dylan. Drafts only — placeholder imagery, working copy. Real images and final wording added once you pick a direction.
    </footer>
  </main>
</body>
</html>
"""


# ─── public entry point ───────────────────────────────────────────────────────

async def generate_homepage_variations(
    *,
    client_id: str,
    variation_count: int = 5,
    deploy: bool = True,
) -> dict[str, Any]:
    """Generate N homepage variations for a client and (optionally) deploy them
    under one Cloudflare Pages preview project.

    Args:
        client_id: ParlayVU client id (must have an active config.yaml).
        variation_count: Clamped to [1, 10]. Defaults to 5.
        deploy: If True, calls deploy_static_directory_to_cloudflare after
            writing files. The deploy is best-effort — failures are reported in
            the result but don't raise.

    Returns:
        {
          "status": "generated" | "deployed",
          "client_id": str,
          "variations": [{variation_number, thesis, path, bytes}, ...],
          "index_path": str,
          "preview_url": str | None,
          "deploy": {... raw deploy helper result ...} | None,
          "memory_output_id": str | None,
          "event_id": str | None,
        }

    Raises:
        ClientConfigError: if the client_id isn't onboarded.
    """
    # Validate client up-front; raises ClientConfigError with a clear message.
    config = load_client_config(client_id)

    # Clamp variation count.
    n = max(MIN_VARIATIONS, min(MAX_VARIATIONS, int(variation_count)))

    # Read context files.
    client_root = CLIENT_ARTIFACTS_ROOT / client_id
    brief = _read_capped(client_root / BRIEF_PATH)
    references_md = _read_capped(client_root / REFERENCES_PATH)
    design_notes = _read_capped(client_root / DESIGN_NOTES_PATH)

    # Fetch reference site content concurrently.
    urls = _extract_reference_urls(references_md)
    logger.info(
        "Dylan variations: client=%s n=%d references=%d", client_id, n, len(urls)
    )
    fetched = await _fetch_references(urls)
    fetched_block = _format_fetched_references(fetched)

    # Set up the Anthropic client once and reuse across variation calls.
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is required for Dylan variation generation"
        )
    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Generate variations concurrently — each is an independent LLM call.
    async def _produce(i: int) -> dict[str, Any]:
        html = await _generate_variation_html(
            client_display_name=config.display_name,
            variation_number=i,
            total=n,
            brief=brief,
            references_index=references_md or "",
            fetched_references=fetched_block,
            design_notes=design_notes,
            client=client,
        )
        write_info = _write_site_file(client_id, f"variation-{i}/index.html", html)
        thesis_idx = (i - 1) % len(DYLAN_VARIATION_THESES)
        return {
            "variation_number": i,
            "thesis": DYLAN_VARIATION_THESES[thesis_idx],
            "path": write_info["path"],
            "bytes": write_info["bytes"],
        }

    variations = await asyncio.gather(*(_produce(i) for i in range(1, n + 1)))

    # Write the landing-page index that links to each variation.
    index_html = _build_variations_index(
        client_display_name=config.display_name,
        variations=list(variations),
    )
    index_info = _write_site_file(client_id, "index.html", index_html)

    # Optional deploy. Imported lazily to avoid pulling subprocess deps into
    # tests that don't exercise this path.
    deploy_result: Optional[dict[str, Any]] = None
    preview_url: Optional[str] = None
    if deploy:
        try:
            from app.agents.tools.dylan_tools import (
                deploy_static_directory_to_cloudflare,
            )

            sites_dir = (CLIENT_ARTIFACTS_ROOT / client_id / SITES_SUBPATH).resolve()
            project_name = f"{client_id}-previews"
            deploy_result = deploy_static_directory_to_cloudflare(
                directory=sites_dir,
                project_name=project_name,
            )
            preview_url = deploy_result.get("url")
        except Exception as exc:
            logger.exception("Dylan variations deploy step failed")
            deploy_result = {"status": "error", "message": str(exc)}

    # Audit.
    status = "deployed" if (deploy and deploy_result and deploy_result.get("status") in {"success", "deployed"}) else "generated"
    memory_output_id = record_generated_output(
        client_id=client_id,
        project_id=None,
        agent_name="dylan",
        output_type="homepage_variations",
        title=f"{config.display_name} — {n} homepage variations",
        content=None,
        uri=preview_url,
        status=status,
        metadata={
            "variations": list(variations),
            "index_path": index_info["path"],
            "preview_url": preview_url,
            "deploy": deploy_result,
            "reference_urls_used": urls,
        },
    )
    event_id = record_agent_event(
        agent_name="dylan",
        client_id=client_id,
        event_type="homepage_variations_generated",
        channel="api",
        summary=f"Generated {n} homepage variations for {config.display_name}",
        payload={
            "variation_count": n,
            "preview_url": preview_url,
            "memory_output_id": memory_output_id,
        },
    )

    return {
        "status": status,
        "client_id": client_id,
        "variations": list(variations),
        "index_path": index_info["path"],
        "preview_url": preview_url,
        "deploy": deploy_result,
        "memory_output_id": memory_output_id,
        "event_id": event_id,
    }
