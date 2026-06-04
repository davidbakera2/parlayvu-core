# parlayvu-core/app/main.py
import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Any, Optional
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

# Mount static files from video_system/docs so the generated dashboards and workflow viewers
# are available at https://.../static/Parlays_Dashboard.html etc.
# This is required for MS Teams tabs (which need https web content, not local file paths).
# Anchor to the repo root (not the process CWD) and don't crash startup if the dir
# is absent — check_dir=False makes a missing directory a 404, not a boot failure.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "video_system" / "docs"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR), check_dir=False), name="static")

# ========================= MODELS =========================
class NathanRequest(BaseModel):
    message: str
    client_id: Optional[str] = "default-client"
    project_id: Optional[str] = None
    brand_voice_summary: Optional[str] = None
    conversation_id: Optional[str] = None   # NEW: enables conversation memory across calls


class DylanGenerateSiteRequest(BaseModel):
    content: str
    client_id: Optional[str] = "default-client"
    project_id: Optional[str] = None
    site_name: Optional[str] = "marketing-landing"
    brand_voice: Optional[str] = "Professional, modern, and conversion-focused"
    deploy: bool = False
    project_name: Optional[str] = None
    approval_id: Optional[str] = None


class IngestClientFilesRequest(BaseModel):
    force: bool = False


class DylanGenerateVariationsRequest(BaseModel):
    client_id: str
    variation_count: int = 5
    deploy: bool = True


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
    build_site_edit_approval_card,
    build_site_variations_approval_card,
    graph_files_target_from_teams_activity,
    grounded_project_reply,
    is_bot_framework_activity,
    is_channel_bind_request,
    is_conversation_reset_request,
    is_meeting_note_publish_request,
    nathan_response_to_text,
    normalize_teams_message,
    parse_meeting_note_publish_command,
    resolve_demo_bind_target,
    send_bot_framework_card,
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
    load_conversation_history,
    record_agent_event,
    record_generated_output,
    reset_conversation_history,
    save_conversation_turn,
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
from langchain_core.messages import HumanMessage, AIMessage


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
    """
    Thin wrapper around app.services.meeting_notes_service. Translates the
    HTTP request into kwargs and translates ValueError into 400 so the
    HTTP contract is unchanged. The real work lives in the service so
    Nathan's save_meeting_notes tool can reuse the same code path.
    """
    from app.services.meeting_notes_service import publish_meeting_notes_to_teams

    client_display = _meeting_note_client_display_name(request)
    client_full_name = _meeting_note_client_full_name(request, fallback=client_display)

    try:
        return await publish_meeting_notes_to_teams(
            title=request.title,
            summary=request.summary,
            client_id=request.client_id or "ramair",
            project_id=request.project_id,
            project_name=request.project_name,
            client_name=client_full_name,
            source_conversation_id=request.source_conversation_id,
            team_id=request.team_id,
            channel_id=request.channel_id,
            folder_path=request.folder_path,
            channel=channel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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

    # === NEW: Load conversation history if conversation_id is provided ===
    history_messages: list = []
    if request.conversation_id:
        # Support reset commands on the API path (same as Teams)
        if is_conversation_reset_request(request.message):
            deleted = reset_conversation_history(
                conversation_id=request.conversation_id,
                client_id=request.client_id,
            )
            ack = (
                f"Started fresh — cleared {deleted} prior turn(s) from this conversation."
                if deleted
                else "Started fresh. (No prior history to clear.)"
            )
            return _endpoint_response("Nathan", final_output={"message": ack}, client_id=request.client_id)

        history = load_conversation_history(
            conversation_id=request.conversation_id,
            client_id=request.client_id,
        )
        for turn in history:
            if turn["role"] == "user":
                history_messages.append(HumanMessage(content=turn["content"]))
            else:
                history_messages.append(AIMessage(content=turn["content"]))

    # Build final messages list: history + current user message
    messages = history_messages + [HumanMessage(content=request.message)]

    initial_state = ParlayVuState(
        messages=messages,
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

    # === NEW: Persist turns if conversation_id is present ===
    if request.conversation_id:
        try:
            save_conversation_turn(
                conversation_id=request.conversation_id,
                client_id=request.client_id,
                role="user",
                content=request.message,
            )
            # Best-effort extraction of assistant text for saving
            assistant_text = None
            if isinstance(result, dict):
                fo = result.get("final_output")
                if isinstance(fo, dict):
                    assistant_text = fo.get("message") or fo.get("content")
            if assistant_text:
                save_conversation_turn(
                    conversation_id=request.conversation_id,
                    client_id=request.client_id,
                    role="assistant",
                    content=assistant_text,
                )
        except Exception as exc:
            logger.warning("Failed to persist conversation turns for /nathan: %s", exc)

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


@app.get("/parlays/dashboard", response_class=HTMLResponse)
async def parlays_dashboard():
    """Live project/parlays dashboard (HTML).

    This now serves the rich generated dashboard (same as the static file)
    but dynamically, so it's always up-to-date when the API is running.
    Perfect for embedding as an MS Teams tab (use the https URL via ngrok in dev,
    or the deployed Container App URL in prod).

    The static version (for double-click/offline) is still at
    video_system/docs/Parlays_Dashboard.html — regenerate with the script if needed.
    """
    try:
        # Import the generator logic
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[1]  # app/ -> root
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from tools.generate_parlays_dashboard import (
            scan_clients,
            scan_video_parlays,
            collect_pending_approvals,
            build_dashboard_html,
        )

        clients = scan_clients()
        parlays = scan_video_parlays()
        try:
            pending = collect_pending_approvals()
        except Exception:
            pending = []

        # Enrich like the generator does (simplified here for live serving)
        # For full fidelity, the generator's main() does the status enrichment.
        # We call build with web_mode=True so links point to /static/...
        html = build_dashboard_html(clients, parlays, pending, web_mode=True)
        return html

    except Exception as exc:
        logger.exception("Failed to build rich parlays dashboard")
        # Fallback to a simple message
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>ParlayVU • Parlays Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-slate-50 p-8">
<h1 class="text-3xl font-semibold">ParlayVU Parlays Dashboard</h1>
<p class="text-red-600">Error building dashboard: {exc}</p>
<p>Try the static file: <a href="/static/Parlays_Dashboard.html">/static/Parlays_Dashboard.html</a></p>
<p>Or run <code>python tools/generate_parlays_dashboard.py</code> and open the HTML directly.</p>
</body></html>"""


@app.post("/clients/{client_id}/ingest-files")
async def ingest_client_files_endpoint(client_id: str, body: IngestClientFilesRequest):
    """Pre-ingest a client's Teams channel files (PDF, .docx) into structured
    markdown summaries Nathan reads via get_project_context — no Graph round-
    trip mid-call. Body: {"force": bool}. Force re-ingests even if the local
    .md is newer than the source's last-modified timestamp."""
    from .client_config import ClientConfigError
    from .services.client_file_ingester import ingest_client_files

    try:
        result = await ingest_client_files(client_id, force=body.force)
    except ClientConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("ingest_client_files failed for %s", client_id)
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@app.post("/dylan/generate-variations")
async def dylan_generate_variations_endpoint(body: DylanGenerateVariationsRequest):
    """Generate N distinct homepage variations for a client using the client's
    reference sites + brand notes + design notes, optionally deploying all
    variations under one Cloudflare Pages preview project (<client>-previews).

    Body:
        client_id: ParlayVU client_id (must be onboarded).
        variation_count: clamped to [1, 10]; default 5.
        deploy: if true, deploys to <client>-previews.pages.dev after writing
            local files. Default true.

    Returns the service result (status, variations list, preview_url, audit IDs).
    Preview deploys do NOT go through the approval gate — they land on a
    <client>-previews subdomain, not the client's live site. The existing
    /dylan/deploy-site approval flow still gates production deploys.
    """
    from .client_config import ClientConfigError
    from .services.dylan_variations_service import generate_homepage_variations

    if not body.client_id or not body.client_id.strip():
        raise HTTPException(status_code=400, detail="client_id is required")

    try:
        result = await generate_homepage_variations(
            client_id=body.client_id.strip(),
            variation_count=body.variation_count,
            deploy=body.deploy,
        )
    except ClientConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("generate_homepage_variations failed for %s", body.client_id)
        raise HTTPException(status_code=500, detail=str(exc))
    return result


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


def _sync_parlay_decision(approval: Optional[dict], *, status: str, notes: Optional[str]) -> None:
    """If a decided approval is a Podcast Parlay review gate, advance the parlay
    state machine to match the client's decision.

    This is the loop hook: without it, approving a video draft in Teams would
    leave the episode stuck at the review stage forever. Identified by the
    approval's metadata (action_type starting with 'video_' + a 'stage'). Strictly
    best-effort — never let a state hiccup break the approval decision itself.
    """
    if not approval:
        return
    try:
        meta = approval.get("metadata") or {}
        stage = meta.get("stage")
        action_type = meta.get("action_type") or ""
        project_id = approval.get("project_id")
        if not project_id or not stage or not action_type.startswith("video_"):
            return
        from app import parlay_state as ps
        ps.record_decision(project_id, stage=stage, decision=status, notes=notes, by="client")
    except Exception:
        logger.warning("Parlay state sync skipped for approval %s", approval.get("id"), exc_info=True)


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
        _sync_parlay_decision(approval, status=request.status, notes=request.decision_notes)
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
        _sync_parlay_decision(approval, status=request.status, notes=request.decision_notes)
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
    """Handle a Teams chat message via Nathan's unified tool-loop brain.

    Pre-Track-4 this dispatched through the LangGraph router which gave
    Nathan routing decisions but no direct tool access. Now Teams uses the
    same Anthropic tool-loop that powers Tavus — Nathan can call
    get_project_context, read_client_file, web_search, save_meeting_notes,
    etc. directly from chat. Same brain, different surface: `surface=
    "teams_chat"` enables markdown and drops the voice-narration guidance.

    Returns: `{status, channel, conversation_id, team_id, channel_id,
              client_id, project_id, nathan_text}`. Callers (the Bot
    Framework handler, the direct-API caller) read `nathan_text` to feed
    into the outbound reply.
    """
    from .nathan_llm import run_nathan_conversation

    normalized_text = normalize_teams_message(request.text)
    if not normalized_text:
        raise HTTPException(status_code=400, detail="Teams message text is required")

    _apply_teams_channel_binding(request)

    # Explicit "start over" / "reset" / "new conversation" wipes Nathan's
    # memory for this Teams thread before he even sees the message. Returns
    # immediately with a short ack so the user knows it took effect.
    if is_conversation_reset_request(normalized_text):
        deleted = reset_conversation_history(
            conversation_id=request.conversation_id,
            client_id=request.client_id,
        )
        ack = (
            f"Started fresh — cleared {deleted} prior turn(s) from this thread."
            if deleted
            else "Started fresh. (No prior history to clear.)"
        )
        return {
            "status": "routed",
            "channel": "teams",
            "conversation_id": request.conversation_id,
            "team_id": request.team_id,
            "channel_id": request.channel_id,
            "client_id": request.client_id,
            "project_id": request.project_id,
            "nathan_text": ack,
        }

    # Replay the recent conversation history (last 20 turns, 72h window,
    # 60K char cap — see project_memory.CONVERSATION_MAX_*). Empty list
    # when memory is disabled or this is the first turn. We append the new
    # user message after the history so Nathan reads it in chronological
    # order.
    history = load_conversation_history(
        conversation_id=request.conversation_id,
        client_id=request.client_id,
    )

    nathan_messages = history + [{"role": "user", "content": normalized_text}]

    try:
        nathan_text = await run_nathan_conversation(
            nathan_messages,
            client_id=request.client_id,
            surface="teams_chat",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /teams/messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Persist BOTH sides of the turn so the next message in this thread can
    # replay the full exchange. Saves are best-effort and never raise.
    save_conversation_turn(
        conversation_id=request.conversation_id,
        client_id=request.client_id,
        role="user",
        content=normalized_text,
    )
    if nathan_text:
        save_conversation_turn(
            conversation_id=request.conversation_id,
            client_id=request.client_id,
            role="assistant",
            content=nathan_text,
        )

    # Keep audit parity with the previous LangGraph path — every Teams
    # turn produces one `nathan_replied` event tied to the conversation.
    try:
        record_agent_event(
            agent_name="nathan",
            client_id=request.client_id,
            project_id=request.project_id,
            channel="teams",
            event_type="nathan_replied",
            summary=normalized_text[:200],
            payload={
                "from_user": request.from_user,
                "conversation_id": request.conversation_id,
                "team_id": request.team_id,
                "channel_id": request.channel_id,
                "response_chars": len(nathan_text or ""),
            },
        )
    except Exception as exc:
        logger.warning("Audit record for Teams reply failed: %s", exc)

    return {
        "status": "routed",
        "channel": "teams",
        "conversation_id": request.conversation_id,
        "team_id": request.team_id,
        "channel_id": request.channel_id,
        "client_id": request.client_id,
        "project_id": request.project_id,
        "nathan_text": nathan_text,
    }


def _apply_teams_channel_binding(request: TeamsMessageRequest) -> None:
    if request.team_id and request.channel_id:
        binding = get_teams_channel_binding(team_id=request.team_id, channel_id=request.channel_id)
        if binding:
            request.client_id = binding["client_id"]
            request.project_id = binding["project_id"]


def _is_authorized_dm_sender(client_id: str | None, from_user: str | None) -> bool:
    """Check if a 1:1 DM sender is on the client's authorized_contacts list.

    Fail-closed semantics:
      - No client_id resolved → unauthorized (no client → no allowlist).
      - Client config can't be loaded → unauthorized.
      - authorized_contacts is empty → unauthorized for ALL DMs (clients
        opt in to DM access by populating the list).
      - from_user not in the list → unauthorized.

    Channel posts skip this check entirely — anyone in the bound channel
    is implicitly authorized.
    """
    from .client_config import ClientConfigError, load_client_config

    if not client_id or not from_user:
        return False
    try:
        config = load_client_config(client_id)
    except ClientConfigError:
        return False
    allowlist = [c.strip().lower() for c in config.preferences.authorized_contacts if c.strip()]
    if not allowlist:
        return False
    return from_user.strip().lower() in allowlist


async def _save_teams_attachments(
    client_id: str,
    attachments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Download each Teams attachment and save under
    client_artifacts/<client_id>/01_Source_Material/uploads/<safe-name>.

    Returns a list of saved-file metadata dicts the caller can include in
    Nathan's user message so he knows what landed and where.
    """
    import re
    from pathlib import Path

    from .teams import download_bot_framework_attachment

    if not client_id or not attachments:
        return []

    uploads_root = Path("client_artifacts") / client_id / "01_Source_Material" / "uploads"
    uploads_root.mkdir(parents=True, exist_ok=True)

    saved: list[dict[str, Any]] = []
    for att in attachments:
        try:
            data = await download_bot_framework_attachment(att["content_url"])
        except Exception as exc:
            logger.warning("Failed to download Teams attachment %r: %s", att.get("name"), exc)
            saved.append({**att, "saved_path": None, "error": str(exc)})
            continue
        raw_name = att.get("name") or "attachment"
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", raw_name).strip("-") or "attachment"
        target = uploads_root / safe
        # Avoid overwriting an existing file with a different version by
        # adding a numeric suffix when collisions happen.
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            for i in range(1, 100):
                candidate = uploads_root / f"{stem}-{i}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
        target.write_bytes(data)
        rel_path = str(target).replace("\\", "/")
        saved.append({**att, "saved_path": rel_path, "bytes": len(data)})
        try:
            record_agent_event(
                agent_name="nathan",
                client_id=client_id,
                channel="teams",
                event_type="teams_attachment_uploaded",
                summary=f"Saved attachment {raw_name!r}",
                payload={
                    "saved_path": rel_path,
                    "content_type": att.get("content_type"),
                    "size": len(data),
                    "is_teams_file": att.get("is_teams_file"),
                },
            )
        except Exception as exc:
            logger.warning("Audit for attachment save failed: %s", exc)
    return saved


async def _pending_site_approval_ids(client_id: Optional[str]) -> set[str]:
    """Snapshot of pending deploy_site approvals for a client's website project.
    Used by the Teams handler to compute the delta after Nathan runs (new
    approvals → cards to post)."""
    if not client_id:
        return set()
    project_id = f"{client_id}-website"
    approvals = list_approvals(project_id=project_id, status="pending")
    return {
        a["id"]
        for a in approvals
        if (a.get("metadata") or {}).get("action_type") == "deploy_site"
    }


async def _post_new_site_approval_cards(
    payload: dict[str, Any],
    client_id: Optional[str],
    before_ids: set[str],
) -> list[str]:
    """List pending deploy_site approvals NOT in `before_ids` and post a card
    for each. Returns the approval IDs that were posted (for caller logs/audit).
    Failures to post are logged but don't raise — the text reply already went out.
    """
    if not client_id:
        return []
    project_id = f"{client_id}-website"
    try:
        from .client_config import load_client_config
        config = load_client_config(client_id)
    except Exception:
        logger.exception("client config lookup failed in approval-card poster")
        return []

    approvals = list_approvals(project_id=project_id, status="pending")
    new_approvals = [
        a for a in approvals
        if a["id"] not in before_ids
        and (a.get("metadata") or {}).get("action_type") == "deploy_site"
    ]
    posted: list[str] = []
    for approval in new_approvals:
        meta = approval.get("metadata") or {}
        kind = meta.get("kind")
        try:
            if kind == "site_variations":
                card = build_site_variations_approval_card(
                    approval_id=approval["id"],
                    client_display_name=config.display_name,
                    target_domain=meta.get("target_domain") or config.cloudflare_config.production_domain,
                    variations=meta.get("variations") or [],
                    preview_index_url=meta.get("preview_url"),
                )
            elif kind == "site_edit":
                card = build_site_edit_approval_card(
                    approval_id=approval["id"],
                    client_display_name=config.display_name,
                    target_domain=meta.get("target_domain") or config.cloudflare_config.production_domain,
                    change_description=meta.get("change_description") or "(no description)",
                    preview_url=meta.get("preview_url"),
                )
            else:
                # Unknown deploy_site sub-kind — skip rather than post a broken card.
                continue
            await send_bot_framework_card(payload, card)
            posted.append(approval["id"])
        except Exception:
            logger.exception("Failed to post site approval card | approval_id=%s", approval["id"])
    return posted


async def _handle_site_approval_card_action(
    payload: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any]:
    """Handle an Adaptive-Card button tap on a site approval card.

    For approve actions: marks the approval approved, promotes the chosen
    artifact to production via client_deploy.promote_to_production, and posts
    a confirmation reply into the same Teams conversation.

    For reject actions: marks the approval rejected and posts a 'no changes
    made' reply.

    Returns a small status dict (also handy for tests).
    """
    from .client_config import load_client_config
    from .services.client_deploy import client_sites_root, promote_to_production

    kind = value.get("kind")
    approval_id = value.get("approval_id")
    if not approval_id:
        logger.warning("card action missing approval_id | kind=%s", kind)
        return {"status": "error", "detail": "missing approval_id"}

    # Resolve the approver from the activity 'from' if available.
    from_user = (payload.get("from") or {})
    approver = (
        from_user.get("aadObjectId")
        or from_user.get("id")
        or from_user.get("name")
        or "teams_user"
    )

    # Look up the approval first so we know which client + which artifact to promote.
    approvals = list_approvals(status=None)  # full list; tiny scale today
    approval = next((a for a in approvals if a["id"] == approval_id), None)
    if approval is None:
        await send_bot_framework_reply(payload, f"That approval ({approval_id[:8]}…) is no longer in the system.")
        return {"status": "not_found"}

    metadata = approval.get("metadata") or {}
    if approval.get("status") != "pending":
        await send_bot_framework_reply(
            payload,
            f"That approval was already {approval['status']} — no further action taken.",
        )
        return {"status": "already_decided", "approval_status": approval["status"]}

    project_id = approval.get("project_id") or ""
    # Derive client_id from project_id convention "<client_id>-website".
    if not project_id.endswith("-website"):
        await send_bot_framework_reply(payload, "I can't promote that approval — its project doesn't follow the website convention.")
        return {"status": "unsupported_project"}
    client_id = project_id[: -len("-website")]

    # Rejection paths.
    if kind in ("reject_site_variants", "reject_site_edit"):
        decide_approval(
            approval_id=approval_id,
            status="rejected",
            approver=str(approver),
            decision_notes="Rejected via Teams approval card.",
        )
        await send_bot_framework_reply(
            payload,
            "Got it — no changes published. The preview drafts remain available for review.",
        )
        return {"status": "rejected", "approval_id": approval_id}

    # Approve paths: resolve the source_dir to promote.
    try:
        config = load_client_config(client_id)
    except Exception as exc:
        await send_bot_framework_reply(payload, f"Couldn't load config for {client_id}: {exc}")
        return {"status": "config_error", "detail": str(exc)}

    sub_kind = metadata.get("kind")
    sites_root = client_sites_root(client_id)
    if kind == "approve_site_variant" and sub_kind == "site_variations":
        selected_variant = value.get("selected_variant")
        if selected_variant is None:
            await send_bot_framework_reply(payload, "That card tap was missing a variant number; please try again.")
            return {"status": "missing_variant"}
        source_dir = sites_root / f"variation-{int(selected_variant)}"
        decision_notes = f"Approved variant {selected_variant} via Teams."
    elif kind == "approve_site_edit" and sub_kind == "site_edit":
        edit_slug = metadata.get("edit_slug")
        if not edit_slug:
            await send_bot_framework_reply(payload, "That edit approval is missing its edit slug; can't promote.")
            return {"status": "missing_edit_slug"}
        # The container disk may have been wiped between the edit being
        # generated and this approval click; if so, recover the edit HTML
        # from the preview deploy before promoting.
        from .services.dylan_edit_service import ensure_edit_dir_on_disk
        try:
            source_dir = await ensure_edit_dir_on_disk(
                client_id=client_id,
                edit_slug=edit_slug,
                preview_url=metadata.get("preview_url"),
            )
        except FileNotFoundError as exc:
            await send_bot_framework_reply(
                payload,
                f"Couldn't promote that edit: {exc}",
            )
            return {"status": "edit_recovery_failed", "detail": str(exc)}
        decision_notes = f"Approved edit {edit_slug} via Teams."
    else:
        await send_bot_framework_reply(payload, "I don't know how to apply that approval kind.")
        return {"status": "kind_mismatch"}

    # Decide first so the audit trail records who approved; then promote.
    decide_approval(
        approval_id=approval_id,
        status="approved",
        approver=str(approver),
        decision_notes=decision_notes,
    )
    try:
        deploy = promote_to_production(client_id=client_id, source_dir=source_dir)
    except Exception as exc:
        logger.exception("promote_to_production failed | client=%s source=%s", client_id, source_dir)
        await send_bot_framework_reply(
            payload,
            f"Approval was recorded but the deploy step failed: {exc}. "
            f"You may need to re-run the production deploy manually.",
        )
        return {"status": "promote_failed", "detail": str(exc)}

    domain = config.cloudflare_config.production_domain
    live_url = f"https://{domain}/" if domain else deploy.get("url")
    reply_lines = [
        "Approved and published — your site is now live.",
        f"Live: {live_url}",
    ]
    if deploy.get("status") == "manual_step_required":
        reply_lines = [
            "Approval recorded. The deploy needs a manual step:",
            deploy.get("message") or "Check wrangler output in logs.",
        ]
    await send_bot_framework_reply(payload, "\n".join(reply_lines))

    # Site shipped — close out Nathan's conversation memory for this Teams
    # thread. The next message in this channel starts a fresh ask, not a
    # continuation of "which variant do we pick?". Best-effort; never raises.
    if deploy.get("status") != "manual_step_required":
        conv_id = (payload.get("conversation") or {}).get("id")
        if conv_id:
            cleared = reset_conversation_history(
                conversation_id=conv_id,
                client_id=client_id,
            )
            if cleared:
                logger.info(
                    "Cleared conversation memory after successful promote | "
                    "conversation_id=%s client_id=%s turns=%s",
                    conv_id, client_id, cleared,
                )

    return {"status": "approved_and_deployed", "approval_id": approval_id, "deploy": deploy}


@app.post("/teams/messages")
async def teams_message_endpoint(request: Request):
    payload = await request.json()
    if is_bot_framework_activity(payload):
        if payload.get("type") != "message":
            return {"status": "ignored", "activity_type": payload.get("type")}

        # Adaptive-Card Action.Submit shows up as a message activity with empty
        # `text` and a populated `value` containing our `kind` discriminator.
        # Route it BEFORE the Nathan/binding/normal-message path.
        submit_value = payload.get("value") if isinstance(payload.get("value"), dict) else None
        if submit_value and submit_value.get("kind") in {
            "approve_site_variant",
            "reject_site_variants",
            "approve_site_edit",
            "reject_site_edit",
        }:
            return await _handle_site_approval_card_action(payload, submit_value)

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

        # 1:1 DM authorization gate. Channel posts skip — anyone in the
        # bound channel is implicitly authorized. DMs require the sender to
        # be on the client's authorized_contacts allowlist (fail-closed:
        # empty allowlist = no DM access).
        from .teams import is_one_to_one_dm, extract_teams_attachments

        if is_one_to_one_dm(payload):
            if not _is_authorized_dm_sender(teams_request.client_id, teams_request.from_user):
                reply_text = (
                    "I can only help you if you're on the authorized contacts "
                    "list for one of our clients. Please reach out to your "
                    "ParlayVU contact to get added."
                )
                try:
                    await send_bot_framework_reply(payload, reply_text)
                except Exception as e:
                    logger.error(f"Error sending Bot Framework rejection: {e}")
                return {
                    "status": "unauthorized_dm",
                    "channel": "teams",
                    "conversation_id": teams_request.conversation_id,
                }

        # Attachment handling. Bot Framework activities may carry uploaded
        # files; download them to the client's uploads folder and tell
        # Nathan their paths so he can read them via read_client_file.
        attachments = extract_teams_attachments(payload)
        saved_attachments: list[dict[str, Any]] = []
        if attachments and teams_request.client_id:
            saved_attachments = await _save_teams_attachments(
                teams_request.client_id, attachments
            )
            if saved_attachments:
                successes = [a for a in saved_attachments if a.get("saved_path")]
                if successes:
                    lines = ["", "[Attachments saved to client_artifacts uploads/:"]
                    for a in successes:
                        size = a.get("bytes") or 0
                        lines.append(
                            f" - {a['saved_path']} ({size} bytes, {a.get('content_type') or 'unknown type'})"
                        )
                    lines.append("]")
                    teams_request.text = (teams_request.text or "") + "\n" + "\n".join(lines)

        # Snapshot pending site-approvals BEFORE Nathan runs. Anything new
        # afterwards is something Dylan created during this turn and needs a
        # picker card posted into the channel.
        before_ids = await _pending_site_approval_ids(teams_request.client_id)

        response = await _handle_teams_message(teams_request)
        reply_text = response["nathan_text"]
        try:
            await send_bot_framework_reply(payload, reply_text)
        except Exception as e:
            logger.error(f"Error sending Bot Framework reply: {e}")
            raise HTTPException(status_code=502, detail=str(e))

        # Post any new deploy_site approval cards into this channel.
        posted_cards = await _post_new_site_approval_cards(
            payload, teams_request.client_id, before_ids
        )

        return {
            "status": "replied",
            "channel": "teams",
            "conversation_id": teams_request.conversation_id,
            "attachments_saved": [a.get("saved_path") for a in saved_attachments if a.get("saved_path")],
            "approval_cards_posted": posted_cards,
        }

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
    run_nathan_conversation_streaming,
)


class ChatCompletionRequest(BaseModel):
    model: str = "nathan-opus"
    messages: list[dict] = Field(default_factory=list)
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@app.get("/v1/models")
@app.get("/models")
async def openai_list_models():
    """
    OpenAI-compatible models list. Registered at both /v1/models and /models
    because different custom-LLM clients vary in whether they treat the
    configured base_url as already including /v1.
    """
    return build_models_response()


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
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

    # Per-client binding: each Tavus persona is configured to send
    # X-Parlayvu-Client-Id on its custom-LLM calls. Falls back to
    # NATHAN_DEFAULT_CLIENT_ID (default "ramair") so the existing single
    # persona keeps working through any deploy window where personas haven't
    # been updated yet.
    client_id = (
        request.headers.get("X-Parlayvu-Client-Id", "").strip()
        or os.getenv("NATHAN_DEFAULT_CLIENT_ID", "ramair").strip()
        or None
    )
    if client_id:
        logger.info("Nathan conversation bound to client_id=%s", client_id)

    if body.stream:
        # Streaming: emit text chunks AS Claude produces them. Critically,
        # this means narration text Claude produces alongside a tool call
        # gets streamed to Tavus BEFORE the tool runs - so Tavus speaks
        # "give me a moment while I file these" while we're uploading to
        # Graph in the background, instead of silence.
        from fastapi.responses import StreamingResponse
        import json as _json

        async def stream_response():
            request_id = f"{uuid4().hex[:12]}"
            created = int(__import__("time").time())

            def chunk_event(text: str) -> str:
                chunk = {
                    "id": f"chatcmpl-{request_id}",
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": body.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant", "content": text},
                        "finish_reason": None,
                    }],
                }
                return f"data: {_json.dumps(chunk)}\n\n"

            any_chunk = False
            try:
                async for text in run_nathan_conversation_streaming(
                    body.messages, client_id=client_id
                ):
                    if not text:
                        continue
                    any_chunk = True
                    # Trailing space so spoken output flows between fragments
                    yield chunk_event(text if any_chunk else text)
                    # (No space prefix - Tavus joins chunks verbatim. The
                    # natural sentence breaks in Claude's output handle pacing.)
            except Exception:
                logger.exception("Nathan LLM stream error")
                if not any_chunk:
                    yield chunk_event("I'm having trouble right now. Give me a moment.")

            if not any_chunk:
                yield chunk_event("I'm thinking about that — give me just a moment.")

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
        text = await run_nathan_conversation(body.messages, client_id=client_id)
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