from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
import uuid

from app.utils.time import utc_now


class Tenant(SQLModel, table=True):
    tenant_id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_key: str = Field(unique=True)       # human slug, e.g. "retail_001"
    name: str
    status: str = "requested"                  # requested|provisioning_running|ready|disabled|error
    snowflake_connection_alias: Optional[str] = None
    dbt_repo_url: Optional[str] = None
    dbt_default_branch: Optional[str] = None
    workspace_root: Optional[str] = None
    last_error: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
