from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models.ticket import Ticket
from app.models.workflow_run import WorkflowRun
from app.models.workflow_event import WorkflowEvent
from app.schemas.ticket_schema import TicketCreate
from app.services.workflow_events import append_workflow_event
from app.services.agent_queue import AgentQueue
from app.workflows.ticket_to_pr import STATE_AGENT_MAP

from app.services.orchestrator import Orchestrator
from app.services.workspace_manager import WorkspaceManager


router = APIRouter(
	prefix="/tickets",
	tags=["tickets"]
)


@router.post("")
def create_ticket(ticket: TicketCreate, session: Session = Depends(get_session)):
    new_ticket = Ticket(
        ticket_kind=ticket.ticket_kind,
        title=ticket.title,
        description=ticket.description
    )
    session.add(new_ticket)
    session.commit()
    session.refresh(new_ticket)

    # compute attempt (future-proof for retries)
    existing_runs = session.exec(
        select(WorkflowRun).where(WorkflowRun.ticket_id == new_ticket.ticket_id)
    ).all()
    attempt = len(existing_runs) + 1

    workflow = WorkflowRun(
        ticket_id=new_ticket.ticket_id,
        attempt=attempt,
        current_state="TICKET_INTAKE",
    )

    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    # Create workspace for this run
    workspace = WorkspaceManager().create_run_workspace(
        tenant_id="default",
        ticket_id=workflow.ticket_id,
        workflow_run_id=workflow.workflow_run_id
    )

    workflow.workspace_root = str(workspace)

    session.add(workflow)
    session.commit()

    # log the initial state transition as an event
    append_workflow_event(
        session,
        workflow_run_id=workflow.workflow_run_id,
        ticket_id=new_ticket.ticket_id,
        trace_id=workflow.trace_id,
        event_type="state_transition",
        from_state=None,
        to_state="TICKET_INTAKE",
        message="Workflow run started",
    )

    queue = AgentQueue(session)
    queue.enqueue(
        workflow.workflow_run_id,
        STATE_AGENT_MAP["TICKET_INTAKE"],
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