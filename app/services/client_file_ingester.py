"""Pre-ingest client documents (PDF, .docx) into markdown summaries.

For each binary file in a client's Teams channel Files area, this service
produces a structured markdown document at
`client_artifacts/<client_id>/01_Source_Material/reports/<safe-name>.md`
containing an executive summary, key findings, notable data points, open
questions, and the full extracted text.

Those .md files flow through the existing `get_project_context` tool path, so
Nathan picks them up on every Tavus call without any extra Graph round-trip
or extraction latency at conversation time.

Trigger: HTTP `POST /clients/{client_id}/ingest-files` or CLI
`python -m app.services.client_file_ingester <client_id> [--force]`.

Skip semantics: if a target .md already exists and is newer than the source
file's lastModifiedDateTime, the source is skipped. Pass `force=True` to
re-ingest everything regardless of timestamps.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import anthropic
import httpx

from app.agents.prompts import CLIENT_FILE_INGEST_PROMPT_TEMPLATE
from app.client_config import ClientConfigError, load_client_config
from app.microsoft365 import MicrosoftGraphClient
from app.project_memory import record_agent_event, record_generated_output
from app.tools.text_extractors import detect_extractor

logger = logging.getLogger("parlayvu.services.client_file_ingester")


CLIENT_ARTIFACTS_ROOT = Path("client_artifacts")
REPORTS_SUBPATH = Path("01_Source_Material") / "reports"
SONNET_MODEL = "claude-sonnet-4-6"
SONNET_MAX_TOKENS = 4_000

# Cap the extracted-text payload we send to the summarizer. A 100-page report
# would otherwise blow the input budget. The summarizer still gets enough
# material to produce useful Findings + Data Points; verbatim quotes for the
# tail of huge documents can still be retrieved via on-demand read_client_file.
MAX_EXTRACTED_CHARS_TO_SUMMARIZE = 80_000

# File extensions we ingest. Plain markdown/txt files are skipped because
# they're already in the right format and don't need re-summarizing.
INGESTIBLE_EXTENSIONS = (".pdf", ".docx")

# Folders we skip during the walk. These contain content that should NOT be
# re-summarized into the client's project context:
#   - 06_Templates/ holds DOCX templates full of {{PLACEHOLDER}} tokens — a
#     "summary" of these is noise (the renderer's literal field list).
#   - 03_Deliverables/Meeting Notes/ holds Nathan's own .md + .docx meeting
#     note outputs. The .md versions are already markdown; summarizing the
#     .docx version produces a duplicate of content Nathan already has.
# Path prefix match against the source_path returned by list_channel_files.
SKIP_FOLDER_PREFIXES: tuple[str, ...] = (
    "06_Templates/",
    "03_Deliverables/Meeting Notes/",
)


def _sanitize_filename(source_path: str) -> str:
    """Turn a Teams path like 'Reports/Q3-2026 Report.pdf' into a clean .md
    filename like 'reports-q3-2026-report.md'. Keeps the file flat under
    01_Source_Material/reports/ rather than mirroring the source tree, which
    keeps get_project_context's top-3-files-per-folder rule simple."""
    base = source_path.replace("\\", "/").strip("/")
    # Drop the extension, lowercase, replace separators.
    stem = re.sub(r"\.[^./]+$", "", base)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower()
    return f"{safe or 'document'}.md"


def _parse_iso8601(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    # Graph timestamps are like "2026-05-25T22:13:46.042871Z"
    try:
        return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _target_md_path(client_id: str, source_path: str) -> Path:
    return CLIENT_ARTIFACTS_ROOT / client_id / REPORTS_SUBPATH / _sanitize_filename(source_path)


def _is_up_to_date(target: Path, source_modified: Optional[datetime]) -> bool:
    """True if the existing .md is newer than the source's last-modified time
    (or if we can't determine the source time — conservative: re-ingest)."""
    if not target.is_file():
        return False
    if source_modified is None:
        return False
    try:
        target_mtime = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return False
    return target_mtime >= source_modified


async def _walk_channel_files(
    graph: MicrosoftGraphClient,
    *,
    team_id: str,
    channel_id: str,
    folder: Optional[str] = None,
    max_depth: int = 4,
    _depth: int = 0,
) -> list[dict[str, Any]]:
    """Recursively list every file in a client's Teams channel. Returns a flat
    list of file entries (folders are descended into, not returned). Depth is
    capped to avoid runaway traversal of pathological trees."""
    if _depth >= max_depth:
        return []
    try:
        items = await graph.list_channel_files(
            team_id=team_id, channel_id=channel_id, folder_path=folder
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.info("Folder %r not present in channel — skipping", folder)
            return []
        raise

    files: list[dict[str, Any]] = []
    for item in items:
        kind = item.get("kind")
        item_path = item.get("path", "")
        if _is_skipped_path(item_path):
            logger.info("Skipping %r (matches SKIP_FOLDER_PREFIXES)", item_path)
            continue
        if kind == "file":
            files.append(item)
        elif kind == "folder":
            files.extend(
                await _walk_channel_files(
                    graph,
                    team_id=team_id,
                    channel_id=channel_id,
                    folder=item["path"],
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )
            )
    return files


def _is_skipped_path(path: str) -> bool:
    """True if the given Teams-channel-relative path falls under any folder we
    deliberately do not ingest (templates, Nathan's own outputs, etc.)."""
    normalized = path.replace("\\", "/").strip("/")
    for prefix in SKIP_FOLDER_PREFIXES:
        clean = prefix.strip("/")
        if normalized == clean or normalized.startswith(clean + "/"):
            return True
    return False


def _page_count_label(extracted_text: str) -> str:
    """Quick heuristic for the prompt header so the summarizer has a sense of
    document scale without us computing the real page count."""
    if "--- page " in extracted_text:
        markers = re.findall(r"--- page (\d+) ---", extracted_text)
        if markers:
            return f"~{markers[-1]} pages"
    return "page count unknown"


async def _summarize_to_markdown(
    *,
    client_display_name: str,
    source_path: str,
    extracted_text: str,
    anthropic_client: anthropic.AsyncAnthropic,
) -> str:
    """Call Sonnet 4.6 to produce the structured markdown summary. Returns the
    raw markdown body (the section beginning with the level-1 title)."""
    capped = extracted_text
    if len(capped) > MAX_EXTRACTED_CHARS_TO_SUMMARIZE:
        capped = capped[:MAX_EXTRACTED_CHARS_TO_SUMMARIZE] + (
            "\n\n[...truncated for summarization; full text available via read_client_file...]"
        )

    prompt = CLIENT_FILE_INGEST_PROMPT_TEMPLATE.format(
        source_path=source_path,
        client_display_name=client_display_name,
        char_count=len(extracted_text),
        page_count_label=_page_count_label(extracted_text),
        extracted_text=capped,
    )
    response = await anthropic_client.messages.create(
        model=SONNET_MODEL,
        max_tokens=SONNET_MAX_TOKENS,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [block.text for block in response.content if hasattr(block, "text")]
    body = "".join(parts).strip()
    # Defensive: strip accidental code fences.
    if body.startswith("```"):
        body = re.sub(r"^```[a-zA-Z]*\n", "", body)
        body = re.sub(r"\n```\s*$", "", body)
    return body.strip()


def _build_md_frontmatter(
    *,
    source_path: str,
    source_modified: Optional[datetime],
    char_count: int,
) -> str:
    """Comment header at the top of the .md so a future re-ingester (or human
    reviewer) can see provenance at a glance. Lives above the level-1 title
    Sonnet produces — markdown renders comments invisibly."""
    ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    modified_line = (
        source_modified.strftime("%Y-%m-%d %H:%M UTC") if source_modified else "unknown"
    )
    return (
        "<!--\n"
        f"  Ingested by ParlayVU client_file_ingester.\n"
        f"  Source: {source_path}\n"
        f"  Source last modified: {modified_line}\n"
        f"  Ingested at: {ingested_at}\n"
        f"  Extracted text size: {char_count} characters\n"
        f"  Re-ingest with: python -m app.services.client_file_ingester <client_id> [--force]\n"
        "-->\n\n"
    )


async def _ingest_one(
    *,
    client_id: str,
    client_display_name: str,
    file_item: dict[str, Any],
    graph: MicrosoftGraphClient,
    anthropic_client: anthropic.AsyncAnthropic,
    force: bool,
) -> dict[str, Any]:
    """Ingest a single file. Returns a dict describing what happened."""
    source_path = file_item["path"]
    extractor = detect_extractor(source_path)
    if extractor is None:
        return {"path": source_path, "status": "skipped_unsupported"}

    target = _target_md_path(client_id, source_path)
    source_modified = _parse_iso8601(file_item.get("last_modified"))

    if not force and _is_up_to_date(target, source_modified):
        return {
            "path": source_path,
            "status": "skipped_up_to_date",
            "target": str(target).replace("\\", "/"),
        }

    try:
        data = await graph.download_teams_channel_file(
            file_path=source_path,
            team_id=file_item.get("team_id"),  # may be unused — present in some shapes
            channel_id=file_item.get("channel_id"),
        )
    except TypeError:
        # download_teams_channel_file's signature doesn't take team/channel
        # from file_item — it gets them from the calling context. We always
        # pass them via the closure in ingest_client_files.
        raise

    extracted_text = extractor(data)
    if not extracted_text.strip():
        return {
            "path": source_path,
            "status": "skipped_no_text",
            "note": "Document parsed but contained no extractable text (image-only PDF?). Consider OCR.",
        }

    summary_md = await _summarize_to_markdown(
        client_display_name=client_display_name,
        source_path=source_path,
        extracted_text=extracted_text,
        anthropic_client=anthropic_client,
    )

    frontmatter = _build_md_frontmatter(
        source_path=source_path,
        source_modified=source_modified,
        char_count=len(extracted_text),
    )
    final = frontmatter + summary_md + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(final, encoding="utf-8")

    return {
        "path": source_path,
        "status": "ingested",
        "target": str(target).replace("\\", "/"),
        "extracted_chars": len(extracted_text),
        "summary_chars": len(summary_md),
    }


async def ingest_client_files(
    client_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Walk a client's Teams channel, ingest every supported file into
    markdown under client_artifacts/<client_id>/01_Source_Material/reports/.

    Args:
        client_id: ParlayVU client id (must have active config.yaml).
        force: If True, re-ingest every file even if the existing .md is newer
            than the source's last-modified timestamp.

    Returns:
        {client_id, ingested: [...], skipped: [...], errors: [...]}
        Each entry has at least `path` and `status`. `ingested` entries also
        include `target`, `extracted_chars`, `summary_chars`.
    """
    config = load_client_config(client_id)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is required for client file ingestion"
        )
    anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
    graph = MicrosoftGraphClient()

    # Wrap download to inject the per-client team/channel without polluting the
    # public Graph helper signature.
    team_id = config.teams.team_id
    channel_id = config.teams.channel_id

    async def _download(file_path: str) -> bytes:
        return await graph.download_teams_channel_file(
            file_path=file_path, team_id=team_id, channel_id=channel_id
        )

    # Walk the channel.
    try:
        all_files = await _walk_channel_files(
            graph, team_id=team_id, channel_id=channel_id, folder=None
        )
    except Exception as exc:
        logger.exception("Channel walk failed for %s", client_id)
        return {
            "client_id": client_id,
            "client_display_name": config.display_name,
            "ingested": [],
            "skipped": [],
            "errors": [{"path": "(channel root)", "error": str(exc)}],
            "memory_output_id": None,
            "event_id": None,
        }

    logger.info(
        "Ingester: client=%s found %d files in channel", client_id, len(all_files)
    )

    ingested: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    # Sequential rather than concurrent to keep Anthropic call rate sane and
    # to make log output readable. If we ever ingest 100+ files per client
    # we'll revisit with a bounded semaphore.
    for file_item in all_files:
        source_path = file_item.get("path", "(unknown)")
        # If the extension isn't ingestible, fast-skip without downloading.
        if not source_path.lower().endswith(INGESTIBLE_EXTENSIONS):
            skipped.append({"path": source_path, "status": "skipped_unsupported"})
            continue

        try:
            # Inline download wrapper so _ingest_one doesn't need team/channel.
            # We do the download here and pass the bytes via the file_item.
            extractor = detect_extractor(source_path)
            if extractor is None:
                skipped.append({"path": source_path, "status": "skipped_unsupported"})
                continue

            target = _target_md_path(client_id, source_path)
            source_modified = _parse_iso8601(file_item.get("last_modified"))
            if not force and _is_up_to_date(target, source_modified):
                skipped.append({
                    "path": source_path,
                    "status": "skipped_up_to_date",
                    "target": str(target).replace("\\", "/"),
                })
                continue

            data = await _download(source_path)
            extracted_text = extractor(data)
            if not extracted_text.strip():
                skipped.append({
                    "path": source_path,
                    "status": "skipped_no_text",
                    "note": "Document parsed but contained no extractable text (image-only PDF?). Consider OCR.",
                })
                continue

            summary_md = await _summarize_to_markdown(
                client_display_name=config.display_name,
                source_path=source_path,
                extracted_text=extracted_text,
                anthropic_client=anthropic_client,
            )
            frontmatter = _build_md_frontmatter(
                source_path=source_path,
                source_modified=source_modified,
                char_count=len(extracted_text),
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(frontmatter + summary_md + "\n", encoding="utf-8")

            ingested.append({
                "path": source_path,
                "status": "ingested",
                "target": str(target).replace("\\", "/"),
                "extracted_chars": len(extracted_text),
                "summary_chars": len(summary_md),
            })
            logger.info("Ingested %s -> %s", source_path, target)
        except Exception as exc:
            logger.exception("Ingest failed for %s", source_path)
            errors.append({"path": source_path, "error": str(exc)})

    # Audit.
    memory_output_id = record_generated_output(
        client_id=client_id,
        project_id=None,
        agent_name="dylan",  # ingester is infrastructural; "dylan" or "system" both fine. Picking system-ish "nathan" since Nathan benefits.
        output_type="client_file_ingestion",
        title=f"{config.display_name} — file ingestion ({len(ingested)} ingested, {len(skipped)} skipped, {len(errors)} errors)",
        content=None,
        uri=None,
        status="completed" if not errors else "partial",
        metadata={
            "ingested": ingested,
            "skipped": skipped,
            "errors": errors,
            "force": force,
        },
    )
    event_id = record_agent_event(
        agent_name="nathan",
        client_id=client_id,
        event_type="client_files_ingested",
        channel="api",
        summary=(
            f"Ingested {len(ingested)} files for {config.display_name} "
            f"(skipped {len(skipped)}, errors {len(errors)})"
        ),
        payload={
            "ingested_count": len(ingested),
            "skipped_count": len(skipped),
            "error_count": len(errors),
            "memory_output_id": memory_output_id,
        },
    )

    return {
        "client_id": client_id,
        "client_display_name": config.display_name,
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors,
        "memory_output_id": memory_output_id,
        "event_id": event_id,
    }


# ─── CLI entry point ─────────────────────────────────────────────────────────

def _cli() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest a client's Teams channel files into markdown summaries that "
            "ground Nathan's answers without a Graph round-trip mid-call."
        )
    )
    parser.add_argument("client_id", help="Active client_id (e.g. 'ramair')")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest every file even if the existing .md is newer than the source.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show DEBUG-level logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        result = asyncio.run(ingest_client_files(args.client_id, force=args.force))
    except ClientConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: ingestion failed: {exc}", file=sys.stderr)
        return 1

    display = result.get("client_display_name") or result.get("client_id") or args.client_id
    print(f"\n== Ingestion complete for {display} ==")
    print(f"  Ingested: {len(result['ingested'])}")
    for entry in result["ingested"]:
        print(f"    + {entry['path']} -> {entry['target']} ({entry['summary_chars']} chars)")
    print(f"  Skipped : {len(result['skipped'])}")
    for entry in result["skipped"]:
        note = f" ({entry.get('note') or entry.get('status')})"
        print(f"    - {entry['path']}{note}")
    if result["errors"]:
        print(f"  Errors  : {len(result['errors'])}")
        for entry in result["errors"]:
            print(f"    ! {entry['path']}: {entry['error']}")
        print()
        # Surface the most likely fix based on what the error text says.
        # The error strings come from upstream SDKs / Graph; we keyword-match
        # rather than parse them to stay resilient to message changes.
        joined = " ".join(str(e.get("error", "")) for e in result["errors"]).lower()
        if "credit balance" in joined or "insufficient" in joined or "billing" in joined:
            print(
                "  Likely fix: Anthropic API credit balance is too low. Top up "
                "at https://console.anthropic.com/settings/billing — a typical "
                "ingestion run is well under $1."
            )
        elif "401" in joined or "unauthorized" in joined:
            print(
                "  Likely fix: MICROSOFT_CLIENT_SECRET in .env has expired or "
                "doesn't match the value set on the Container App. Check Azure "
                "portal -> Entra ID -> App registrations -> ParlayVU Agents -> "
                "Certificates & secrets."
            )
        elif "403" in joined or "forbidden" in joined:
            print(
                "  Likely fix: the Graph app registration is missing a "
                "permission. Check that Files.Read.All and Sites.Read.All are "
                "admin-consented for the ParlayVU Agents app."
            )
        else:
            print(
                "  Check the error messages above and the application logs for "
                "context. The most common failures are Anthropic billing and "
                "Microsoft auth — both surface clearly when they're the cause."
            )
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(_cli())
