from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

from app.utils.time import utc_now


class AgentTask(SQLModel, table=True):

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    workflow_run_id: str
    agent_name: str

    status: str = "pending"  # pending | running | completed | failed

    created_at: datetime = Field(default_factory=utc_now)