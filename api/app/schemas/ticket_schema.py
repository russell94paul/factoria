from pydantic import BaseModel
from typing import Optional, List


class TicketCreate(BaseModel):
    ticket_kind: str
    title: str
    description: Optional[str] = None
    # Structured requirements
    sources: Optional[List[str]] = None         # source table/file names
    grain: Optional[str] = None                 # e.g. "one row per order per day"
    metrics: Optional[List[str]] = None         # metric definitions
    constraints: Optional[List[str]] = None     # constraint notes
