from sqlmodel import Session

from app.models.workflow_run import WorkflowRun
from app.services.workflow_events import append_workflow_event
from app.services.agent_queue import AgentQueue
from app.workflows.ticket_to_pr import WORKFLOW_GRAPH, STATE_AGENT_MAP
from app.utils.time import utc_now

class Orchestrator:

    def __init__(self, session: Session):
        self.session = session

    # -------------------------
    # Advance workflow
    # -------------------------

    def advance(self, workflow: WorkflowRun):
        if workflow.status != "running":
            return workflow

        next_state = WORKFLOW_GRAPH.get(workflow.current_state)

        if not next_state:
            return workflow

        if next_state == "DONE":
            return self.complete_workflow(workflow)

        return self.transition(workflow, next_state)

    # -------------------------
    # State transition
    # -------------------------

    def transition(self, workflow: WorkflowRun, new_state: str):
        old_state = workflow.current_state
        workflow.current_state = new_state

        append_workflow_event(
            self.session,
            workflow_run_id=workflow.workflow_run_id,
            ticket_id=workflow.ticket_id,
            trace_id=workflow.trace_id,
            event_type="state_transition",
            from_state=old_state,
            to_state=new_state,
        )

        self.session.add(workflow)
        self.session.commit()

        agent_name = STATE_AGENT_MAP.get(new_state)

        if agent_name:
            queue = AgentQueue(self.session)
            queue.enqueue(workflow.workflow_run_id, agent_name)

        return workflow

    # -------------------------
    # Workflow completion
    # -------------------------

    def complete_workflow(self, workflow: WorkflowRun):

        workflow = self.transition(workflow, "DONE")
        workflow.status = "succeeded"
        workflow.finished_at = utc_now()

        self.session.add(workflow)
        self.session.commit()

        return workflow