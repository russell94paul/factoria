from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select

from app.db import get_session
from app.models.artifact import Artifact

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/tickets/{ticket_id}")
def list_ticket_artifacts(ticket_id: str, session: Session = Depends(get_session)):
    artifacts = session.exec(
        select(Artifact)
        .where(Artifact.ticket_id == ticket_id)
        .order_by(Artifact.created_at)
    ).all()
    return artifacts


@router.get("/{artifact_id}/content")
def get_artifact_content(artifact_id: str, session: Session = Depends(get_session)):
    artifact = session.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    path = Path(artifact.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    content = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        media_type = "application/json"
    else:
        media_type = "text/plain"

    return Response(content=content, media_type=media_type)
