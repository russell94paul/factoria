from sqlmodel import select

from app.models.workflow_event import WorkflowEvent
from app.models.workflow_run import WorkflowRun

from app.services.orchestrator import Orchestrator
from app.services.agent_queue import AgentQueue
from app.workflows.ticket_to_pr import STATE_AGENT_MAP


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

        # When state changes → enqueue agent
        if event.event_type == "state_transition":

            agent_name = STATE_AGENT_MAP.get(workflow.current_state)

            if agent_name:
                queue = AgentQueue(self.session)
                queue.enqueue(workflow.workflow_run_id, agent_name)

        # When agent finishes → advance workflow
        elif event.event_type == "agent_completed":

            self.orchestrator.advance(workflow)