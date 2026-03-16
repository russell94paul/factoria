from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import uuid

from app.utils.time import utc_now


class UploadedFile(SQLModel, table=True):
    __tablename__ = "uploaded_file"

    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    ticket_id: str
    filename: str
    stored_path: str            # absolute path on disk
    size_bytes: int = 0
    checksum_sha256: Optional[str] = None
    mime_type: Optional[str] = None
    schema_json: Optional[str] = None      # inferred columns: [{name, type}]
    uploaded_at: datetime = Field(default_factory=utc_now)
