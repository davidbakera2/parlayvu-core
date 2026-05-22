from typing import Any, Optional

from app.database import session_scope
from app.models import AgentEvent, Approval, GeneratedOutput
from app.project_memory import _dt, ensure_project_context

PENDING_STATUS = "pending"
DECISION_STATUSES = {"approved", "rejected", "changes_requested", "cancelled"}


def serialize_approval(approval: Approval) -> dict[str, Any]:
    generated_output = approval.generated_output
    return {
        "id": approval.id,
        "project_id": approval.project_id,
        "generated_output_id": approval.generated_output_id,
        "requested_by_agent": approval.requested_by_agent,
        "approver": approval.approver,
        "status": approval.status,
        "decision_notes": approval.decision_notes,
        "metadata": approval.metadata_json or {},
        "generated_output": (
            {
                "id": generated_output.id,
                "agent_name": generated_output.agent_name,
                "output_type": generated_output.output_type,
                "title": generated_output.title,
                "status": generated_output.status,
                "uri": generated_output.uri,
            }
            if generated_output
            else None
        ),
        "created_at": _dt(approval.created_at),
        "updated_at": _dt(approval.updated_at),
    }


def request_approval(
    *,
    client_id: str,
    project_id: str,
    requested_by_agent: str,
    action_type: str,
    title: str,
    summary: Optional[str] = None,
    generated_output_id: Optional[str] = None,
    project_name: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    with session_scope() as session:
        project = ensure_project_context(
            session,
            client_id=client_id,
            project_id=project_id,
            project_name=project_name,
        )
        generated_output = None
        if generated_output_id:
            generated_output = session.get(GeneratedOutput, generated_output_id)
            if generated_output is None:
                raise ValueError(f"Generated output not found: {generated_output_id}")
            if generated_output.project_id != project.id:
                raise ValueError("Generated output does not belong to the requested project")

        approval = Approval(
            project=project,
            generated_output=generated_output,
            requested_by_agent=requested_by_agent,
            status=PENDING_STATUS,
            decision_notes=summary,
            metadata_json={
                "action_type": action_type,
                "title": title,
                **(metadata or {}),
            },
        )
        session.add(approval)
        session.flush()
        session.add(
            AgentEvent(
                project=project,
                client_id=client_id,
                agent_name=requested_by_agent,
                event_type="approval_requested",
                channel="approval",
                summary=title,
                payload={
                    "approval_id": approval.id,
                    "action_type": action_type,
                    "generated_output_id": generated_output_id,
                },
            )
        )
        session.flush()
        return serialize_approval(approval)


def list_approvals(
    *,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    with session_scope() as session:
        query = session.query(Approval)
        if project_id:
            query = query.filter(Approval.project_id == project_id)
        if status:
            query = query.filter(Approval.status == status)
        approvals = query.order_by(Approval.created_at.desc()).all()
        return [serialize_approval(approval) for approval in approvals]


def decide_approval(
    *,
    approval_id: str,
    status: str,
    approver: str,
    decision_notes: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    if status not in DECISION_STATUSES:
        raise ValueError(f"Approval decision status must be one of: {', '.join(sorted(DECISION_STATUSES))}")

    with session_scope() as session:
        approval = session.get(Approval, approval_id)
        if approval is None:
            return None

        approval.status = status
        approval.approver = approver
        approval.decision_notes = decision_notes
        if approval.generated_output:
            approval.generated_output.status = status

        session.add(
            AgentEvent(
                project=approval.project,
                client_id=approval.project.client_id,
                agent_name=approval.requested_by_agent,
                event_type="approval_decided",
                channel="approval",
                summary=f"{status}: {approval.metadata_json.get('title', approval.id)}",
                payload={
                    "approval_id": approval.id,
                    "status": status,
                    "approver": approver,
                },
            )
        )
        session.flush()
        return serialize_approval(approval)


def require_approved_approval(
    *,
    approval_id: str,
    project_id: Optional[str] = None,
    action_type: Optional[str] = None,
) -> dict[str, Any]:
    with session_scope() as session:
        approval = session.get(Approval, approval_id)
        if approval is None:
            raise ValueError(f"Approval not found: {approval_id}")
        if approval.status != "approved":
            raise PermissionError(f"Approval {approval_id} is not approved")
        if project_id and approval.project_id != project_id:
            raise PermissionError("Approval does not belong to the requested project")
        if action_type and (approval.metadata_json or {}).get("action_type") != action_type:
            raise PermissionError("Approval does not match the requested action type")
        return serialize_approval(approval)
