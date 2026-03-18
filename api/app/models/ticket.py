from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

from app.utils.time import utc_now

class Ticket(SQLModel, table=True):

    ticket_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True
    )

    tenant_id: Optional[str] = None

    ticket_kind: str
    title: str
    description: Optional[str] = None

    state: str = "TICKET_INTAKE"
    last_error: Optional[str] = None

    # Structured requirements (stored as JSON strings)
    sources_json: Optional[str] = None      # list of source table/file names
    grain: Optional[str] = None             # e.g. "one row per order per day"
    metrics_json: Optional[str] = None      # list of metric definitions
    constraints_json: Optional[str] = None  # list of constraint notes

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)