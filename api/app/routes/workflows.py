from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models.workflow_run import WorkflowRun
from app.models.workflow_event import WorkflowEvent
from app.models.gate_approval import GateApproval
from app.services.orchestrator import Orchestrator, GATED_STATES

router = APIRouter(
	prefix="/workflows",
	tags=["workflows"]
)

@router.get("/{workflow_run_id}")
def get_workflow(workflow_run_id: str, session: Session = Depends(get_session)):
    run = session.get(WorkflowRun, workflow_run_id)
    
    if not run:
    	return {"error": "workflow run not found"}  
    events = session.exec(
        select(WorkflowEvent)
        .where(WorkflowEvent.workflow_run_id == workflow_run_id)
        .order_by(WorkflowEvent.seq)
    ).all() 
    return {
        "workflow_run_id": run.workflow_run_id,
        "ticket_id": run.ticket_id,
        "attempt": run.attempt,
        "status": run.status,
        "current_state": run.current_state,
        "trace_id": run.trace_id,
        "events": events
    }


@router.post("/{workflow_run_id}/advance")
def advance_workflow(workflow_run_id: str, session: Session = Depends(get_session)):
	
    workflow = session.get(WorkflowRun, workflow_run_id)

    if not workflow:
        return {"error": "workflow not found"}

    orchestrator = Orchestrator(session)

    updated = orchestrator.advance(workflow)

    return {
    "workflow_run_id": updated.workflow_run_id,
    "state": updated.current_state
    }


@router.post("/{workflow_run_id}/gates/{gate_name}/approve")
def approve_gate(workflow_run_id: str, gate_name: str, session: Session = Depends(get_session)):
	
    gate = gate_name.upper()

    if gate not in GATED_STATES:
        return {"error": "unknown gate"}

    workflow = session.get(WorkflowRun, workflow_run_id)

    if not workflow:
        return {"error": "workflow not found"}

    approval = GateApproval(
    workflow_run_id=workflow_run_id,
    gate_name=gate,
    decision="approved",
    actor_id="api",
    )

    session.add(approval)
    session.commit()

    orchestrator = Orchestrator(session)
    updated = orchestrator.advance(workflow)

    return {
    "workflow_run_id": updated.workflow_run_id,
    "state": updated.current_state,
    "gate": gate,
    "decision": "approved"
    }