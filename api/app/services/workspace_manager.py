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

    def get_ticket_workspace(self, tenant_id: str, ticket_id: str) -> Path:
        path = (
            WORKSPACES_ROOT
            / "tenants"
            / str(tenant_id)
            / "tickets"
            / str(ticket_id)
        )
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_uploads_dir(self, tenant_id: str, ticket_id: str) -> Path:
        path = self.get_ticket_workspace(tenant_id, ticket_id) / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_catalog_path(self, tenant_id: str, ticket_id: str) -> Path:
        """Path to the ticket-level DuckDB catalog (shared across runs).
        The directory is created lazily; the .duckdb file only exists after ingestion."""
        catalog_dir = self.get_ticket_workspace(tenant_id, ticket_id) / "duckdb"
        # Don't mkdir here — let the runner create it when it actually loads data
        return catalog_dir / "catalog.duckdb"
