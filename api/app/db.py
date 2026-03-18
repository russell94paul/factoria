from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = "sqlite:////workspace/factoria.db"

engine = create_engine(DATABASE_URL, echo=True)

# IMPORTANT: import all models so SQLModel knows about them
from app.models.ticket import Ticket
from app.models.workflow_run import WorkflowRun
from app.models.workflow_event import WorkflowEvent
from app.models.agent_task import AgentTask
from app.models.artifact import Artifact
from app.models.agent_session import AgentSession
from app.models.gate_approval import GateApproval
from app.models.tenant import Tenant
from app.models.runner_job import RunnerJob
from app.models.uploaded_file import UploadedFile


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    
def get_session():
    with Session(engine) as session:
        yield session