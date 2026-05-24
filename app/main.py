# parlayvu-core/app/main.py
import logging
import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("parlayvu")

from .settings import build_agent_model_map, get_settings

settings = get_settings()

# ========================= APP =========================
app = FastAPI(title="ParlayVu.ai Core", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================= MODELS =========================
class NathanRequest(BaseModel):
    message: str
    client_id: Optional[str] = "default-client"
    project_id: Optional[str] = None
    brand_voice_summary: Optional[str] = None


class DylanGenerateSiteRequest(BaseModel):
    content: str
    client_id: Optional[str] = "default-client"
    project_id: Optional[str] = None
    site_name: Optional[str] = "marketing-landing"
    brand_voice: Optional[str] = "Professional, modern, and conversion-focused"
    deploy: bool = False
    project_name: Optional[str] = None
    approval_id: Optional[str] = None


class DylanDeploySiteRequest(BaseModel):
    site_path: str
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    approval_id: Optional[str] = None


class EmailDraftRequest(BaseModel):
    agent_name: str
    to_recipients: list[str]
    subject: str
    body: str
    client_id: Optional[str] = None
    project_id: Optional[str] = None
    request_approval: bool = True


class OneNoteMeetingNoteRequest(BaseModel):
    title: str
    summary: str
    client_id: Optional[str] = "ramair"
    client_name: Optional[str] = None
    project_id: Optional[str] = "ramair-straight-from-the-hart"
    project_name: Optional[str] = None
    source_conversation_id: Optional[str] = None
    team_id: Optional[str] = None
    channel_id: Optional[str] = None


class FilesMeetingNoteRequest(BaseModel):
    title: str
    summary: str
    client_id: Optional[str] = "ramair"
    client_name: Optional[str] = None
    project_id: Optional[str] = "ramair-straight-from-the-hart"
    project_name: Optional[str] = None
    source_conversation_id: Optional[str] = None
    team_id: Optional[str] = None
    channel_id: Optional[str] = None
    folder_path: Optional[str] = None


class TeamsMessageRequest(BaseModel):
    text: str
    from_user: Optional[str] = None
    conversation_id: Optional[str] = None
    team_id: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    client_id: Optional[str] = "default-client"
    project_id: Optional[str] = None


class ApprovalRequest(BaseModel):
    client_id: str
    project_id: str
    requested_by_agent: str
    action_type: str
    title: str
    summary: Optional[str] = None
    generated_output_id: Optional[str] = None
    project_name: Optional[str] = None
    metadata: Optional[dict] = None


class ApprovalDecisionRequest(BaseModel):
    status: str
    approver: str
    decision_notes: Optional[str] = None


class TeamsApprovalDecisionRequest(BaseModel):
    status: str
    approver: str
    decision_notes: Optional[str] = None
    conversation_id: Optional[str] = None
    team_id: Optional[str] = None
    channel_id: Optional[str] = None


class MeetingStrategyRequest(BaseModel):
    transcript: str
    meeting_title: Optional[str] = "Meeting"
    client_id: Optional[str] = "default-client"
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    team_id: Optional[str] = None
    channel_id: Optional[str] = None
    folder_path: Optional[str] = None


# ========================= IMPORTS =========================
from .approvals import decide_approval, list_approvals, request_approval, require_approved_approval
from .agents.registry import initialize_registry
from .agents.tools.dylan_tools import deploy_to_cloudflare, generate_astro_site
from .graph import get_graph, ParlayVuState
from .readiness import readiness_report
from .teams import (
    approvals_to_teams_cards,
    graph_files_target_from_teams_activity,
    grounded_project_reply,
    is_bot_framework_activity,
    is_channel_bind_request,
    is_meeting_note_publish_request,
    nathan_response_to_text,
    normalize_teams_message,
    parse_meeting_note_publish_command,
    resolve_demo_bind_target,
    send_bot_framework_reply,
    teams_message_from_activity,
    teams_status,
)
from .project_memory import (
    bind_teams_channel,
    get_teams_channel_binding,
    get_project_context,
    list_clients,
    list_projects,
    record_agent_event,
    record_generated_output,
)
from .microsoft365 import (
    MicrosoftGraphClient,
    build_meeting_notes_docx,
    build_meeting_notes_markdown,
    build_meeting_notes_template_placeholders,
    build_onenote_meeting_page_html,
    mailbox_status,
    render_meeting_notes_template_docx,
    sanitize_file_stem,
)
from langchain_core.messages import HumanMessage


def _endpoint_response(agent: str, route_decision=None, final_output=None, client_id: Optional[str] = None, **extra):
    response = {
        "agent": agent,
        "route_decision": jsonable_encoder(route_decision),
        "final_output": jsonable_encoder(final_output),
        "client_id": client_id,
    }
    response.update(extra)
    return response


def _deploy_site(site_path: str, project_name: Optional[str] = None):
    return deploy_to_cloudflare.invoke(
        {
            "site_path": site_path,
            "project_name": project_name,
        }
    )


def _memory_error(exc: Exception) -> HTTPException:
    message = str(exc)
    status_code = 503 if "DATABASE_URL" in message else 500
    return HTTPException(status_code=status_code, detail=message)


def _template_fallback_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 404:
            return "Template file was not found at the configured SharePoint path"
        return f"SharePoint template download failed with HTTP {status_code}"
    return str(exc)


def _meeting_note_client_display_name(request: OneNoteMeetingNoteRequest | FilesMeetingNoteRequest) -> Optional[str]:
    if request.client_name and request.client_name.strip():
        return request.client_name.strip()

    return request.client_id


def _meeting_note_client_full_name(
    request: OneNoteMeetingNoteRequest | FilesMeetingNoteRequest,
    *,
    fallback: Optional[str] = None,
) -> Optional[str]:
    if request.project_id:
        try:
            project_context = get_project_context(request.project_id)
        except Exception as exc:
            logger.warning("Project context lookup skipped for meeting note client full name: %s", exc)
        else:
            client = (project_context or {}).get("client") or {}
            if client.get("name"):
                return client["name"]

    if request.client_id:
        try:
            for client in list_clients():
                if client.get("id") == request.client_id and client.get("name"):
                    return client["name"]
        except Exception as exc:
            logger.warning("Client lookup skipped for meeting note client full name: %s", exc)
        return fallback or request.client_id

    return fallback


def _teams_request_client_name(request: TeamsMessageRequest) -> Optional[str]:
    if not request.client_id or not request.channel_name:
        return None
    normalized_client_id = request.client_id.replace("-", "").replace("_", "").lower()
    normalized_channel_name = request.channel_name.replace(" ", "").replace("-", "").replace("_", "").lower()
    if normalized_client_id and normalized_client_id in normalized_channel_name:
        return request.channel_name
    return None


async def _publish_onenote_meeting_note(
    request: OneNoteMeetingNoteRequest,
    *,
    channel: str = "api",
):
    title = request.title.strip()
    summary = request.summary.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Meeting note title is required")
    if not summary:
        raise HTTPException(status_code=400, detail="Meeting note summary is required")

    html = build_onenote_meeting_page_html(
        title=title,
        summary=summary,
        client_id=request.client_id,
        project_id=request.project_id,
    )
    page = await MicrosoftGraphClient().create_onenote_page(title=title, html=html)
    memory_output_id = record_generated_output(
        client_id=request.client_id or "ramair",
        project_id=request.project_id,
        project_name=request.project_name,
        agent_name="nathan",
        output_type="onenote_meeting_note",
        title=title,
        content=summary,
        uri=page.get("webUrl"),
        status="published",
        metadata={
            "page": page,
            "source_of_truth": "ParlayVU project memory",
            "source_conversation_id": request.source_conversation_id,
            "team_id": request.team_id,
            "channel_id": request.channel_id,
        },
    )
    event_id = record_agent_event(
        client_id=request.client_id,
        project_id=request.project_id,
        project_name=request.project_name,
        agent_name="nathan",
        event_type="onenote_meeting_note_published",
        channel=channel,
        summary=f"Published OneNote meeting note: {title}",
        payload={
            "page": page,
            "memory_output_id": memory_output_id,
            "source_conversation_id": request.source_conversation_id,
            "team_id": request.team_id,
            "channel_id": request.channel_id,
        },
    )
    return {
        "status": "published",
        "page": page,
        "memory_output_id": memory_output_id,
        "event_id": event_id,
    }


async def _publish_files_meeting_note(
    request: FilesMeetingNoteRequest,
    *,
    channel: str = "api",
):
    title = request.title.strip()
    summary = request.summary.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Meeting note title is required")
    if not summary:
        raise HTTPException(status_code=400, detail="Meeting note summary is required")

    markdown = build_meeting_notes_markdown(
        title=title,
        summary=summary,
        client_id=request.client_id,
        project_id=request.project_id,
    )
    stem = sanitize_file_stem(title)
    graph_client = MicrosoftGraphClient()
    template_path = graph_client.settings.files_meeting_notes_template_path
    expected_template_location = f"Teams channel Files root/{template_path.strip('/')}"
    docx_template = {
        "status": "template",
        "path": template_path,
        "expected_location": expected_template_location,
        "fallback_reason": None,
    }
    try:
        template_docx = await graph_client.download_teams_channel_file(
            file_path=template_path,
            team_id=request.team_id,
            channel_id=request.channel_id,
        )
        client_display = _meeting_note_client_display_name(request)
        docx = render_meeting_notes_template_docx(
            template_docx,
            build_meeting_notes_template_placeholders(
                title=title,
                summary=summary,
                client_id=request.client_id,
                client_name=client_display,
                client_full_name=_meeting_note_client_full_name(request, fallback=client_display),
                project_id=request.project_id,
            ),
        )
    except Exception as exc:
        fallback_reason = _template_fallback_reason(exc)
        logger.warning(
            "Using generated meeting notes DOCX fallback; template_path=%s expected_location=%s reason=%s",
            template_path,
            expected_template_location,
            fallback_reason,
        )
        docx = build_meeting_notes_docx(
            title=title,
            summary=summary,
            client_id=request.client_id,
            project_id=request.project_id,
        )
        docx_template = {
            "status": "fallback",
            "path": template_path,
            "expected_location": expected_template_location,
            "fallback_reason": fallback_reason,
        }
    markdown_file = await graph_client.upload_teams_channel_file(
        filename=f"{stem}.md",
        content=markdown.encode("utf-8"),
        content_type="text/markdown; charset=utf-8",
        team_id=request.team_id,
        channel_id=request.channel_id,
        folder_path=request.folder_path,
    )
    docx_file = await graph_client.upload_teams_channel_file(
        filename=f"{stem}.docx",
        content=docx,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        team_id=request.team_id,
        channel_id=request.channel_id,
        folder_path=request.folder_path,
    )
    files = {"markdown": markdown_file, "docx": docx_file}
    memory_output_id = record_generated_output(
        client_id=request.client_id or "ramair",
        project_id=request.project_id,
        project_name=request.project_name,
        agent_name="nathan",
        output_type="teams_files_meeting_notes",
        title=title,
        content=markdown,
        uri=docx_file.get("webUrl") or markdown_file.get("webUrl"),
        status="published",
        metadata={
            "files": files,
            "source_of_truth": "ParlayVU project memory",
            "source_conversation_id": request.source_conversation_id,
            "team_id": request.team_id,
            "channel_id": request.channel_id,
            "folder_path": request.folder_path,
            "docx_template": docx_template,
        },
    )
    event_id = record_agent_event(
        client_id=request.client_id,
        project_id=request.project_id,
        project_name=request.project_name,
        agent_name="nathan",
        event_type="teams_files_meeting_notes_published",
        channel=channel,
        summary=f"Published Teams Files meeting notes: {title}",
        payload={
            "files": files,
            "memory_output_id": memory_output_id,
            "source_conversation_id": request.source_conversation_id,
            "team_id": request.team_id,
            "channel_id": request.channel_id,
            "folder_path": request.folder_path,
            "docx_template": docx_template,
        },
    )
    return {
        "status": "published",
        "files": files,
        "docx_template": docx_template,
        "memory_output_id": memory_output_id,
        "event_id": event_id,
    }


async def _run_nathan_request(
    request: NathanRequest,
    *,
    channel: str = "api",
    event_payload: Optional[dict] = None,
):
    project_context = None
    if request.project_id:
        try:
            project_context = get_project_context(request.project_id)
        except Exception as e:
            raise _memory_error(e)
        if project_context is None:
            raise HTTPException(status_code=404, detail=f"Project not found: {request.project_id}")

    initial_state = ParlayVuState(
        messages=[HumanMessage(content=request.message)],
        client_id=request.client_id,
        project_id=request.project_id,
        project_context=project_context,
        brand_voice_summary=request.brand_voice_summary,
    )

    graph = get_graph()
    result = await graph.ainvoke(initial_state)
    route_decision = result.get("route_decision") if isinstance(result, dict) else result.route_decision
    final_output = result.get("final_output") if isinstance(result, dict) else result.final_output
    record_agent_event(
        client_id=request.client_id,
        project_id=request.project_id,
        project_name=project_context.get("name") if project_context else None,
        agent_name="nathan",
        event_type="route_decision",
        channel=channel,
        summary=getattr(route_decision, "reason", None) if route_decision else None,
        payload={
            "message": request.message,
            "target_agent": getattr(getattr(route_decision, "target_agent", None), "value", None),
            "project_id": request.project_id,
            **(event_payload or {}),
        },
    )

    return _endpoint_response(
        "Nathan",
        route_decision,
        final_output,
        request.client_id,
        project_id=request.project_id,
        project_context=project_context,
    )

# ========================= STARTUP =========================
@app.on_event("startup")
async def startup_event():
    try:
        model_map = build_agent_model_map(settings)
        initialize_registry(model_map)
        get_graph()

        logger.info(
            "ParlayVu.ai started | xai_key=%s anthropic_key=%s",
            bool(settings.xai_api_key),
            bool(settings.anthropic_api_key),
        )
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


# ========================= ROUTES =========================
@app.get("/health")
async def health():
    readiness = readiness_report(settings)
    return {
        "status": "healthy",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.active_model,
        "readiness_status": readiness["status"],
    }


@app.get("/readiness")
async def readiness_endpoint():
    return readiness_report(settings)


@app.get("/memory/clients")
async def memory_clients_endpoint():
    try:
        return {"clients": list_clients()}
    except Exception as e:
        logger.error(f"Error in /memory/clients: {e}")
        raise _memory_error(e)


@app.get("/memory/projects")
async def memory_projects_endpoint(client_id: Optional[str] = None):
    try:
        return {"projects": list_projects(client_id=client_id)}
    except Exception as e:
        logger.error(f"Error in /memory/projects: {e}")
        raise _memory_error(e)


@app.get("/memory/projects/{project_id}")
async def memory_project_context_endpoint(project_id: str):
    try:
        project = get_project_context(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        return {"project": project}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /memory/projects/{project_id}: {e}")
        raise _memory_error(e)


@app.get("/approvals")
async def approvals_list_endpoint(project_id: Optional[str] = None, status: Optional[str] = None):
    try:
        return {"approvals": list_approvals(project_id=project_id, status=status)}
    except Exception as e:
        logger.error(f"Error in /approvals: {e}")
        raise _memory_error(e)


@app.post("/approvals")
async def approvals_request_endpoint(request: ApprovalRequest):
    try:
        approval = request_approval(
            client_id=request.client_id,
            project_id=request.project_id,
            project_name=request.project_name,
            requested_by_agent=request.requested_by_agent,
            action_type=request.action_type,
            title=request.title,
            summary=request.summary,
            generated_output_id=request.generated_output_id,
            metadata=request.metadata,
        )
        return {"approval": approval}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in POST /approvals: {e}")
        raise _memory_error(e)


@app.post("/approvals/{approval_id}/decision")
async def approvals_decision_endpoint(approval_id: str, request: ApprovalDecisionRequest):
    try:
        approval = decide_approval(
            approval_id=approval_id,
            status=request.status,
            approver=request.approver,
            decision_notes=request.decision_notes,
        )
        if approval is None:
            raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id}")
        return {"approval": approval}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in /approvals/{approval_id}/decision: {e}")
        raise _memory_error(e)


@app.get("/m365/status")
async def m365_status_endpoint():
    return mailbox_status()


@app.post("/m365/email-drafts")
async def m365_email_draft_endpoint(request: EmailDraftRequest):
    try:
        draft = await MicrosoftGraphClient().create_email_draft(
            agent_name=request.agent_name,
            to_recipients=request.to_recipients,
            subject=request.subject,
            body=request.body,
        )
        record_agent_event(
            client_id=request.client_id,
            project_id=request.project_id,
            agent_name=request.agent_name,
            event_type="email_draft_created",
            channel="m365",
            summary=f"Created email draft: {request.subject}",
            payload={
                "to_recipients": request.to_recipients,
                "subject": request.subject,
                "draft_id": draft.get("id"),
            },
        )
        approval = None
        if request.request_approval and request.client_id and request.project_id:
            approval = request_approval(
                client_id=request.client_id,
                project_id=request.project_id,
                requested_by_agent=request.agent_name,
                action_type="send_email",
                title=f"Review email draft: {request.subject}",
                summary="An agent created an email draft that needs approval before sending.",
                metadata={
                    "draft_id": draft.get("id"),
                    "to_recipients": request.to_recipients,
                    "subject": request.subject,
                },
            )
        return {"status": "draft_created", "draft": draft, "approval": approval}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error in /m365/email-drafts: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/m365/onenote/meeting-notes")
async def m365_onenote_meeting_note_endpoint(request: OneNoteMeetingNoteRequest):
    try:
        return await _publish_onenote_meeting_note(request, channel="api")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /m365/onenote/meeting-notes: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/m365/files/meeting-notes")
async def m365_files_meeting_note_endpoint(request: FilesMeetingNoteRequest):
    try:
        return await _publish_files_meeting_note(request, channel="api")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /m365/files/meeting-notes: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/teams/status")
async def teams_status_endpoint():
    return teams_status()


@app.get("/teams/approval-cards")
async def teams_approval_cards_endpoint(project_id: Optional[str] = None, status: Optional[str] = "pending"):
    try:
        approvals = list_approvals(project_id=project_id, status=status)
        return {"cards": approvals_to_teams_cards(approvals)}
    except Exception as e:
        logger.error(f"Error in /teams/approval-cards: {e}")
        raise _memory_error(e)


@app.post("/teams/approvals/{approval_id}/decision")
async def teams_approval_decision_endpoint(approval_id: str, request: TeamsApprovalDecisionRequest):
    try:
        approval = decide_approval(
            approval_id=approval_id,
            status=request.status,
            approver=request.approver,
            decision_notes=request.decision_notes,
        )
        if approval is None:
            raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id}")
        record_agent_event(
            client_id=None,
            project_id=approval.get("project_id"),
            agent_name=approval.get("requested_by_agent") or "nathan",
            event_type="teams_approval_decision",
            channel="teams",
            summary=f"{request.status}: {approval_id}",
            payload={
                "approval_id": approval_id,
                "approver": request.approver,
                "status": request.status,
                "conversation_id": request.conversation_id,
                "team_id": request.team_id,
                "channel_id": request.channel_id,
            },
        )
        return {"status": "decision_recorded", "card": approvals_to_teams_cards([approval])[0], "approval": approval}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in /teams/approvals/{approval_id}/decision: {e}")
        raise _memory_error(e)


async def _handle_teams_message(request: TeamsMessageRequest):
    normalized_text = normalize_teams_message(request.text)
    if not normalized_text:
        raise HTTPException(status_code=400, detail="Teams message text is required")

    _apply_teams_channel_binding(request)

    try:
        nathan_response = await _run_nathan_request(
            NathanRequest(
                message=normalized_text,
                client_id=request.client_id,
                project_id=request.project_id,
            ),
            channel="teams",
            event_payload={
                "from_user": request.from_user,
                "conversation_id": request.conversation_id,
                "team_id": request.team_id,
                "channel_id": request.channel_id,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /teams/messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "routed",
        "channel": "teams",
        "conversation_id": request.conversation_id,
        "team_id": request.team_id,
        "channel_id": request.channel_id,
        "nathan": nathan_response,
    }


def _apply_teams_channel_binding(request: TeamsMessageRequest) -> None:
    if request.team_id and request.channel_id:
        binding = get_teams_channel_binding(team_id=request.team_id, channel_id=request.channel_id)
        if binding:
            request.client_id = binding["client_id"]
            request.project_id = binding["project_id"]


@app.post("/teams/messages")
async def teams_message_endpoint(request: Request):
    payload = await request.json()
    if is_bot_framework_activity(payload):
        if payload.get("type") != "message":
            return {"status": "ignored", "activity_type": payload.get("type")}

        teams_request = TeamsMessageRequest(**teams_message_from_activity(payload))
        _apply_teams_channel_binding(teams_request)
        if is_channel_bind_request(teams_request.text):
            target = resolve_demo_bind_target(teams_request.text)
            if not target:
                reply_text = "I can bind this channel once you name a known client/project. For the demo, try: bind this channel to RamAir."
            elif not teams_request.team_id or not teams_request.channel_id:
                reply_text = "I can only bind a Teams channel from a team channel conversation, not a personal chat."
            else:
                binding = bind_teams_channel(
                    team_id=teams_request.team_id,
                    channel_id=teams_request.channel_id,
                    channel_name=teams_request.channel_name,
                    client_id=target["client_id"],
                    project_id=target["project_id"],
                    project_name=target["project_name"],
                    bound_by=teams_request.from_user,
                )
                reply_text = (
                    f"This channel is now bound to {target['project_name']} "
                    f"({binding['project_id']}). I will use that project memory for future messages here."
                )
            try:
                await send_bot_framework_reply(payload, reply_text)
            except Exception as e:
                logger.error(f"Error sending Bot Framework reply: {e}")
                raise HTTPException(status_code=502, detail=str(e))
            return {"status": "bound", "channel": "teams", "conversation_id": teams_request.conversation_id}

        if is_meeting_note_publish_request(teams_request.text):
            command = parse_meeting_note_publish_command(teams_request.text)
            try:
                if command.get("target") == "onenote":
                    result = await _publish_onenote_meeting_note(
                        OneNoteMeetingNoteRequest(
                            title=command["title"],
                            summary=command["summary"],
                            client_id=teams_request.client_id,
                            client_name=_teams_request_client_name(teams_request),
                            project_id=teams_request.project_id,
                            source_conversation_id=teams_request.conversation_id,
                            team_id=teams_request.team_id,
                            channel_id=teams_request.channel_id,
                        ),
                        channel="teams",
                    )
                    reply_text = f"Created OneNote meeting note: {result['page'].get('title')}"
                    if result["page"].get("webUrl"):
                        reply_text += f"\n{result['page']['webUrl']}"
                    response_payload = {
                        "status": "published_onenote",
                        "channel": "teams",
                        "conversation_id": teams_request.conversation_id,
                        "page": result["page"],
                        "memory_output_id": result["memory_output_id"],
                    }
                else:
                    files_target = graph_files_target_from_teams_activity(
                        teams_request.team_id,
                        teams_request.channel_id,
                    )
                    result = await _publish_files_meeting_note(
                        FilesMeetingNoteRequest(
                            title=command["title"],
                            summary=command["summary"],
                            client_id=teams_request.client_id,
                            client_name=_teams_request_client_name(teams_request),
                            project_id=teams_request.project_id,
                            source_conversation_id=teams_request.conversation_id,
                            team_id=files_target["team_id"],
                            channel_id=files_target["channel_id"],
                        ),
                        channel="teams",
                    )
                    docx_url = (result["files"].get("docx") or {}).get("webUrl")
                    reply_text = f"Published Teams Files meeting notes: {command['title']}"
                    if docx_url:
                        reply_text += f"\n{docx_url}"
                    if result.get("docx_template", {}).get("status") == "fallback":
                        fallback_reason = result["docx_template"].get("fallback_reason")
                        template_path = result["docx_template"].get("path")
                        reply_text += "\nUsed generated DOCX fallback because the RamAir template could not be applied."
                        if fallback_reason:
                            reply_text += f"\nReason: {fallback_reason}."
                        if template_path:
                            reply_text += f"\nExpected template path: {template_path}"
                    response_payload = {
                        "status": "published_files",
                        "channel": "teams",
                        "conversation_id": teams_request.conversation_id,
                        "files": result["files"],
                        "docx_template": result.get("docx_template"),
                        "memory_output_id": result["memory_output_id"],
                    }
            except Exception as e:
                logger.error(f"Error publishing meeting note from Teams: {e}")
                if command.get("target") == "onenote":
                    reply_text = (
                        "I recognized the OneNote meeting note command, but the publish step failed before a page was "
                        "created. Please check the Microsoft 365 OneNote configuration and app logs."
                    )
                else:
                    reply_text = (
                        "I recognized the meeting note publish command, but the publish step failed before files were "
                        "created. Please check the Microsoft 365 Teams/SharePoint Files configuration and app logs."
                    )
                try:
                    await send_bot_framework_reply(payload, reply_text)
                except Exception as reply_error:
                    logger.error(f"Error sending Bot Framework reply: {reply_error}")
                    raise HTTPException(status_code=502, detail=str(reply_error))
                return {"status": "publish_failed", "channel": "teams", "conversation_id": teams_request.conversation_id}
            try:
                await send_bot_framework_reply(payload, reply_text)
            except Exception as e:
                logger.error(f"Error sending Bot Framework reply: {e}")
                raise HTTPException(status_code=502, detail=str(e))
            return response_payload

        response = await _handle_teams_message(teams_request)
        project_context = response["nathan"].get("project_context")
        if project_context and teams_request.project_id:
            approvals = list_approvals(project_id=teams_request.project_id, status="pending")
            reply_text = grounded_project_reply(project_context, approvals)
        else:
            reply_text = nathan_response_to_text(response["nathan"])
        try:
            await send_bot_framework_reply(payload, reply_text)
        except Exception as e:
            logger.error(f"Error sending Bot Framework reply: {e}")
            raise HTTPException(status_code=502, detail=str(e))
        return {"status": "replied", "channel": "teams", "conversation_id": teams_request.conversation_id}

    teams_request = TeamsMessageRequest(**payload)
    _apply_teams_channel_binding(teams_request)
    if is_meeting_note_publish_request(teams_request.text):
        command = parse_meeting_note_publish_command(teams_request.text)
        if command.get("target") == "onenote":
            return await _publish_onenote_meeting_note(
                OneNoteMeetingNoteRequest(
                    title=command["title"],
                    summary=command["summary"],
                    client_id=teams_request.client_id,
                    client_name=_teams_request_client_name(teams_request),
                    project_id=teams_request.project_id,
                    source_conversation_id=teams_request.conversation_id,
                    team_id=teams_request.team_id,
                    channel_id=teams_request.channel_id,
                ),
                channel="teams",
            )
        return await _publish_files_meeting_note(
            FilesMeetingNoteRequest(
                title=command["title"],
                summary=command["summary"],
                client_id=teams_request.client_id,
                client_name=_teams_request_client_name(teams_request),
                project_id=teams_request.project_id,
                source_conversation_id=teams_request.conversation_id,
                team_id=teams_request.team_id,
                channel_id=teams_request.channel_id,
            ),
            channel="teams",
        )

    return await _handle_teams_message(teams_request)

@app.post("/nathan")
async def nathan_endpoint(request: NathanRequest):
    try:
        return await _run_nathan_request(request, channel="api")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /nathan: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dylan/generate-site")
async def dylan_generate_site_endpoint(request: DylanGenerateSiteRequest):
    try:
        tool_output = generate_astro_site.invoke(
            {
                "content": request.content,
                "site_name": request.site_name,
                "client_id": request.client_id,
                "brand_voice": request.brand_voice,
            }
        )
        deploy_output = None
        if request.deploy:
            if not request.approval_id:
                approval = request_approval(
                    client_id=request.client_id or "default-client",
                    project_id=request.project_id or f"{request.client_id or 'default-client'}-default",
                    project_name=request.project_name or request.site_name,
                    requested_by_agent="dylan",
                    action_type="deploy_site",
                    title=f"Deploy {request.site_name or 'generated site'}",
                    summary="Dylan generated a site and needs approval before deployment.",
                    metadata={"site_path": tool_output.get("site_path")},
                )
                final_output = {
                    "agent": "dylan",
                    "content": "Dylan generated the site. Deployment is waiting for approval.",
                    "tool_output": tool_output,
                    "approval_required": True,
                    "approval": approval,
                }
                return _endpoint_response("Dylan", final_output=final_output, client_id=request.client_id)
            require_approved_approval(
                approval_id=request.approval_id,
                project_id=request.project_id,
                action_type="deploy_site",
            )
            deploy_output = _deploy_site(tool_output["site_path"], request.project_name)

        memory_output_id = record_generated_output(
            client_id=request.client_id or "default-client",
            project_id=request.project_id,
            project_name=request.project_name or request.site_name,
            brand_voice_summary=request.brand_voice,
            agent_name="dylan",
            output_type="astro_site",
            title=request.site_name or "marketing-landing",
            content=tool_output.get("message"),
            uri=tool_output.get("site_path"),
            status="generated",
            metadata={"tool_output": tool_output},
        )
        record_agent_event(
            client_id=request.client_id,
            project_id=request.project_id,
            project_name=request.project_name or request.site_name,
            agent_name="dylan",
            event_type="site_generated",
            channel="api",
            summary=tool_output.get("message"),
            payload={"site_path": tool_output.get("site_path"), "memory_output_id": memory_output_id},
        )

        final_output = {
            "agent": "dylan",
            "content": tool_output.get("message"),
            "tool_output": tool_output,
        }
        if memory_output_id:
            final_output["memory_output_id"] = memory_output_id
        if deploy_output:
            final_output["deployment_output"] = deploy_output
            final_output["content"] = deploy_output.get("message") or final_output["content"]
            record_agent_event(
                client_id=request.client_id,
                project_id=request.project_id,
                project_name=request.project_name or request.site_name,
                agent_name="dylan",
                event_type="site_deployed",
                channel="api",
                summary=deploy_output.get("message"),
                payload=deploy_output,
            )

        return _endpoint_response("Dylan", final_output=final_output, client_id=request.client_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in /dylan/generate-site: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dylan/deploy-site")
async def dylan_deploy_site_endpoint(request: DylanDeploySiteRequest):
    try:
        if not request.approval_id:
            approval = request_approval(
                client_id=request.client_id or "default-client",
                project_id=request.project_id or f"{request.client_id or 'default-client'}-default",
                project_name=request.project_name,
                requested_by_agent="dylan",
                action_type="deploy_site",
                title=f"Deploy site at {request.site_path}",
                summary="Dylan needs approval before deploying this site.",
                metadata={"site_path": request.site_path},
            )
            final_output = {
                "agent": "dylan",
                "content": "Deployment is waiting for approval.",
                "approval_required": True,
                "approval": approval,
            }
            return _endpoint_response("Dylan", final_output=final_output, client_id=request.client_id)

        require_approved_approval(
            approval_id=request.approval_id,
            project_id=request.project_id,
            action_type="deploy_site",
        )
        tool_output = _deploy_site(request.site_path, request.project_name)
        final_output = {
            "agent": "dylan",
            "content": tool_output.get("message"),
            "tool_output": tool_output,
        }
        record_agent_event(
            client_id=request.client_id,
            project_id=request.project_id,
            project_name=request.project_name,
            agent_name="dylan",
            event_type="site_deploy_requested",
            channel="api",
            summary=tool_output.get("message"),
            payload={"site_path": request.site_path, "deploy_output": tool_output},
        )
        return _endpoint_response("Dylan", final_output=final_output)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in /dylan/deploy-site: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/meetings/strategy")
async def meetings_strategy_endpoint(request: MeetingStrategyRequest):
    """Process a meeting transcript through Blake + Nathan to produce a strategy .docx."""
    if not request.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is required")

    project_context = None
    if request.project_id:
        try:
            project_context = get_project_context(request.project_id)
        except Exception as exc:
            logger.warning("Could not load project context for strategy: %s", exc)

    from app.agents.workflows.meeting_strategy import run_meeting_strategy
    result = await run_meeting_strategy(
        transcript=request.transcript,
        project_id=request.project_id,
        client_id=request.client_id,
        meeting_title=request.meeting_title or "Meeting",
        project_context=project_context,
    )

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    blake_analysis = result.get("blake_analysis") or {}
    nathan_strategy = result.get("nathan_strategy") or ""

    from app.microsoft365 import build_strategy_docx
    docx_bytes = build_strategy_docx(
        meeting_title=request.meeting_title or "Meeting",
        client_id=request.client_id,
        project_id=request.project_id,
        blake_analysis=blake_analysis,
        nathan_strategy=nathan_strategy,
    )

    teams_file = None
    stem = sanitize_file_stem(f"{request.meeting_title or 'meeting'}-strategy")
    try:
        teams_file = await MicrosoftGraphClient().upload_teams_channel_file(
            filename=f"{stem}.docx",
            content=docx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            team_id=request.team_id,
            channel_id=request.channel_id,
            folder_path=request.folder_path or "03_Deliverables/Strategy Docs",
        )
        logger.info("Strategy doc filed in Teams | url=%s", teams_file.get("webUrl"))
    except Exception as exc:
        logger.warning("Teams upload skipped: %s", exc)

    memory_output_id = record_generated_output(
        client_id=request.client_id or "default-client",
        project_id=request.project_id,
        agent_name="nathan",
        output_type="meeting_strategy",
        title=f"{request.meeting_title} — Strategy",
        content=nathan_strategy,
        uri=teams_file.get("webUrl") if teams_file else None,
        status="published" if teams_file else "generated",
    )
    record_agent_event(
        client_id=request.client_id,
        project_id=request.project_id,
        agent_name="nathan",
        event_type="meeting_strategy_generated",
        channel="api",
        summary=f"Strategy doc generated: {request.meeting_title}",
        payload={
            "session_id": request.session_id,
            "themes_count": len(blake_analysis.get("key_themes", [])),
            "action_items_count": len(blake_analysis.get("action_items", [])),
            "memory_output_id": memory_output_id,
            "teams_file": teams_file,
        },
    )

    return {
        "status": "published" if teams_file else "generated",
        "meeting_title": request.meeting_title,
        "blake_analysis": blake_analysis,
        "nathan_strategy": nathan_strategy,
        "docx": {
            "filed_in_teams": bool(teams_file),
            "url": teams_file.get("webUrl") if teams_file else None,
        },
        "memory_output_id": memory_output_id,
    }


# ── Nathan Custom LLM — OpenAI-Compatible Endpoint ───────────────────────────
#
# Tavus CVI supports pointing a persona at a custom LLM endpoint that follows
# the OpenAI Chat Completions API format. When configured, Tavus calls
# POST /v1/chat/completions with the conversation history instead of using their
# built-in model. Nathan's responses are then powered by Claude Opus 4.7 with
# full tool access: web search, URL fetch, Teams files, and project context.
#
# To configure:
#   1. Set TAVILY_API_KEY in Azure (get free key at https://tavily.com)
#   2. Run scripts/Update-NathanPersonaLLM.ps1 to update the Tavus persona
#   3. The persona will call POST https://<your-api-host>/v1/chat/completions
#
# Authentication: set NATHAN_LLM_API_KEY to require a bearer token.
# Leave it empty to allow unauthenticated access (Tavus can't always send auth).


from .nathan_llm import (
    build_chat_completion_response,
    build_models_response,
    run_nathan_conversation,
)


class ChatCompletionRequest(BaseModel):
    model: str = "nathan-opus"
    messages: list[dict] = Field(default_factory=list)
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@app.get("/v1/models")
async def openai_list_models():
    """
    OpenAI-compatible models list.
    Tavus validates this endpoint before calling /v1/chat/completions.
    """
    return build_models_response()


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request, body: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint powering Nathan in Tavus CVI.

    Tavus calls this endpoint with the live conversation history.
    Claude Opus 4.7 processes the messages, calls tools as needed
    (web search, URL fetch, Teams files, project context), and returns
    Nathan's spoken response.

    Authentication: if NATHAN_LLM_API_KEY is set, Bearer token is required.
    """
    # Optional bearer token auth
    expected_key = os.getenv("NATHAN_LLM_API_KEY", "")
    if expected_key:
        auth_header = request.headers.get("Authorization", "")
        provided_key = auth_header.removeprefix("Bearer ").strip()
        if provided_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key.")

    if not body.messages:
        raise HTTPException(status_code=400, detail="messages array is required.")

    if body.stream:
        # Streaming: run Nathan and stream the response character by character
        from fastapi.responses import StreamingResponse
        import json as _json

        async def stream_response():
            try:
                text = await run_nathan_conversation(body.messages)
            except Exception as exc:
                logger.exception("Nathan LLM stream error")
                text = "I'm having trouble right now. Give me a moment."

            request_id = f"{uuid4().hex[:12]}"
            created = int(__import__("time").time())

            # Stream in chunks
            chunk_size = 20
            for i in range(0, len(text), chunk_size):
                chunk_text = text[i:i + chunk_size]
                chunk = {
                    "id": f"chatcmpl-{request_id}",
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": body.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": chunk_text},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {_json.dumps(chunk)}\n\n"

            # Final chunk with finish_reason
            final_chunk = {
                "id": f"chatcmpl-{request_id}",
                "object": "chat.completion.chunk",
                "created": created,
                "model": body.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {_json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming
    try:
        text = await run_nathan_conversation(body.messages)
    except Exception as exc:
        logger.exception("Nathan LLM error")
        text = "I'm having a bit of trouble right now. Can you repeat the question?"

    return build_chat_completion_response(text, model=body.model, request_id=uuid4().hex[:12])


@app.get("/nathan/llm/status")
async def nathan_llm_status():
    """
    Check Nathan's custom LLM configuration status.
    Shows which tools are configured and ready.
    """
    tavily_configured = bool(os.getenv("TAVILY_API_KEY"))
    anthropic_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
    teams_configured = bool(
        os.getenv("MICROSOFT_TENANT_ID")
        and os.getenv("MICROSOFT_CLIENT_ID")
        and os.getenv("MICROSOFT_CLIENT_SECRET")
    )
    auth_required = bool(os.getenv("NATHAN_LLM_API_KEY"))

    return {
        "status": "ready" if anthropic_configured else "missing_anthropic_key",
        "endpoint": "POST /v1/chat/completions",
        "models_endpoint": "GET /v1/models",
        "auth_required": auth_required,
        "tools": {
            "web_search": {
                "configured": tavily_configured,
                "note": "Requires TAVILY_API_KEY — get free key at https://tavily.com",
            },
            "fetch_url": {
                "configured": True,
                "note": "Uses Jina Reader (r.jina.ai) — no API key required. "
                        "Fetches LinkedIn profiles, websites, social media.",
            },
            "teams_files": {
                "configured": teams_configured,
                "note": "Requires MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET "
                        "and Files.Read.All + Sites.Read.All Graph permissions.",
            },
            "project_context": {
                "configured": True,
                "note": "Uses ParlayVU project memory + client_artifacts/ flat files.",
            },
        },
        "tavus_setup": {
            "persona_endpoint": "PATCH https://tavusapi.com/v2/personas/{personaId}",
            "custom_llm_field": "custom_llm",
            "required_fields": {
                "model_name": "nathan-opus",
                "base_url": "<this-api-host>",
                "api_key": "<NATHAN_LLM_API_KEY or empty>",
            },
            "script": "services/teams-media-bot/scripts/Update-NathanPersonaLLM.ps1",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)