import hashlib
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session, select

from app.db import get_session
from app.models.ticket import Ticket
from app.models.uploaded_file import UploadedFile
from app.models.workflow_run import WorkflowRun
from app.models.workflow_event import WorkflowEvent
from app.schemas.ticket_schema import TicketCreate
from app.services.agent_queue import AgentQueue
from app.services.runner_client import RunnerClient
from app.services.workflow_events import append_workflow_event
from app.services.workspace_manager import WorkspaceManager, WORKSPACES_ROOT
from app.workflows.ticket_to_pr import STATE_AGENT_MAP
from app.services.orchestrator import Orchestrator

ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".parquet", ".json", ".jsonl"}


router = APIRouter(
    prefix="/tickets",
    tags=["tickets"]
)


@router.post("")
def create_ticket(ticket: TicketCreate, session: Session = Depends(get_session)):
    new_ticket = Ticket(
        ticket_kind=ticket.ticket_kind,
        title=ticket.title,
        description=ticket.description,
        sources_json=json.dumps(ticket.sources) if ticket.sources else None,
        grain=ticket.grain,
        metrics_json=json.dumps(ticket.metrics) if ticket.metrics else None,
        constraints_json=json.dumps(ticket.constraints) if ticket.constraints else None,
    )
    session.add(new_ticket)
    session.commit()
    session.refresh(new_ticket)

    existing_runs = session.exec(
        select(WorkflowRun).where(WorkflowRun.ticket_id == new_ticket.ticket_id)
    ).all()
    attempt = len(existing_runs) + 1

    workflow = WorkflowRun(
        ticket_id=new_ticket.ticket_id,
        attempt=attempt,
        current_state="DATA_INGESTION",
    )

    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    tenant_id = new_ticket.tenant_id or "default"
    workspace = WorkspaceManager().create_run_workspace(
        tenant_id=tenant_id,
        ticket_id=workflow.ticket_id,
        workflow_run_id=workflow.workflow_run_id,
    )

    workflow.workspace_root = str(workspace)
    session.add(workflow)
    session.commit()

    append_workflow_event(
        session,
        workflow_run_id=workflow.workflow_run_id,
        ticket_id=new_ticket.ticket_id,
        trace_id=workflow.trace_id,
        event_type="state_transition",
        from_state=None,
        to_state="DATA_INGESTION",
        message="Workflow run started",
    )

    queue = AgentQueue(session)
    queue.enqueue(
        workflow.workflow_run_id,
        STATE_AGENT_MAP["DATA_INGESTION"],
    )

    return {
        "ticket_id": new_ticket.ticket_id,
        "workflow_run_id": workflow.workflow_run_id,
        "attempt": workflow.attempt,
        "trace_id": workflow.trace_id,
        "state": workflow.current_state,
    }


@router.get("")
def list_tickets(session: Session = Depends(get_session)):
    tickets = session.exec(select(Ticket).order_by(Ticket.created_at.desc())).all()
    result = []
    for ticket in tickets:
        run = session.exec(
            select(WorkflowRun)
            .where(WorkflowRun.ticket_id == ticket.ticket_id)
            .order_by(WorkflowRun.started_at.desc())
        ).first()
        result.append({
            "ticket_id": ticket.ticket_id,
            "title": ticket.title,
            "description": ticket.description,
            "ticket_kind": ticket.ticket_kind,
            "state": ticket.state,
            "created_at": ticket.created_at,
            "current_state": run.current_state if run else ticket.state,
            "workflow_run_id": run.workflow_run_id if run else None,
            "workflow_status": run.status if run else None,
            "last_error": ticket.last_error,
        })
    return result


@router.get("/{ticket_id}")
def get_ticket(ticket_id: str, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        return {"error": "ticket not found"}
    return ticket


@router.get("/{ticket_id}/workflow")
def get_ticket_workflow(ticket_id: str, session: Session = Depends(get_session)):
    run = session.exec(
        select(WorkflowRun)
        .where(WorkflowRun.ticket_id == ticket_id)
        .order_by(WorkflowRun.started_at.desc())
    ).first()
    if not run:
        return {"error": "no workflow run"}
    return {"workflow_run_id": run.workflow_run_id}


# ---------------------------------------------------------------------------
# File upload endpoints
# ---------------------------------------------------------------------------

@router.post("/{ticket_id}/uploads")
async def upload_file(
    ticket_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"file type '{suffix}' not allowed; accepted: {sorted(ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    tenant_id = ticket.tenant_id or "default"
    uploads_dir = WorkspaceManager().get_uploads_dir(tenant_id, ticket_id)

    # Sanitise filename: keep stem + suffix only
    safe_name = Path(file.filename).name
    dest = uploads_dir / safe_name

    content = await file.read()
    dest.write_bytes(content)

    checksum = hashlib.sha256(content).hexdigest()
    mime = file.content_type or "application/octet-stream"

    record = UploadedFile(
        ticket_id=ticket_id,
        filename=safe_name,
        stored_path=str(dest),
        size_bytes=len(content),
        checksum_sha256=checksum,
        mime_type=mime,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    return {
        "file_id": record.file_id,
        "filename": record.filename,
        "size_bytes": record.size_bytes,
        "checksum_sha256": record.checksum_sha256,
        "mime_type": record.mime_type,
    }


@router.get("/{ticket_id}/uploads")
def list_uploads(ticket_id: str, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")

    files = session.exec(
        select(UploadedFile).where(UploadedFile.ticket_id == ticket_id)
    ).all()
    return [
        {
            "file_id": f.file_id,
            "filename": f.filename,
            "size_bytes": f.size_bytes,
            "mime_type": f.mime_type,
            "schema_json": json.loads(f.schema_json) if f.schema_json else None,
            "uploaded_at": f.uploaded_at,
        }
        for f in files
    ]


@router.get("/{ticket_id}/data-preview")
def data_preview(
    ticket_id: str,
    table: str,
    session: Session = Depends(get_session),
):
    ticket = session.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="ticket not found")

    tenant_id = ticket.tenant_id or "default"
    catalog_path = WorkspaceManager().get_catalog_path(tenant_id, ticket_id)
    catalog_rel = str(catalog_path.relative_to(WORKSPACES_ROOT))

    runner = RunnerClient()
    try:
        result = runner.run_job("data_preview", catalog_rel, {"table_name": table})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"runner error: {exc}")

    return result
