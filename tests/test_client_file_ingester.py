"""Tests for app/services/client_file_ingester.py.

The ingester reaches into Teams (Graph) and Anthropic, so every test patches
both. We verify file walks, skip-if-up-to-date semantics, force re-ingest,
unsupported-extension fast-skip, image-only-PDF graceful skip, and the
audit-recording shape.
"""

import asyncio
import io
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from app.client_config import (
    ClientConfig,
    ClientPreferences,
    TeamsConfig,
    clear_client_config_cache,
)
from app.services import client_file_ingester
from app.services.client_file_ingester import (
    _is_skipped_path,
    _is_up_to_date,
    _sanitize_filename,
    _target_md_path,
    ingest_client_files,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _config() -> ClientConfig:
    return ClientConfig(
        client_id="acme",
        display_name="Acme Corp",
        teams=TeamsConfig(team_id="team-x", channel_id="channel-x", template_path="x.docx"),
        preferences=ClientPreferences(),
    )


def _minimal_pdf_bytes(text: str) -> bytes:
    """Build a minimal PDF pypdf can parse and extract text from."""
    from pypdf import PdfWriter
    from pypdf.generic import (
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
    )

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    cs = DecodedStreamObject()
    cs.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))

    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = cs

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _minimal_docx_bytes(text: str) -> bytes:
    from docx import Document
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _fake_anthropic_client(summary_md: str) -> MagicMock:
    """Build an Anthropic-like mock whose messages.create() returns summary_md."""
    block = MagicMock()
    block.text = summary_md
    response = MagicMock()
    response.content = [block]

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def _fake_graph_for_files(files: list[dict], file_bytes: dict[str, bytes]) -> MagicMock:
    """Build a MicrosoftGraphClient mock whose:
      - list_channel_files returns `files` at the root (flat for these tests)
      - download_teams_channel_file(file_path=...) returns file_bytes[file_path]
    """
    graph = MagicMock()

    async def _list(team_id, channel_id, folder_path=None):
        if folder_path:
            return []
        return files

    async def _download(file_path, team_id, channel_id):
        return file_bytes[file_path]

    graph.list_channel_files = AsyncMock(side_effect=_list)
    graph.download_teams_channel_file = AsyncMock(side_effect=_download)
    return graph


# ─── filename + path helpers ──────────────────────────────────────────────────

class SanitizeFilenameTests(unittest.TestCase):
    def test_strips_extension_and_flattens(self):
        self.assertEqual(_sanitize_filename("Reports/Q3-2026 Report.pdf"), "reports-q3-2026-report.md")
        self.assertEqual(_sanitize_filename("Nested/Subfolder/Q4 — Final.docx"), "nested-subfolder-q4-final.md")
        self.assertEqual(_sanitize_filename("simple.pdf"), "simple.md")

    def test_unknown_collapses_to_document(self):
        self.assertEqual(_sanitize_filename("///.pdf"), "document.md")


class SkipFolderTests(unittest.TestCase):
    def test_skips_06_templates(self):
        self.assertTrue(_is_skipped_path("06_Templates/Meeting_Notes_Template.docx"))
        self.assertTrue(_is_skipped_path("06_Templates"))
        self.assertTrue(_is_skipped_path("06_Templates/"))

    def test_skips_meeting_notes_outputs(self):
        self.assertTrue(
            _is_skipped_path("03_Deliverables/Meeting Notes/ramair-weekly.docx")
        )

    def test_does_not_skip_other_03_deliverables(self):
        # Only Meeting Notes inside 03_Deliverables is skipped — other Dylan
        # deliverables (sites/, etc.) should still be ingestible if they ever
        # become a thing.
        self.assertFalse(_is_skipped_path("03_Deliverables/sites/variation-1/index.html"))
        self.assertFalse(_is_skipped_path("03_Deliverables/some-other-doc.pdf"))

    def test_does_not_skip_reports_or_brief(self):
        self.assertFalse(_is_skipped_path("Reports/Q3-2026.pdf"))
        self.assertFalse(_is_skipped_path("00_Client_Brief/brand-voice.pdf"))

    def test_handles_backslash_paths(self):
        self.assertTrue(_is_skipped_path("06_Templates\\Meeting_Notes_Template.docx"))


class UpToDateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "report.md"

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_target_is_not_up_to_date(self):
        future = datetime.now(timezone.utc) - timedelta(days=1)
        self.assertFalse(_is_up_to_date(self.path, future))

    def test_unknown_source_modified_treats_as_stale(self):
        self.path.write_text("hi", encoding="utf-8")
        self.assertFalse(_is_up_to_date(self.path, None))

    def test_target_newer_than_source_is_up_to_date(self):
        old_source = datetime.now(timezone.utc) - timedelta(days=2)
        self.path.write_text("hi", encoding="utf-8")
        self.assertTrue(_is_up_to_date(self.path, old_source))

    def test_target_older_than_source_is_stale(self):
        self.path.write_text("hi", encoding="utf-8")
        # Set the file's mtime well in the past.
        old = (datetime.now(timezone.utc) - timedelta(days=2)).timestamp()
        os.utime(self.path, (old, old))
        recent_source = datetime.now(timezone.utc) - timedelta(hours=1)
        self.assertFalse(_is_up_to_date(self.path, recent_source))


# ─── full ingest flow ─────────────────────────────────────────────────────────

class IngestClientFilesTests(unittest.TestCase):

    def setUp(self):
        clear_client_config_cache()
        self._tmp = TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        # Redirect the artifacts root so we write into a tempdir instead of the repo.
        self._root_patch = patch.object(
            client_file_ingester, "CLIENT_ARTIFACTS_ROOT", self.tmp_root
        )
        self._root_patch.start()
        # Sufficient fake key to bypass the os.getenv check.
        self._env = patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key-for-tests"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._root_patch.stop()
        clear_client_config_cache()
        self._tmp.cleanup()

    def _patches(self, graph_mock, anthropic_mock):
        """Common patch stack for the unit under test."""
        return (
            patch.object(client_file_ingester, "load_client_config", return_value=_config()),
            patch.object(client_file_ingester, "MicrosoftGraphClient", return_value=graph_mock),
            patch.object(client_file_ingester.anthropic, "AsyncAnthropic", return_value=anthropic_mock),
            patch.object(client_file_ingester, "record_generated_output", return_value="out-1"),
            patch.object(client_file_ingester, "record_agent_event", return_value="evt-1"),
        )

    def test_ingests_pdf_and_writes_markdown_summary(self):
        files = [
            {"name": "Q3-2026.pdf", "kind": "file", "size": 1234,
             "last_modified": "2026-05-25T12:00:00Z",
             "web_url": "https://t/p", "path": "Reports/Q3-2026.pdf"},
        ]
        graph = _fake_graph_for_files(
            files,
            {"Reports/Q3-2026.pdf": _minimal_pdf_bytes("Q3 revenue grew 18%")},
        )
        summary = "# Q3 2026 Performance Report\n\n## Executive Summary\nRevenue is up 18%.\n"
        anthropic_client = _fake_anthropic_client(summary)

        patches = self._patches(graph, anthropic_client)
        for p in patches: p.start()
        try:
            result = asyncio.run(ingest_client_files("acme"))
        finally:
            for p in reversed(patches): p.stop()

        self.assertEqual(len(result["ingested"]), 1)
        self.assertEqual(result["ingested"][0]["path"], "Reports/Q3-2026.pdf")
        target_path = self.tmp_root / "acme" / "01_Source_Material" / "reports" / "reports-q3-2026.md"
        self.assertTrue(target_path.exists())
        body = target_path.read_text(encoding="utf-8")
        # Provenance frontmatter + LLM summary both present.
        self.assertIn("Ingested by ParlayVU client_file_ingester", body)
        self.assertIn("Q3 2026 Performance Report", body)

    def test_skips_when_target_md_is_newer_than_source(self):
        target = self.tmp_root / "acme" / "01_Source_Material" / "reports" / "reports-q3-2026.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("existing summary", encoding="utf-8")
        # Source modified 2 days ago, target is fresh → skip.
        files = [
            {"name": "Q3-2026.pdf", "kind": "file", "size": 1234,
             "last_modified": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
             "web_url": "https://t/p", "path": "Reports/Q3-2026.pdf"},
        ]
        graph = _fake_graph_for_files(files, {"Reports/Q3-2026.pdf": b""})
        anthropic_client = _fake_anthropic_client("")

        patches = self._patches(graph, anthropic_client)
        for p in patches: p.start()
        try:
            result = asyncio.run(ingest_client_files("acme"))
        finally:
            for p in reversed(patches): p.stop()

        self.assertEqual(len(result["ingested"]), 0)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["status"], "skipped_up_to_date")
        # Graph download should not have been called for the skipped file.
        graph.download_teams_channel_file.assert_not_awaited()
        # Anthropic should not have been called.
        anthropic_client.messages.create.assert_not_awaited()

    def test_force_reingests_even_when_target_is_newer(self):
        target = self.tmp_root / "acme" / "01_Source_Material" / "reports" / "reports-q3-2026.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("existing summary", encoding="utf-8")
        files = [
            {"name": "Q3-2026.pdf", "kind": "file", "size": 1234,
             "last_modified": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
             "web_url": "https://t/p", "path": "Reports/Q3-2026.pdf"},
        ]
        graph = _fake_graph_for_files(
            files,
            {"Reports/Q3-2026.pdf": _minimal_pdf_bytes("Fresh extraction.")},
        )
        anthropic_client = _fake_anthropic_client("# Fresh summary\n")

        patches = self._patches(graph, anthropic_client)
        for p in patches: p.start()
        try:
            result = asyncio.run(ingest_client_files("acme", force=True))
        finally:
            for p in reversed(patches): p.stop()

        self.assertEqual(len(result["ingested"]), 1)
        # Target file was overwritten.
        self.assertIn("Fresh summary", target.read_text(encoding="utf-8"))

    def test_unsupported_extensions_are_fast_skipped_without_download(self):
        files = [
            {"name": "logo.png", "kind": "file", "size": 1000,
             "last_modified": None, "web_url": "https://t/l", "path": "Brand/logo.png"},
            {"name": "data.xlsx", "kind": "file", "size": 2000,
             "last_modified": None, "web_url": "https://t/d", "path": "Reports/data.xlsx"},
        ]
        graph = _fake_graph_for_files(files, {})  # download_bytes empty — should never be called
        anthropic_client = _fake_anthropic_client("")

        patches = self._patches(graph, anthropic_client)
        for p in patches: p.start()
        try:
            result = asyncio.run(ingest_client_files("acme"))
        finally:
            for p in reversed(patches): p.stop()

        self.assertEqual(len(result["ingested"]), 0)
        self.assertEqual(len(result["skipped"]), 2)
        graph.download_teams_channel_file.assert_not_awaited()
        anthropic_client.messages.create.assert_not_awaited()

    def test_image_only_pdf_skipped_with_note(self):
        # PDF that parses but has no extractable text → empty extraction.
        # We simulate this by patching detect_extractor to return a callable
        # that yields empty text, since constructing a real text-less PDF
        # programmatically is finicky.
        files = [
            {"name": "scanned.pdf", "kind": "file", "size": 1000,
             "last_modified": None, "web_url": "https://t/s", "path": "Reports/scanned.pdf"},
        ]
        graph = _fake_graph_for_files(files, {"Reports/scanned.pdf": b"%PDF-1.4\n%fake but bytes are downloaded"})
        anthropic_client = _fake_anthropic_client("")

        patches = list(self._patches(graph, anthropic_client))
        patches.append(
            patch.object(client_file_ingester, "detect_extractor", return_value=lambda data: "")
        )
        for p in patches: p.start()
        try:
            result = asyncio.run(ingest_client_files("acme"))
        finally:
            for p in reversed(patches): p.stop()

        self.assertEqual(len(result["ingested"]), 0)
        self.assertEqual(len(result["skipped"]), 1)
        self.assertEqual(result["skipped"][0]["status"], "skipped_no_text")
        self.assertIn("OCR", result["skipped"][0]["note"])
        anthropic_client.messages.create.assert_not_awaited()

    def test_records_audit_with_counts(self):
        files = [
            {"name": "Q3.pdf", "kind": "file", "size": 100,
             "last_modified": "2026-05-25T12:00:00Z",
             "web_url": "https://t/", "path": "Q3.pdf"},
        ]
        graph = _fake_graph_for_files(files, {"Q3.pdf": _minimal_pdf_bytes("summary")})
        anthropic_client = _fake_anthropic_client("# Title\n## Executive Summary\nbody\n")

        patches = self._patches(graph, anthropic_client)
        for p in patches: p.start()
        try:
            with patch.object(client_file_ingester, "record_generated_output", return_value="out-99") as rgo, \
                 patch.object(client_file_ingester, "record_agent_event", return_value="evt-99") as rae:
                result = asyncio.run(ingest_client_files("acme"))
        finally:
            for p in reversed(patches): p.stop()

        self.assertEqual(result["memory_output_id"], "out-99")
        rgo.assert_called_once()
        self.assertEqual(rgo.call_args.kwargs["output_type"], "client_file_ingestion")
        rae.assert_called_once()
        self.assertEqual(rae.call_args.kwargs["event_type"], "client_files_ingested")


if __name__ == "__main__":
    unittest.main()
