from sqlmodel import Session

from app.models.agent_task import AgentTask


class AgentQueue:

    def __init__(self, session):
        self.session = session

    def enqueue(self, workflow_run_id, agent_name):

        task = AgentTask(
            workflow_run_id=workflow_run_id,
            agent_name=agent_name,
            status="pending",
        )

        self.session.add(task)
        self.session.commit()