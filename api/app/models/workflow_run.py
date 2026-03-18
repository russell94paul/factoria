from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

from app.utils.time import utc_now


class WorkflowRun(SQLModel, table=True):
    workflow_run_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    ticket_id: str

    workflow_name: str = "ticket_to_pr"
    attempt: int = 1

    status: str = "running"
    current_state: str = "TICKET_INTAKE"
    state_entered_at: datetime = Field(default_factory=utc_now)

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    
    workspace_root: str | None = None
    tenant_id: str | None = None
    last_error: str | None = None
    error_code: str | None = None   # AGENT_FAILED | RUNNER_ERROR | TIMEOUT