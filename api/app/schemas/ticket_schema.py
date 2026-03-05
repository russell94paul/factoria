from pydantic import BaseModel


class TicketCreate(BaseModel):
    ticket_kind: str
    title: str
    description: str | None = None