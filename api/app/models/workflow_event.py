from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

from app.utils.time import utc_now


class WorkflowEvent(SQLModel, table=True):
    workflow_event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    workflow_run_id: str
    ticket_id: str

    seq: int = 0  # monotonic per workflow_run_id

    event_type: str = "state_transition"
    from_state: str | None = None
    to_state: str | None = None

    actor_type: str = "system"
    actor_id: str | None = None

    message: str | None = None
    payload_json: str | None = None  # keep as TEXT for now; later JSON

    trace_id: str | None = None

    created_at: datetime = Field(default_factory=utc_now)