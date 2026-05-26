"""Tests for app/tools/client_files_tool.py — Nathan's per-client file
listing and reading (PDF/docx/markdown via Teams SharePoint)."""

import asyncio
import io
import unittest
import zipfile
from unittest.mock import AsyncMock, patch

import httpx

from app.client_config import (
    ClientConfig,
    ClientPreferences,
    TeamsConfig,
    clear_client_config_cache,
)
from app.tools import client_files_tool
from app.tools.client_files_tool import (
    MAX_FILE_CHARS,
    _detect_extractor,
    _extract_docx_text,
    _extract_pdf_text,
    list_client_files,
    read_client_file,
)


def _fake_config() -> ClientConfig:
    return ClientConfig(
        client_id="ramair",
        display_name="RamAir International",
        teams=TeamsConfig(team_id="team-1", channel_id="channel-1", template_path="x.docx"),
        preferences=ClientPreferences(),
    )


def _minimal_pdf_bytes(text: str = "Hello from the Q3 report.") -> bytes:
    """Build a minimal PDF that pypdf can actually parse and extract text from."""
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject

    # pypdf's blank-page + write-content path is the simplest way to produce
    # a parseable PDF with embedded text. Construct via reportlab-less means:
    # use PdfWriter to add a blank page, then patch the content stream to
    # include a text-showing operator so .extract_text() returns something.
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    # Inject a text content stream so extract_text returns our payload.
    from pypdf.generic import (
        ContentStream,
        DecodedStreamObject,
        NameObject,
        TextStringObject,
        create_string_object,
    )

    content_stream_bytes = (
        f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    )
    decoded = DecodedStreamObject()
    decoded.set_data(content_stream_bytes)
    # Wire a tiny font resource so the Tj operator has something to reference.
    from pypdf.generic import DictionaryObject

    font_obj = DictionaryObject()
    font_obj.update({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    resources = DictionaryObject()
    resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font_obj})
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = decoded

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _minimal_docx_bytes(text: str = "Quarterly report body. Action: revisit Q4 plan.") -> bytes:
    """Build a minimal .docx via python-docx."""
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class DetectorTests(unittest.TestCase):
    def test_extractor_matches_extension(self):
        from app.tools.client_files_tool import _decode_text

        self.assertIs(_detect_extractor("foo.md"), _decode_text)
        self.assertIs(_detect_extractor("a/b/foo.txt"), _decode_text)
        self.assertIs(_detect_extractor("Reports/Q3.pdf"), _extract_pdf_text)
        self.assertIs(_detect_extractor("brand.DOCX"), _extract_docx_text)
        self.assertIsNone(_detect_extractor("notes.xlsx"))
        self.assertIsNone(_detect_extractor("image.png"))


class ExtractorTests(unittest.TestCase):
    def test_pdf_extraction_returns_embedded_text(self):
        pdf_bytes = _minimal_pdf_bytes("The Q3 numbers came in 12% above plan.")
        text = _extract_pdf_text(pdf_bytes)
        self.assertIn("Q3", text)
        self.assertIn("12% above plan", text)

    def test_pdf_extraction_raises_for_garbage(self):
        with self.assertRaises(ValueError):
            _extract_pdf_text(b"this is definitely not a PDF")

    def test_docx_extraction_returns_paragraph_text(self):
        docx_bytes = _minimal_docx_bytes("Hello from the docx — revisit Q4 plan.")
        text = _extract_docx_text(docx_bytes)
        self.assertIn("Hello from the docx", text)
        self.assertIn("revisit Q4 plan", text)


class ListClientFilesTests(unittest.TestCase):
    def setUp(self):
        clear_client_config_cache()

    def tearDown(self):
        clear_client_config_cache()

    def test_lists_files_at_root_when_folder_omitted(self):
        graph = AsyncMock()
        graph.list_channel_files = AsyncMock(return_value=[
            {"name": "Reports", "kind": "folder", "size": None, "last_modified": None, "web_url": "https://t/", "path": "Reports"},
            {"name": "client-brief.md", "kind": "file", "size": 1234, "last_modified": None, "web_url": "https://t/c", "path": "client-brief.md"},
        ])
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(list_client_files("ramair"))

        self.assertEqual(result["client_id"], "ramair")
        self.assertEqual(result["client_display_name"], "RamAir International")
        self.assertEqual(result["folder"], "")
        names = [item["name"] for item in result["items"]]
        self.assertIn("Reports", names)
        self.assertIn("client-brief.md", names)
        graph.list_channel_files.assert_awaited_once_with(
            team_id="team-1", channel_id="channel-1", folder_path=None
        )

    def test_list_passes_folder_through(self):
        graph = AsyncMock()
        graph.list_channel_files = AsyncMock(return_value=[
            {"name": "Q3-2026.pdf", "kind": "file", "size": 50000, "last_modified": None, "web_url": "https://t/p", "path": "Reports/Q3-2026.pdf"},
        ])
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(list_client_files("ramair", folder="Reports"))

        self.assertEqual(result["folder"], "Reports")
        self.assertEqual(result["items"][0]["path"], "Reports/Q3-2026.pdf")
        graph.list_channel_files.assert_awaited_once_with(
            team_id="team-1", channel_id="channel-1", folder_path="Reports"
        )

    def test_missing_folder_returns_error_field(self):
        graph = AsyncMock()
        response = httpx.Response(404, request=httpx.Request("GET", "https://x"))
        graph.list_channel_files = AsyncMock(side_effect=httpx.HTTPStatusError("404", request=response.request, response=response))
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(list_client_files("ramair", folder="DoesNotExist"))

        self.assertEqual(result["items"], [])
        self.assertIn("not found", result["error"].lower())


class ReadClientFileTests(unittest.TestCase):
    def setUp(self):
        clear_client_config_cache()

    def tearDown(self):
        clear_client_config_cache()

    def _patched_graph(self, file_bytes: bytes) -> AsyncMock:
        graph = AsyncMock()
        graph.download_teams_channel_file = AsyncMock(return_value=file_bytes)
        return graph

    def test_reads_pdf_and_returns_extracted_text(self):
        pdf = _minimal_pdf_bytes("The Q3 numbers came in 12% above plan.")
        graph = self._patched_graph(pdf)
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(read_client_file("ramair", "Reports/Q3-2026.pdf"))

        self.assertEqual(result["file_type"], "pdf")
        self.assertIn("12% above plan", result["content"])
        self.assertFalse(result["truncated"])
        graph.download_teams_channel_file.assert_awaited_once_with(
            file_path="Reports/Q3-2026.pdf", team_id="team-1", channel_id="channel-1"
        )

    def test_reads_docx_and_returns_paragraph_text(self):
        docx = _minimal_docx_bytes("Hello from the docx file body.")
        graph = self._patched_graph(docx)
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(read_client_file("ramair", "Reports/notes.docx"))

        self.assertEqual(result["file_type"], "docx")
        self.assertIn("Hello from the docx", result["content"])

    def test_reads_markdown_passthrough(self):
        md = b"# Heading\n\nBody text with some content."
        graph = self._patched_graph(md)
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(read_client_file("ramair", "notes.md"))

        self.assertEqual(result["file_type"], "md")
        self.assertIn("# Heading", result["content"])
        self.assertIn("Body text", result["content"])

    def test_unsupported_extension_returns_clear_error(self):
        # Graph should NEVER be called when extension isn't supported.
        graph = AsyncMock()
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(read_client_file("ramair", "image.png"))

        self.assertIn("Unsupported file type", result["error"])
        graph.download_teams_channel_file.assert_not_awaited()

    def test_missing_file_returns_clear_404_message(self):
        graph = AsyncMock()
        response = httpx.Response(404, request=httpx.Request("GET", "https://x"))
        graph.download_teams_channel_file = AsyncMock(side_effect=httpx.HTTPStatusError("404", request=response.request, response=response))
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(read_client_file("ramair", "Reports/missing.pdf"))

        self.assertIn("not found", result["error"].lower())
        self.assertEqual(result["path"], "Reports/missing.pdf")

    def test_empty_path_returns_validation_error(self):
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()):
            result = asyncio.run(read_client_file("ramair", "   "))
        self.assertIn("required", result["error"].lower())

    def test_content_capped_at_max_file_chars(self):
        long_text = ("ABCDEFGHIJ" * 4_000).encode("utf-8")  # 40k chars
        graph = self._patched_graph(long_text)
        with patch.object(client_files_tool, "load_client_config", return_value=_fake_config()), \
             patch.object(client_files_tool, "MicrosoftGraphClient", return_value=graph):
            result = asyncio.run(read_client_file("ramair", "big.md"))

        self.assertEqual(len(result["content"]), MAX_FILE_CHARS)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
