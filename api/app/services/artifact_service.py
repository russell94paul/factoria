from sqlmodel import Session

from app.models.artifact import Artifact


class ArtifactService:

    def __init__(self, session: Session):
        self.session = session

    def register_artifact(
        self,
        workflow_run_id: str,
        ticket_id: str,
        artifact_role: str,
        artifact_type: str,
        file_path: str,
    ):

        artifact = Artifact(
            workflow_run_id=workflow_run_id,
            ticket_id=ticket_id,
            artifact_role=artifact_role,
            artifact_type=artifact_type,
            file_path=file_path,
        )

        self.session.add(artifact)
        self.session.commit()
        self.session.refresh(artifact)

        return artifact