from sqlmodel import select

from app.models.workflow_event import WorkflowEvent
from app.models.workflow_run import WorkflowRun

from app.services.orchestrator import Orchestrator


class WorkflowEventConsumer:
    def __init__(self, session):
        self.session = session
        self.orchestrator = Orchestrator(session)

    def handle_event(self, event: WorkflowEvent):
        workflow = self.session.exec(
            select(WorkflowRun).where(
                WorkflowRun.workflow_run_id == event.workflow_run_id
            )
        ).first()

        if not workflow:
            return

        if event.event_type == "agent_completed":
            self.orchestrator.advance(workflow)