from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models.agent_session import AgentSession

router = APIRouter(prefix="/workflows", tags=["sessions"])


@router.get("/{workflow_run_id}/sessions")
def list_workflow_sessions(workflow_run_id: str, session: Session = Depends(get_session)):
    sessions = session.exec(
        select(AgentSession)
        .where(AgentSession.workflow_run_id == workflow_run_id)
        .order_by(AgentSession.started_at)
    ).all()
    return sessions
