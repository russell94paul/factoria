from sqlmodel import Session, select
from app.models.workflow_event import WorkflowEvent


def append_workflow_event(
    session: Session,
    *,
    workflow_run_id: str,
    ticket_id: str,
    trace_id: str,
    event_type: str,
    to_state: str | None = None,
    from_state: str | None = None,
    actor_type: str = "system",
    actor_id: str = "orchestrator",
    message: str | None = None,
    payload_json: str | None = None,
) -> WorkflowEvent:
    # compute next seq for this workflow_run_id
    last = session.exec(
        select(WorkflowEvent)
        .where(WorkflowEvent.workflow_run_id == workflow_run_id)
        .order_by(WorkflowEvent.seq.desc())
        .limit(1)
    ).first()

    next_seq = (last.seq + 1) if last else 1

    ev = WorkflowEvent(
        workflow_run_id=workflow_run_id,
        ticket_id=ticket_id,
        seq=next_seq,
        trace_id=trace_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor_type=actor_type,
        actor_id=actor_id,
        message=message,
        payload_json=payload_json,
    )

    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev