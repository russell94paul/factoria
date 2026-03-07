from app.models.workflow_event import WorkflowEvent
from app.workflows.ticket_to_pr import WORKFLOW_GRAPH, STATE_AGENT_MAP


class WorkflowRuntimeGraphService:

    def __init__(self, session):
        self.session = session

    def get_completed_states(self, workflow_run_id):

        events = (
            self.session.query(WorkflowEvent)
            .filter(WorkflowEvent.workflow_run_id == workflow_run_id)
            .filter(WorkflowEvent.event_type == "agent_completed")
            .all()
        )

        completed_states = []

        # reverse agent map
        agent_to_state = {v: k for k, v in STATE_AGENT_MAP.items()}

        for e in events:

            agent_name = e.message.replace(" completed", "")

            state = agent_to_state.get(agent_name)

            if state:
                completed_states.append(state)

        return completed_states

    def generate_mermaid(self, workflow_run_id):

        completed = self.get_completed_states(workflow_run_id)

        lines = ["graph TD"]

        for state, next_state in WORKFLOW_GRAPH.items():

            if state in completed:
                style = ":::done"
            else:
                style = ""

            if next_state:
                lines.append(f"{state}{style} --> {next_state}")
            else:
                lines.append(f"{state}{style}")

        lines.append("")
        lines.append("classDef done fill:#90EE90")

        return "\n".join(lines)