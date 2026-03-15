import os
from pathlib import Path

WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "/workspace")).resolve()


class WorkspaceManager:

    def create_run_workspace(self, tenant_id: str, ticket_id: str, workflow_run_id: str) -> Path:
        path = (
            WORKSPACES_ROOT
            / "tenants"
            / str(tenant_id)
            / "tickets"
            / str(ticket_id)
            / "runs"
            / str(workflow_run_id)
        )
        path.mkdir(parents=True, exist_ok=True)
        return path