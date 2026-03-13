from sqlmodel import Session
from app.models.workflow_run import WorkflowRun
from app.services.workflow_events import append_workflow_event


class Orchestrator:

    def __init__(self, session: Session):
        self.session = session

        # State machine registry
        self.handlers = {
            "TICKET_INTAKE": self.handle_ticket_intake,
            "DESIGN_REVIEW": self.handle_design_review,
            "PROFILING": self.handle_profiling,
            "BUILD": self.handle_build,
            "QA": self.handle_qa,
        }

    # -------------------------
    # Advance workflow
    # -------------------------

    def advance(self, workflow: WorkflowRun):

        if workflow.status != "running":
            return workflow

        state = workflow.current_state

        handler = self.handlers.get(state)

        if not handler:
            return workflow

        return handler(workflow)

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

        from app.services.agent_queue import AgentQueue
        from app.workflows.ticket_to_pr import STATE_AGENT_MAP

        # Queue agent execution for the new state
        agent_name = STATE_AGENT_MAP.get(new_state)

        if agent_name:
            queue = AgentQueue(self.session)
            queue.enqueue(workflow.workflow_run_id, agent_name)

        return workflow

    # -------------------------
    # State Handlers
    # -------------------------

    def handle_ticket_intake(self, workflow: WorkflowRun):

        return self.transition(workflow, "DESIGN_REVIEW")

    def handle_design_review(self, workflow: WorkflowRun):

        return self.transition(workflow, "PROFILING")

    def handle_profiling(self, workflow: WorkflowRun):

        return self.transition(workflow, "BUILD")

    def handle_build(self, workflow: WorkflowRun):

        return self.transition(workflow, "QA")

    def handle_qa(self, workflow: WorkflowRun):

        return self.transition(workflow, "PR_CREATION")