from sqlmodel import Session, select
from pathlib import Path

from app.services.openclaw_service import OpenClawClient
from app.services.workflow_events import append_workflow_event
from app.services.artifact_service import ArtifactService
from app.models.agent_session import AgentSession
from app.models.workflow_run import WorkflowRun


from app.workflows.ticket_to_pr import STATE_AGENT_MAP

AGENT_STATE_MAP = {agent: state for state, agent in STATE_AGENT_MAP.items()}


STATE_ARTIFACT_MAP = {
    "TICKET_INTAKE": "intake.md",
    "DESIGN_REVIEW": "design.md",
    "PROFILING": "profiling_report.json",
    "BUILD": "build_summary.json",
    "QA": "qa_report.md",
}


class AgentRunner:

    def __init__(self, session: Session):
        self.session = session
        self.client = OpenClawClient()

    def run_task(self, workflow_run, agent_name):
        target_state = AGENT_STATE_MAP.get(agent_name)

        if not target_state:
            print(f"Unknown agent '{agent_name}' for workflow {workflow_run.workflow_run_id}")
            return None

        existing = self.session.exec(
            select(AgentSession).where(
                AgentSession.workflow_run_id == workflow_run.workflow_run_id,
                AgentSession.agent_name == agent_name,
            )
        ).first()

        if existing:
            print(f"Agent already executed for this state: {agent_name}")
            return None

        agent_session = AgentSession(
            workflow_run_id=workflow_run.workflow_run_id,
            ticket_id=workflow_run.ticket_id,
            tenant_id="default",
            agent_name=agent_name,
            status="running",
        )

        self.session.add(agent_session)
        self.session.commit()
        self.session.refresh(agent_session)

        result = self.client.start_agent(
            agent_name=agent_name,
            workflow_run_id=workflow_run.workflow_run_id,
        )
        workspace = Path(workflow_run.workspace_root)

        artifact_name = STATE_ARTIFACT_MAP.get(target_state, f"{agent_name}.md")
        artifact_path = workspace / artifact_name

        artifact_path.write_text(
            f"# {agent_name} Output\n\n"
            f"Workflow Run: {workflow_run.workflow_run_id}\n"
            f"State: {target_state}\n"
        )

        artifact_service = ArtifactService(self.session)
        artifact_service.register_artifact(
            workflow_run_id=workflow_run.workflow_run_id,
            ticket_id=workflow_run.ticket_id,
            artifact_role="agent_output",
            artifact_type="markdown",
            file_path=str(artifact_path),
        )

        self.mark_agent_complete(agent_session)

        return result
    
    def mark_agent_complete(self, agent_session: AgentSession):

        if agent_session.status == "completed":
            return
    
        agent_session.status = "completed"
    
        self.session.add(agent_session)
        self.session.commit()
    
        workflow_run = self.session.get(
            WorkflowRun,
            agent_session.workflow_run_id
        )
    
        append_workflow_event(
            self.session,
            workflow_run_id=workflow_run.workflow_run_id,
            ticket_id=workflow_run.ticket_id,
            trace_id=workflow_run.trace_id,
            event_type="agent_completed",
            message=f"{agent_session.agent_name} completed",
        )
    