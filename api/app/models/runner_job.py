from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import uuid

from app.utils.time import utc_now


class RunnerJob(SQLModel, table=True):
    __tablename__ = "runner_job"

    runner_job_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workflow_run_id: str
    ticket_id: str
    request_id: str = Field(unique=True)       # idempotency: "<wf_run_id>:<job_type>:<seq>"
    parent_job_id: Optional[str] = None        # retry chain
    job_type: str                              # snowflake_sql|dbt_compile|…
    status: str = "queued"                     # queued|running|succeeded|failed
    attempt: int = 1
    request_payload_json: Optional[str] = None
    result_payload_json: Optional[str] = None
    error_message: Optional[str] = None
    requested_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
