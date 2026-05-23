import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from typing import Any, Optional
from urllib.parse import quote

import httpx

DEFAULT_MEETING_NOTES_TEMPLATE_PATH = "00_Client_Brief/Templates/RamAir Meeting Notes Template.docx"

AGENT_MAILBOX_ENV = {
    "nathan": "NATHAN_MAILBOX",
    "alex": "ALEX_MAILBOX",
    "ava": "AVA_MAILBOX",
    "blake": "BLAKE_MAILBOX",
    "casey": "CASEY_MAILBOX",
    "codey": "CODEY_MAILBOX",
    "dylan": "DYLAN_MAILBOX",
    "jordan": "JORDAN_MAILBOX",
    "michael": "MICHAEL_MAILBOX",
    "morgan": "MORGAN_MAILBOX",
    "nora": "NORA_MAILBOX",
    "riley": "RILEY_MAILBOX",
    "taylor": "TAYLOR_MAILBOX",
}


@dataclass(frozen=True)
class Microsoft365Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    graph_scope: str
    webhook_client_state: str
    allow_send: bool
    agent_mailboxes: dict[str, str]
    onenote_owner_mailbox: str = ""
    onenote_notebook_id: str = ""
    onenote_notebook_name: str = "RamAir"
    onenote_section_id: str = ""
    onenote_section_name: str = "Meeting Notes"
    files_team_id: str = ""
    files_channel_id: str = ""
    files_drive_id: str = ""
    files_folder_item_id: str = ""
    files_base_path: str = "03_Deliverables/Meeting Notes"
    files_meeting_notes_template_path: str = DEFAULT_MEETING_NOTES_TEMPLATE_PATH

    @property
    def configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.client_secret)


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_microsoft365_settings() -> Microsoft365Settings:
    agent_mailboxes = {
        agent: mailbox
        for agent, env_name in AGENT_MAILBOX_ENV.items()
        if (mailbox := os.getenv(env_name, "").strip())
    }
    return Microsoft365Settings(
        tenant_id=os.getenv("MICROSOFT_TENANT_ID", ""),
        client_id=os.getenv("MICROSOFT_CLIENT_ID", ""),
        client_secret=os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        graph_scope=os.getenv("MICROSOFT_GRAPH_SCOPE", "https://graph.microsoft.com/.default"),
        webhook_client_state=os.getenv("MICROSOFT_WEBHOOK_CLIENT_STATE", ""),
        allow_send=_truthy(os.getenv("MICROSOFT_GRAPH_ALLOW_SEND", "false")),
        agent_mailboxes=agent_mailboxes,
        onenote_owner_mailbox=os.getenv("ONENOTE_OWNER_MAILBOX", agent_mailboxes.get("nathan", "")),
        onenote_notebook_id=os.getenv("ONENOTE_NOTEBOOK_ID", ""),
        onenote_notebook_name=os.getenv("ONENOTE_NOTEBOOK_NAME", "RamAir"),
        onenote_section_id=os.getenv("ONENOTE_SECTION_ID", ""),
        onenote_section_name=os.getenv("ONENOTE_SECTION_NAME", "Meeting Notes"),
        files_team_id=os.getenv("M365_FILES_TEAM_ID", os.getenv("RAMAIR_TEAMS_TEAM_ID", "")),
        files_channel_id=os.getenv("M365_FILES_CHANNEL_ID", os.getenv("RAMAIR_TEAMS_CHANNEL_ID", "")),
        files_drive_id=os.getenv("M365_FILES_DRIVE_ID", ""),
        files_folder_item_id=os.getenv("M365_FILES_FOLDER_ITEM_ID", ""),
        files_base_path=os.getenv("M365_FILES_BASE_PATH", "03_Deliverables/Meeting Notes"),
        files_meeting_notes_template_path=os.getenv(
            "M365_FILES_MEETING_NOTES_TEMPLATE_PATH",
            DEFAULT_MEETING_NOTES_TEMPLATE_PATH,
        ),
    )


def mailbox_status(settings: Optional[Microsoft365Settings] = None) -> dict[str, Any]:
    active_settings = settings or get_microsoft365_settings()
    return {
        "configured": active_settings.configured,
        "allow_send": active_settings.allow_send,
        "onenote": {
            "configured": active_settings.configured
            and bool(active_settings.onenote_owner_mailbox)
            and bool(active_settings.onenote_section_id or active_settings.onenote_section_name),
            "owner_mailbox": active_settings.onenote_owner_mailbox or None,
            "notebook_id_configured": bool(active_settings.onenote_notebook_id),
            "notebook_name": active_settings.onenote_notebook_name or None,
            "section_id_configured": bool(active_settings.onenote_section_id),
            "section_name": active_settings.onenote_section_name or None,
        },
        "files": {
            "configured": active_settings.configured
            and (
                bool(active_settings.files_team_id and active_settings.files_channel_id)
                or bool(active_settings.files_drive_id)
            ),
            "team_id_configured": bool(active_settings.files_team_id),
            "channel_id_configured": bool(active_settings.files_channel_id),
            "drive_id_configured": bool(active_settings.files_drive_id),
            "folder_item_id_configured": bool(active_settings.files_folder_item_id),
            "base_path": active_settings.files_base_path or None,
            "meeting_notes_template_path": active_settings.files_meeting_notes_template_path or None,
        },
        "agents": {
            agent: {
                "configured": agent in active_settings.agent_mailboxes,
                "mailbox": active_settings.agent_mailboxes.get(agent),
            }
            for agent in AGENT_MAILBOX_ENV
        },
    }


def sanitize_file_stem(value: str, *, default: str = "meeting-notes") -> str:
    stem = re.sub(r"[^A-Za-z0-9._ -]+", "", value.strip()).strip(" ._-")
    stem = re.sub(r"\s+", "-", stem).lower()
    return stem[:80] or default


def build_meeting_notes_markdown(
    *,
    title: str,
    summary: str,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    source_label: str = "ParlayVU project memory",
) -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        f"# {title.strip() or 'Meeting Notes'}",
        "",
        f"- Source of truth: {source_label}",
        "- Published by: ParlayVU Nathan",
        f"- Published at: {now}",
    ]
    if client_id:
        lines.append(f"- Client: {client_id}")
    if project_id:
        lines.append(f"- Project: {project_id}")
    lines.extend(["", "## Meeting Summary", "", summary.strip() or "No summary provided.", ""])
    return "\n".join(lines)


def build_meeting_notes_docx(
    *,
    title: str,
    summary: str,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    source_label: str = "ParlayVU project memory",
) -> bytes:
    metadata = [
        f"Source of truth: {source_label}",
        "Published by: ParlayVU Nathan",
    ]
    if client_id:
        metadata.append(f"Client: {client_id}")
    if project_id:
        metadata.append(f"Project: {project_id}")

    def paragraph(text: str, style: str | None = None) -> str:
        style_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{style_xml}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>"

    body = [paragraph(title.strip() or "Meeting Notes", "Title")]
    body.extend(paragraph(item) for item in metadata)
    body.append(paragraph("Meeting Summary", "Heading1"))
    body.extend(paragraph(part) for part in (summary.strip() or "No summary provided.").splitlines() if part.strip())

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}<w:sectPr/></w:body>"
        "</w:document>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def build_strategy_docx(
    *,
    meeting_title: str,
    blake_analysis: dict,
    nathan_strategy: str,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bytes:
    """Build a rich strategy .docx from Blake's analysis and Nathan's strategy text."""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn

    doc = Document()
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    # --- Title ---
    doc.add_heading(f"{meeting_title} — Strategy & Next Steps", 0)

    # --- Metadata ---
    meta = doc.add_paragraph()
    meta.add_run(f"Date: {now}\n")
    if client_id:
        meta.add_run(f"Client: {client_id}\n")
    if project_id:
        meta.add_run(f"Project: {project_id}\n")
    meta.add_run("Prepared by: Nathan Ellis, ParlayVU.ai")

    doc.add_paragraph()  # spacer

    # --- Meeting Summary ---
    summary = blake_analysis.get("meeting_summary", "").strip()
    if summary:
        doc.add_heading("Meeting Summary", 1)
        for para in summary.splitlines():
            if para.strip():
                doc.add_paragraph(para.strip())

    # --- Key Themes ---
    themes = blake_analysis.get("key_themes", [])
    if themes:
        doc.add_heading("Key Themes", 1)
        for theme in themes:
            doc.add_paragraph(str(theme).strip(), style="List Bullet")

    # --- Decisions Made ---
    decisions = blake_analysis.get("decisions_made", [])
    if decisions:
        doc.add_heading("Decisions Made", 1)
        for d in decisions:
            doc.add_paragraph(str(d).strip(), style="List Bullet")

    # --- Action Items table ---
    action_items = blake_analysis.get("action_items", [])
    if action_items:
        doc.add_heading("Action Items", 1)
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        hdr_cells = table.rows[0].cells
        for cell, label in zip(hdr_cells, ["Action Item", "Owner", "Priority"]):
            cell.text = label
            run = cell.paragraphs[0].runs[0]
            run.bold = True
        for item in action_items:
            row = table.add_row().cells
            row[0].text = str(item.get("item", ""))
            row[1].text = str(item.get("owner", ""))
            row[2].text = str(item.get("priority", "")).capitalize()

    # --- Open Questions ---
    questions = blake_analysis.get("open_questions", [])
    if questions:
        doc.add_heading("Open Questions", 1)
        for q in questions:
            doc.add_paragraph(str(q).strip(), style="List Bullet")

    # --- Strategic Opportunities ---
    opportunities = blake_analysis.get("strategic_opportunities", [])
    if opportunities:
        doc.add_heading("Strategic Opportunities", 1)
        for o in opportunities:
            doc.add_paragraph(str(o).strip(), style="List Bullet")

    # --- Nathan's Strategy (parse markdown sections) ---
    if nathan_strategy:
        doc.add_heading("Nathan's Strategic Assessment", 1)
        _render_strategy_markdown(doc, nathan_strategy)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _render_strategy_markdown(doc, text: str) -> None:
    """Render Nathan's markdown strategy text into Word paragraphs."""
    pending: list[str] = []

    def flush():
        for line in pending:
            if line.strip():
                doc.add_paragraph(line.strip())
        pending.clear()

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            doc.add_heading(line[3:].strip(), 2)
        elif line.startswith("### "):
            flush()
            doc.add_heading(line[4:].strip(), 3)
        elif line.startswith(("- ", "* ")):
            flush()
            doc.add_paragraph(line[2:].strip(), style="List Bullet")
        elif line and line[0].isdigit() and ". " in line[:5]:
            flush()
            doc.add_paragraph(line.split(". ", 1)[1].strip(), style="List Number")
        else:
            pending.append(line)

    flush()


def _summary_sections(summary: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "summary"
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        heading = re.match(r"^(?:#{1,6}\s*)?([A-Za-z][A-Za-z /_-]{1,40}):?\s*$", line)
        if heading:
            normalized = re.sub(r"[^a-z0-9]+", "_", heading.group(1).strip().lower()).strip("_")
            if normalized in {
                "attendees",
                "summary",
                "meeting_summary",
                "decisions",
                "action_items",
                "actions",
                "questions",
                "open_questions",
                "next_steps",
            }:
                current = normalized
                sections.setdefault(current, [])
                continue
        sections.setdefault(current, []).append(raw_line)

    return {
        key: "\n".join(part for part in parts).strip()
        for key, parts in sections.items()
        if "\n".join(parts).strip()
    }


def build_meeting_notes_template_placeholders(
    *,
    title: str,
    summary: str,
    client_id: Optional[str] = None,
    client_name: Optional[str] = None,
    client_full_name: Optional[str] = None,
    project_id: Optional[str] = None,
    source_label: str = "ParlayVU project memory",
) -> dict[str, str]:
    sections = _summary_sections(summary)
    client = (client_name or client_id or "RamAir").strip() or "RamAir"
    client_full = (client_full_name or client).strip() or client
    project = project_id or client_id or "RamAir"

    def first_section(*keys: str, default: str = "Not specified.") -> str:
        for key in keys:
            if sections.get(key):
                return sections[key]
        return default

    return {
        "{{MEETING_TITLE}}": title.strip() or "Meeting Notes",
        "{{MEETING_DATE}}": datetime.now(timezone.utc).date().isoformat(),
        "{{CLIENT}}": client,
        "{{CLIENT_NAME}}": client_full,
        "{{PROJECT}}": project,
        "{{ATTENDEES}}": first_section("attendees"),
        "{{SUMMARY}}": first_section("meeting_summary", "summary", default=summary.strip() or "No summary provided."),
        "{{DECISIONS}}": first_section("decisions"),
        "{{ACTION_ITEMS}}": first_section("action_items", "actions"),
        "{{QUESTIONS}}": first_section("questions", "open_questions"),
        "{{NEXT_STEPS}}": first_section("next_steps"),
        "{{SOURCE_MATERIAL}}": source_label,
    }


def _replace_docx_placeholder(xml: str, placeholder: str, value: str) -> tuple[str, int]:
    escaped_value = escape(value)
    direct_count = xml.count(placeholder)
    updated = xml.replace(placeholder, escaped_value)

    xml_tag_gap = r"(?:<[^>]+>)*"
    split_pattern = xml_tag_gap.join(re.escape(char) for char in placeholder)
    updated, split_count = re.subn(split_pattern, lambda _match: escaped_value, updated)
    return updated, direct_count + split_count


def render_meeting_notes_template_docx(template_docx: bytes, placeholders: dict[str, str]) -> bytes:
    if not template_docx:
        raise ValueError("Meeting notes template is empty")

    output = BytesIO()
    replacements = 0
    try:
        with zipfile.ZipFile(BytesIO(template_docx), "r") as source:
            names = set(source.namelist())
            if "word/document.xml" not in names:
                raise ValueError("Meeting notes template is missing word/document.xml")

            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    content = source.read(info.filename)
                    if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                        text = content.decode("utf-8")
                        for placeholder, value in placeholders.items():
                            text, count = _replace_docx_placeholder(text, placeholder, value)
                            replacements += count
                        content = text.encode("utf-8")
                    target.writestr(info, content)
    except zipfile.BadZipFile as exc:
        raise ValueError("Meeting notes template is not a valid DOCX zip") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("Meeting notes template contains unsupported XML encoding") from exc

    if replacements == 0:
        raise ValueError("Meeting notes template did not contain recognized placeholders")
    return output.getvalue()


def build_onenote_meeting_page_html(
    *,
    title: str,
    summary: str,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    source_label: str = "ParlayVU project memory",
) -> str:
    safe_title = escape(title.strip() or "Meeting Notes")
    paragraphs = [
        f"<p>{escape(part).replace(chr(10), '<br />')}</p>"
        for part in summary.strip().split("\n\n")
        if part.strip()
    ]
    metadata_items = [
        ("Source of truth", source_label),
        ("Client", client_id),
        ("Project", project_id),
    ]
    metadata = "\n".join(
        f"<li><strong>{escape(label)}:</strong> {escape(value)}</li>"
        for label, value in metadata_items
        if value
    )
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        f"  <title>{safe_title}</title>\n"
        '  <meta name="created-by" content="ParlayVU Nathan" />\n'
        "</head>\n"
        "<body>\n"
        f"  <h1>{safe_title}</h1>\n"
        f"  <ul>{metadata}</ul>\n"
        "  <h2>Meeting Summary</h2>\n"
        f"  {''.join(paragraphs) or '<p>No summary provided.</p>'}\n"
        "</body>\n"
        "</html>"
    )


class MicrosoftGraphClient:
    def __init__(self, settings: Optional[Microsoft365Settings] = None):
        self.settings = settings or get_microsoft365_settings()

    async def get_access_token(self) -> str:
        if not self.settings.configured:
            raise RuntimeError("Microsoft 365 Graph credentials are not configured")

        token_url = f"https://login.microsoftonline.com/{self.settings.tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": self.settings.client_id,
            "client_secret": self.settings.client_secret,
            "scope": self.settings.graph_scope,
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            payload = response.json()
        return payload["access_token"]

    def mailbox_for_agent(self, agent_name: str) -> str:
        mailbox = self.settings.agent_mailboxes.get(agent_name.lower())
        if not mailbox:
            raise ValueError(f"No Microsoft 365 mailbox is configured for agent: {agent_name}")
        return mailbox

    def onenote_owner_mailbox(self) -> str:
        mailbox = self.settings.onenote_owner_mailbox or self.settings.agent_mailboxes.get("nathan")
        if not mailbox:
            raise ValueError("No OneNote owner mailbox is configured")
        return mailbox

    async def _graph_get(self, path: str, token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.json()

    async def resolve_channel_files_folder(
        self,
        *,
        team_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        token: Optional[str] = None,
    ) -> dict[str, Any]:
        resolved_team_id = team_id or self.settings.files_team_id
        resolved_channel_id = channel_id or self.settings.files_channel_id
        if not resolved_team_id or not resolved_channel_id:
            raise ValueError("Teams file publishing requires a team_id and channel_id")

        access_token = token or await self.get_access_token()
        folder = await self._graph_get(
            f"/teams/{quote(resolved_team_id, safe='')}/channels/{quote(resolved_channel_id, safe='')}/filesFolder",
            access_token,
        )
        parent_reference = folder.get("parentReference") or {}
        drive_id = parent_reference.get("driveId")
        if not drive_id:
            raise ValueError("Graph filesFolder response did not include parentReference.driveId")
        return {
            "id": folder.get("id"),
            "name": folder.get("name"),
            "webUrl": folder.get("webUrl"),
            "drive_id": drive_id,
            "team_id": resolved_team_id,
            "channel_id": resolved_channel_id,
        }

    async def upload_drive_file(
        self,
        *,
        drive_id: str,
        filename: str,
        content: bytes,
        folder_path: Optional[str] = None,
        folder_item_id: Optional[str] = None,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        if not drive_id:
            raise ValueError("drive_id is required for SharePoint file upload")
        clean_filename = filename.strip()
        if not clean_filename:
            raise ValueError("filename is required for SharePoint file upload")

        token = await self.get_access_token()
        relative_path = "/".join(part.strip("/") for part in [folder_path or "", clean_filename] if part.strip("/"))
        quoted_path = quote(relative_path, safe="/")
        if folder_item_id:
            path = f"/drives/{quote(drive_id, safe='')}/items/{quote(folder_item_id, safe='')}:/{quoted_path}:/content"
        else:
            path = f"/drives/{quote(drive_id, safe='')}/root:/{quoted_path}:/content"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(
                f"https://graph.microsoft.com/v1.0{path}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": content_type,
                },
                content=content,
            )
            response.raise_for_status()
            item = response.json()
        parent_reference = item.get("parentReference") or {}
        return {
            "id": item.get("id"),
            "name": item.get("name") or clean_filename,
            "webUrl": item.get("webUrl"),
            "size": item.get("size"),
            "drive_id": parent_reference.get("driveId") or drive_id,
            "path": relative_path,
            "content_type": content_type,
        }

    async def download_drive_file(
        self,
        *,
        drive_id: str,
        file_path: str,
        folder_item_id: Optional[str] = None,
    ) -> bytes:
        if not drive_id:
            raise ValueError("drive_id is required for SharePoint file download")
        clean_path = file_path.strip("/")
        if not clean_path:
            raise ValueError("file_path is required for SharePoint file download")

        token = await self.get_access_token()
        quoted_path = quote(clean_path, safe="/")
        if folder_item_id:
            path = f"/drives/{quote(drive_id, safe='')}/items/{quote(folder_item_id, safe='')}:/{quoted_path}:/content"
        else:
            path = f"/drives/{quote(drive_id, safe='')}/root:/{quoted_path}:/content"

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.content

    async def upload_teams_channel_file(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str,
        team_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        folder_path: Optional[str] = None,
    ) -> dict[str, Any]:
        if team_id or channel_id or (self.settings.files_team_id and self.settings.files_channel_id):
            folder = await self.resolve_channel_files_folder(team_id=team_id, channel_id=channel_id)
            upload = await self.upload_drive_file(
                drive_id=folder["drive_id"],
                folder_item_id=folder["id"],
                folder_path=folder_path or self.settings.files_base_path,
                filename=filename,
                content=content,
                content_type=content_type,
            )
            return {**upload, "team_id": folder["team_id"], "channel_id": folder["channel_id"], "files_folder": folder}

        if self.settings.files_drive_id:
            return await self.upload_drive_file(
                drive_id=self.settings.files_drive_id,
                folder_item_id=self.settings.files_folder_item_id or None,
                folder_path=folder_path or self.settings.files_base_path,
                filename=filename,
                content=content,
                content_type=content_type,
            )

        raise ValueError("Teams/SharePoint file publishing is not configured")

    async def download_teams_channel_file(
        self,
        *,
        file_path: str,
        team_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> bytes:
        if team_id or channel_id or (self.settings.files_team_id and self.settings.files_channel_id):
            folder = await self.resolve_channel_files_folder(team_id=team_id, channel_id=channel_id)
            return await self.download_drive_file(
                drive_id=folder["drive_id"],
                folder_item_id=folder["id"],
                file_path=file_path,
            )

        if self.settings.files_drive_id:
            return await self.download_drive_file(
                drive_id=self.settings.files_drive_id,
                folder_item_id=self.settings.files_folder_item_id or None,
                file_path=file_path,
            )

        raise ValueError("Teams/SharePoint file publishing is not configured")

    async def resolve_onenote_section_id(self, *, token: Optional[str] = None) -> str:
        if self.settings.onenote_section_id:
            return self.settings.onenote_section_id

        mailbox = self.onenote_owner_mailbox()
        access_token = token or await self.get_access_token()
        notebook_id = self.settings.onenote_notebook_id

        if not notebook_id:
            notebooks = await self._graph_get(
                f"/users/{mailbox}/onenote/notebooks?$select=id,displayName",
                access_token,
            )
            notebook_name = self.settings.onenote_notebook_name.strip().lower()
            for notebook in notebooks.get("value", []):
                if (notebook.get("displayName") or "").strip().lower() == notebook_name:
                    notebook_id = notebook["id"]
                    break
            if not notebook_id:
                raise ValueError(f"OneNote notebook not found: {self.settings.onenote_notebook_name}")

        sections = await self._graph_get(
            f"/users/{mailbox}/onenote/notebooks/{notebook_id}/sections?$select=id,displayName",
            access_token,
        )
        section_name = self.settings.onenote_section_name.strip().lower()
        for section in sections.get("value", []):
            if (section.get("displayName") or "").strip().lower() == section_name:
                return section["id"]
        raise ValueError(f"OneNote section not found: {self.settings.onenote_section_name}")

    async def create_onenote_page(
        self,
        *,
        title: str,
        html: str,
    ) -> dict[str, Any]:
        mailbox = self.onenote_owner_mailbox()
        token = await self.get_access_token()
        section_id = await self.resolve_onenote_section_id(token=token)

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://graph.microsoft.com/v1.0/users/{mailbox}/onenote/sections/{section_id}/pages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/html",
                },
                content=html.encode("utf-8"),
            )
            response.raise_for_status()
            page = response.json()

        links = page.get("links") or {}
        web_url = (links.get("oneNoteWebUrl") or {}).get("href")
        return {
            "id": page.get("id"),
            "title": page.get("title") or title,
            "createdDateTime": page.get("createdDateTime"),
            "lastModifiedDateTime": page.get("lastModifiedDateTime"),
            "webUrl": web_url,
            "section_id": section_id,
            "owner_mailbox": mailbox,
        }

    async def create_email_draft(
        self,
        *,
        agent_name: str,
        to_recipients: list[str],
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        mailbox = self.mailbox_for_agent(agent_name)
        token = await self.get_access_token()
        message = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [
                {"emailAddress": {"address": recipient}}
                for recipient in to_recipients
            ],
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json=message,
            )
            response.raise_for_status()
            return response.json()

    async def send_email(
        self,
        *,
        agent_name: str,
        to_recipients: list[str],
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        if not self.settings.allow_send:
            raise PermissionError("Outbound Microsoft 365 sends are disabled; create drafts for approval instead")

        mailbox = self.mailbox_for_agent(agent_name)
        token = await self.get_access_token()
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [
                    {"emailAddress": {"address": recipient}}
                    for recipient in to_recipients
                ],
            },
            "saveToSentItems": True,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            response.raise_for_status()
        return {"status": "sent", "agent": agent_name, "mailbox": mailbox}
