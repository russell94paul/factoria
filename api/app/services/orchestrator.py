from sqlmodel import Session, select

from app.models.workflow_run import WorkflowRun
from app.models.gate_approval import GateApproval
from app.services.workflow_events import append_workflow_event
from app.services.agent_queue import AgentQueue
from app.workflows.ticket_to_pr import WORKFLOW_GRAPH, STATE_AGENT_MAP
from app.utils.time import utc_now

GATED_STATES = {"DESIGN_REVIEW", "READY_FOR_REVIEW"}


class Orchestrator:

    def __init__(self, session: Session):
        self.session = session

    def advance(self, workflow: WorkflowRun):
        if workflow.status != "running":
            return workflow

        if self._gate_is_pending(workflow):
            return workflow

        next_state = WORKFLOW_GRAPH.get(workflow.current_state)

        if not next_state:
            return workflow

        if next_state == "DONE":
            return self.complete_workflow(workflow)

        return self.transition(workflow, next_state)

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

    def complete_workflow(self, workflow: WorkflowRun):
        workflow = self.transition(workflow, "DONE")
        workflow.status = "succeeded"
        workflow.finished_at = utc_now()

        self.session.add(workflow)
        self.session.commit()

        return workflow

    def _gate_is_pending(self, workflow: WorkflowRun) -> bool:
        if workflow.current_state not in GATED_STATES:
            return False

        approval = self.session.exec(
            select(GateApproval)
            .where(
                GateApproval.workflow_run_id == workflow.workflow_run_id,
                GateApproval.gate_name == workflow.current_state,
                GateApproval.decision == "approved",
            )
            .order_by(GateApproval.decided_at.desc())
            .limit(1)
        ).first()

        return approval is None