import os
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Tests that exercise the Teams-download path force the local-first lookup
# to miss by pointing _ARTIFACTS_ROOT at a path that can't exist.
_NO_LOCAL_ARTIFACTS_DIR = Path("__no_local_artifacts_for_tests__")

from fastapi.testclient import TestClient

from app.main import app
from app.microsoft365 import (
    Microsoft365Settings,
    MicrosoftGraphClient,
    build_meeting_notes_docx,
    build_meeting_notes_markdown,
    build_meeting_notes_template_placeholders,
    build_onenote_meeting_page_html,
    get_microsoft365_settings,
    mailbox_status,
    render_meeting_notes_template_docx,
)


class Microsoft365Tests(unittest.TestCase):
    def test_settings_collect_agent_mailboxes(self):
        with patch.dict(
            os.environ,
            {
                "MICROSOFT_TENANT_ID": "tenant",
                "MICROSOFT_CLIENT_ID": "client",
                "MICROSOFT_CLIENT_SECRET": "secret",
                "NATHAN_MAILBOX": "nathan@parlayvu.ai",
                "AVA_MAILBOX": "ava@parlayvu.ai",
                "ONENOTE_NOTEBOOK_NAME": "RamAir",
                "ONENOTE_SECTION_NAME": "Meeting Notes",
            },
            clear=True,
        ):
            settings = get_microsoft365_settings()

        self.assertTrue(settings.configured)
        self.assertEqual(settings.agent_mailboxes["nathan"], "nathan@parlayvu.ai")
        self.assertEqual(settings.agent_mailboxes["ava"], "ava@parlayvu.ai")
        self.assertEqual(settings.onenote_owner_mailbox, "nathan@parlayvu.ai")
        self.assertEqual(settings.onenote_section_name, "Meeting Notes")
        self.assertFalse(settings.allow_send)

    def test_mailbox_status_does_not_expose_secrets(self):
        settings = Microsoft365Settings(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            graph_scope="scope",
            webhook_client_state="state",
            allow_send=False,
            agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
        )

        status = mailbox_status(settings)

        self.assertTrue(status["configured"])
        self.assertEqual(status["agents"]["nathan"]["mailbox"], "nathan@parlayvu.ai")
        self.assertIn("onenote", status)
        self.assertIn("files", status)
        self.assertNotIn("client_secret", status)

    def test_send_email_requires_explicit_allow_send(self):
        settings = Microsoft365Settings(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            graph_scope="scope",
            webhook_client_state="state",
            allow_send=False,
            agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
        )

        client = MicrosoftGraphClient(settings)

        with self.assertRaises(PermissionError):
            import asyncio

            asyncio.run(
                client.send_email(
                    agent_name="nathan",
                    to_recipients=["client@example.com"],
                    subject="Draft",
                    body="Body",
                )
            )

    def test_m365_status_endpoint(self):
        client = TestClient(app)
        response = client.get("/m365/status")

        self.assertEqual(response.status_code, 200)
        self.assertIn("agents", response.json())

    def test_build_onenote_meeting_page_html_escapes_content(self):
        html = build_onenote_meeting_page_html(
            title="RamAir <Weekly>",
            summary="Review <pipeline> progress.",
            client_id="ramair",
            project_id="ramair-straight-from-the-hart",
        )

        self.assertIn("<title>RamAir &lt;Weekly&gt;</title>", html)
        self.assertIn("ParlayVU project memory", html)
        self.assertIn("Review &lt;pipeline&gt; progress.", html)

    def test_build_meeting_notes_files_are_machine_and_word_friendly(self):
        markdown = build_meeting_notes_markdown(
            title="RamAir Weekly",
            summary="Decisions and next steps.",
            client_id="ramair",
            project_id="ramair-straight-from-the-hart",
        )
        docx = build_meeting_notes_docx(
            title="RamAir Weekly",
            summary="Decisions and next steps.",
            client_id="ramair",
            project_id="ramair-straight-from-the-hart",
        )

        self.assertIn("# RamAir Weekly", markdown)
        self.assertIn("Source of truth: ParlayVU project memory", markdown)
        with zipfile.ZipFile(BytesIO(docx)) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("RamAir Weekly", document)
        self.assertIn("Decisions and next steps.", document)

    def test_render_meeting_notes_template_docx_replaces_placeholders(self):
        template = self._minimal_docx(
            "<w:p><w:r><w:t>MEETING NOTES</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{MEETING_TITLE}}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{SUMMARY}}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{NEXT_STEPS}}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{CLIENT}}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{CLIENT_NAME}}</w:t></w:r></w:p>",
            extra_files={
                "word/header1.xml": (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:p><w:r><w:t>{{CLIENT}}</w:t></w:r></w:p>"
                    "<w:p><w:r><w:t>{{CLIENT_NAME}}</w:t></w:r></w:p>"
                    "</w:hdr>"
                )
            },
        )
        placeholders = build_meeting_notes_template_placeholders(
            title="RamAir Weekly",
            summary="Summary:\nClient-approved recap.\n\nNext Steps:\n- Schedule follow-up.",
            client_id="ramair",
            client_name="RamAir",
            client_full_name="RamAir International",
            project_id="ramair-straight-from-the-hart",
        )

        rendered = render_meeting_notes_template_docx(template, placeholders)

        with zipfile.ZipFile(BytesIO(rendered)) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
            header = archive.read("word/header1.xml").decode("utf-8")
        self.assertIn("MEETING NOTES", document)
        self.assertIn("RamAir Weekly", document)
        self.assertIn("RamAir", document)
        self.assertIn("RamAir International", document)
        self.assertIn("RamAir", header)
        self.assertIn("RamAir International", header)
        self.assertIn("Client-approved recap.", document)
        self.assertIn("- Schedule follow-up.", document)
        self.assertNotIn("Source of truth:", document)
        self.assertNotIn("{{MEETING_TITLE}}", document)
        self.assertNotIn("{{CLIENT}}", document)
        self.assertNotIn("{{CLIENT_NAME}}", document)
        self.assertNotIn("{{CLIENT}}", header)
        self.assertNotIn("{{CLIENT_NAME}}", header)

    def test_render_meeting_notes_template_docx_replaces_split_placeholder_runs(self):
        template = self._minimal_docx(
            "<w:p><w:r><w:t>{{MEETING</w:t></w:r><w:r><w:t>_TITLE}}</w:t></w:r></w:p>"
        )

        rendered = render_meeting_notes_template_docx(
            template,
            build_meeting_notes_template_placeholders(
                title="RamAir Split Placeholder",
                summary="Summary text.",
                client_id="ramair",
                project_id="ramair-straight-from-the-hart",
            ),
        )

        with zipfile.ZipFile(BytesIO(rendered)) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("RamAir Split Placeholder", document)
        self.assertNotIn("{{MEETING", document)

    @staticmethod
    def _minimal_docx(document_body: str, extra_files: dict[str, str] | None = None) -> bytes:
        """Build a minimal but spec-compliant DOCX for tests.

        Earlier versions of this helper produced a DOCX with empty
        `[Content_Types].xml` and `_rels/.rels` files - good enough for
        naive string-replace rendering but rejected by python-docx, which
        requires actual content-type overrides and relationship targets to
        parse the package. The bodies below are the minimum spec-compliant
        content for an Office Open XML word document.
        """
        buffer = BytesIO()
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{document_body}<w:sectPr/></w:body>"
            "</w:document>"
        )
        content_types_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        )
        package_rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        )
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", package_rels_xml)
            archive.writestr("word/document.xml", document_xml)
            for filename, content in (extra_files or {}).items():
                archive.writestr(filename, content)
        return buffer.getvalue()

    def test_upload_drive_file_puts_content_to_sharepoint_path(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "id": "item-1",
                    "name": "ramair-weekly.md",
                    "webUrl": "https://sharepoint.example/ramair-weekly.md",
                    "size": 12,
                    "parentReference": {"driveId": "drive-1"},
                }

        class FakeClient:
            last_put = None

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def put(self, url, headers=None, content=None):
                FakeClient.last_put = {"url": url, "headers": headers, "content": content}
                return FakeResponse()

        settings = Microsoft365Settings(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            graph_scope="scope",
            webhook_client_state="state",
            allow_send=False,
            agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
        )
        graph_client = MicrosoftGraphClient(settings)

        with patch.object(graph_client, "get_access_token", AsyncMock(return_value="token")):
            with patch("app.microsoft365.httpx.AsyncClient", FakeClient):
                import asyncio

                item = asyncio.run(
                    graph_client.upload_drive_file(
                        drive_id="drive-1",
                        folder_item_id="folder-1",
                        folder_path="03_Deliverables/Meeting Notes",
                        filename="ramair-weekly.md",
                        content=b"hello",
                        content_type="text/markdown",
                    )
                )

        self.assertEqual(item["id"], "item-1")
        self.assertIn("/drives/drive-1/items/folder-1:/03_Deliverables/Meeting%20Notes/ramair-weekly.md:/content", FakeClient.last_put["url"])
        self.assertEqual(FakeClient.last_put["headers"]["Content-Type"], "text/markdown")

    def test_download_drive_file_gets_sharepoint_path_content(self):
        class FakeResponse:
            content = b"docx-template"

            def raise_for_status(self):
                return None

        class FakeClient:
            last_get = None

            def __init__(self, *args, **kwargs):
                FakeClient.follow_redirects = kwargs.get("follow_redirects")

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def get(self, url, headers=None):
                FakeClient.last_get = {"url": url, "headers": headers}
                return FakeResponse()

        settings = Microsoft365Settings(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            graph_scope="scope",
            webhook_client_state="state",
            allow_send=False,
            agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
        )
        graph_client = MicrosoftGraphClient(settings)

        with patch.object(graph_client, "get_access_token", AsyncMock(return_value="token")):
            with patch("app.microsoft365.httpx.AsyncClient", FakeClient):
                import asyncio

                content = asyncio.run(
                    graph_client.download_drive_file(
                        drive_id="drive-1",
                        folder_item_id="folder-1",
                        file_path="00_Client_Brief/Templates/RamAir Meeting Notes Template.docx",
                    )
                )

        self.assertEqual(content, b"docx-template")
        self.assertTrue(FakeClient.follow_redirects)
        self.assertIn(
            "/drives/drive-1/items/folder-1:/00_Client_Brief/Templates/RamAir%20Meeting%20Notes%20Template.docx:/content",
            FakeClient.last_get["url"],
        )

    def test_create_onenote_page_posts_html_to_configured_section(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "id": "page-1",
                    "title": "Weekly Meeting",
                    "links": {"oneNoteWebUrl": {"href": "https://onenote.example/page-1"}},
                }

        class FakeClient:
            last_post = None

            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, headers=None, content=None, json=None, data=None):
                FakeClient.last_post = {
                    "url": url,
                    "headers": headers,
                    "content": content,
                }
                return FakeResponse()

        settings = Microsoft365Settings(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            graph_scope="scope",
            webhook_client_state="state",
            allow_send=False,
            agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
            onenote_owner_mailbox="owner@example.com",
            onenote_section_id="section-1",
        )
        graph_client = MicrosoftGraphClient(settings)

        with patch.object(graph_client, "get_access_token", AsyncMock(return_value="token")):
            with patch("app.microsoft365.httpx.AsyncClient", FakeClient):
                import asyncio

                page = asyncio.run(
                    graph_client.create_onenote_page(
                        title="Weekly Meeting",
                        html="<html><head><title>Weekly Meeting</title></head><body>Summary</body></html>",
                    )
                )

        self.assertEqual(page["id"], "page-1")
        self.assertEqual(page["webUrl"], "https://onenote.example/page-1")
        self.assertIn("/users/owner@example.com/onenote/sections/section-1/pages", FakeClient.last_post["url"])
        self.assertEqual(FakeClient.last_post["headers"]["Content-Type"], "text/html")
        self.assertIn(b"Weekly Meeting", FakeClient.last_post["content"])

    def test_email_draft_endpoint_uses_graph_client(self):
        graph_client = AsyncMock()
        graph_client.create_email_draft.return_value = {"id": "draft-1", "subject": "Hello"}

        with patch("app.main.MicrosoftGraphClient", return_value=graph_client):
            with patch("app.main.record_agent_event", return_value=None):
                with patch("app.main.request_approval", return_value={"id": "approval-1"}) as approval:
                    client = TestClient(app)
                    response = client.post(
                        "/m365/email-drafts",
                        json={
                            "agent_name": "nathan",
                            "to_recipients": ["client@example.com"],
                            "subject": "Hello",
                            "body": "Draft body",
                            "client_id": "ramair",
                            "project_id": "ramair-straight-from-the-hart",
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"]["id"], "draft-1")
        self.assertEqual(response.json()["approval"]["id"], "approval-1")
        graph_client.create_email_draft.assert_awaited_once()
        approval.assert_called_once()

    def test_email_draft_endpoint_can_skip_approval_request(self):
        graph_client = AsyncMock()
        graph_client.create_email_draft.return_value = {"id": "draft-1", "subject": "Hello"}

        with patch("app.main.MicrosoftGraphClient", return_value=graph_client):
            with patch("app.main.record_agent_event", return_value=None):
                with patch("app.main.request_approval") as approval:
                    client = TestClient(app)
                    response = client.post(
                        "/m365/email-drafts",
                        json={
                            "agent_name": "nathan",
                            "to_recipients": ["client@example.com"],
                            "subject": "Hello",
                            "body": "Draft body",
                            "client_id": "ramair",
                            "project_id": "ramair-straight-from-the-hart",
                            "request_approval": False,
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["approval"])
        approval.assert_not_called()

    def test_onenote_meeting_note_endpoint_logs_memory_metadata(self):
        graph_client = AsyncMock()
        graph_client.create_onenote_page.return_value = {
            "id": "page-1",
            "title": "RamAir Weekly",
            "webUrl": "https://onenote.example/page-1",
            "section_id": "section-1",
            "owner_mailbox": "nathan@parlayvu.ai",
        }

        with patch("app.main.MicrosoftGraphClient", return_value=graph_client):
            with patch("app.main.record_generated_output", return_value="output-1") as generated_output:
                with patch("app.main.record_agent_event", return_value="event-1") as event:
                    client = TestClient(app)
                    response = client.post(
                        "/m365/onenote/meeting-notes",
                        json={
                            "title": "RamAir Weekly",
                            "summary": "Nathan captured the client-approved next steps.",
                            "client_id": "ramair",
                            "project_id": "ramair-straight-from-the-hart",
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page"]["id"], "page-1")
        self.assertEqual(response.json()["memory_output_id"], "output-1")
        graph_client.create_onenote_page.assert_awaited_once()
        self.assertEqual(generated_output.call_args.kwargs["output_type"], "onenote_meeting_note")
        self.assertEqual(generated_output.call_args.kwargs["status"], "published")
        self.assertEqual(event.call_args.kwargs["event_type"], "onenote_meeting_note_published")

    def test_files_meeting_note_endpoint_uploads_markdown_and_docx(self):
        graph_client = AsyncMock()
        graph_client.settings = Microsoft365Settings(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            graph_scope="scope",
            webhook_client_state="state",
            allow_send=False,
            agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
        )
        graph_client.download_teams_channel_file.return_value = self._minimal_docx(
            "<w:p><w:r><w:t>MEETING NOTES</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{MEETING_TITLE}}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{SUMMARY}}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{CLIENT}}</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>{{CLIENT_NAME}}</w:t></w:r></w:p>",
            extra_files={
                "word/header1.xml": (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    "<w:p><w:r><w:t>{{CLIENT}}</w:t></w:r></w:p>"
                    "<w:p><w:r><w:t>{{CLIENT_NAME}}</w:t></w:r></w:p>"
                    "</w:hdr>"
                )
            },
        )
        graph_client.upload_teams_channel_file.side_effect = [
            {"id": "md-1", "name": "ramair-weekly.md", "webUrl": "https://sharepoint.example/ramair-weekly.md"},
            {"id": "docx-1", "name": "ramair-weekly.docx", "webUrl": "https://sharepoint.example/ramair-weekly.docx"},
        ]

        project_context = {"client": {"id": "ramair", "name": "RamAir International"}}
        with patch("app.services.meeting_notes_service.MicrosoftGraphClient", return_value=graph_client), \
             patch("app.services.meeting_notes_service._ARTIFACTS_ROOT", _NO_LOCAL_ARTIFACTS_DIR), \
             patch("app.main.get_project_context", return_value=project_context), \
             patch("app.services.meeting_notes_service.record_generated_output", return_value="output-1") as generated_output, \
             patch("app.services.meeting_notes_service.record_agent_event", return_value="event-1") as event:
            client = TestClient(app)
            response = client.post(
                "/m365/files/meeting-notes",
                json={
                    "title": "RamAir Weekly",
                    "summary": "Nathan captured the client-approved next steps.",
                    "client_id": "ramair",
                    "client_name": "RamAir",
                    "project_id": "ramair-straight-from-the-hart",
                    "team_id": "team-1",
                    "channel_id": "channel-1",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["files"]["markdown"]["id"], "md-1")
        self.assertEqual(response.json()["files"]["docx"]["id"], "docx-1")
        self.assertEqual(response.json()["docx_template"]["status"], "template")
        graph_client.download_teams_channel_file.assert_awaited_once()
        self.assertEqual(graph_client.upload_teams_channel_file.await_count, 2)
        uploaded_docx = graph_client.upload_teams_channel_file.await_args_list[1].kwargs["content"]
        with zipfile.ZipFile(BytesIO(uploaded_docx)) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
            header = archive.read("word/header1.xml").decode("utf-8")
        self.assertIn("MEETING NOTES", document)
        self.assertIn("RamAir", document)
        self.assertIn("RamAir International", document)
        self.assertIn("RamAir", header)
        self.assertIn("RamAir International", header)
        self.assertIn("Nathan captured the client-approved next steps.", document)
        self.assertNotIn("Source of truth:", document)
        self.assertNotIn("{{CLIENT}}", document)
        self.assertNotIn("{{CLIENT_NAME}}", document)
        self.assertNotIn("{{CLIENT}}", header)
        self.assertNotIn("{{CLIENT_NAME}}", header)
        self.assertEqual(generated_output.call_args.kwargs["output_type"], "teams_files_meeting_notes")
        self.assertEqual(generated_output.call_args.kwargs["status"], "published")
        self.assertEqual(event.call_args.kwargs["event_type"], "teams_files_meeting_notes_published")

    def test_files_meeting_note_endpoint_falls_back_when_template_missing(self):
        graph_client = AsyncMock()
        graph_client.settings = Microsoft365Settings(
            tenant_id="tenant",
            client_id="client",
            client_secret="secret",
            graph_scope="scope",
            webhook_client_state="state",
            allow_send=False,
            agent_mailboxes={"nathan": "nathan@parlayvu.ai"},
        )
        graph_client.download_teams_channel_file.side_effect = RuntimeError("template missing")
        graph_client.upload_teams_channel_file.side_effect = [
            {"id": "md-1", "name": "ramair-weekly.md", "webUrl": "https://sharepoint.example/ramair-weekly.md"},
            {"id": "docx-1", "name": "ramair-weekly.docx", "webUrl": "https://sharepoint.example/ramair-weekly.docx"},
        ]

        with patch("app.services.meeting_notes_service.MicrosoftGraphClient", return_value=graph_client), \
             patch("app.services.meeting_notes_service._ARTIFACTS_ROOT", _NO_LOCAL_ARTIFACTS_DIR), \
             patch("app.services.meeting_notes_service.record_generated_output", return_value="output-1"), \
             patch("app.services.meeting_notes_service.record_agent_event", return_value="event-1"):
            client = TestClient(app)
            response = client.post(
                "/m365/files/meeting-notes",
                json={
                    "title": "RamAir Weekly",
                    "summary": "Nathan captured the client-approved next steps.",
                    "client_id": "ramair",
                    "project_id": "ramair-straight-from-the-hart",
                    "team_id": "team-1",
                    "channel_id": "channel-1",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["docx_template"]["status"], "fallback")
        self.assertIn("template missing", response.json()["docx_template"]["fallback_reason"])
        uploaded_docx = graph_client.upload_teams_channel_file.await_args_list[1].kwargs["content"]
        with zipfile.ZipFile(BytesIO(uploaded_docx)) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("Meeting Summary", document)


if __name__ == "__main__":
    unittest.main()
