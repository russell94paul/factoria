from sqlmodel import SQLModel, Field
from datetime import datetime
import uuid

from app.utils.time import utc_now


class Artifact(SQLModel, table=True):

    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)

    workflow_run_id: str
    ticket_id: str

    artifact_role: str
    artifact_type: str

    file_path: str

    created_at: datetime = Field(default_factory=utc_now)