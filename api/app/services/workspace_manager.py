from pathlib import Path

WORKSPACE_ROOT = Path("/workspace")


class WorkspaceManager:

    def create_run_workspace(self, tenant_id, ticket_id, workflow_run_id):

        path = (
            WORKSPACE_ROOT
            / "tenants"
            / str(tenant_id)
            / "tickets"
            / str(ticket_id)
            / "runs"
            / str(workflow_run_id)
        )

        path.mkdir(parents=True, exist_ok=True)

        return path