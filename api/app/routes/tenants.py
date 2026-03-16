import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models.tenant import Tenant
from app.models.ticket import Ticket
from app.models.workflow_run import WorkflowRun
from app.services.workflow_events import append_workflow_event
from app.services.agent_queue import AgentQueue
from app.services.workspace_manager import WorkspaceManager
from app.workflows.tenant_provisioning import STATE_AGENT_MAP
from app.utils.time import utc_now


router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantCreate(BaseModel):
    tenant_key: str
    name: str
    snowflake_connection_alias: str | None = None
    dbt_repo_url: str | None = None


def _enqueue_provisioning(session: Session, tenant: Tenant) -> dict:
    ticket = Ticket(
        tenant_id=tenant.tenant_id,
        ticket_kind="TENANT_PROVISIONING",
        title=f"Provision tenant: {tenant.tenant_key}",
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    existing_runs = session.exec(
        select(WorkflowRun).where(WorkflowRun.ticket_id == ticket.ticket_id)
    ).all()
    attempt = len(existing_runs) + 1

    workflow = WorkflowRun(
        ticket_id=ticket.ticket_id,
        tenant_id=tenant.tenant_id,
        workflow_name="tenant_provisioning",
        attempt=attempt,
        current_state="PROVISIONING_REQUESTED",
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)

    workspace = WorkspaceManager().create_run_workspace(
        tenant_id=tenant.tenant_id,
        ticket_id=ticket.ticket_id,
        workflow_run_id=workflow.workflow_run_id,
    )
    workflow.workspace_root = str(workspace)
    session.add(workflow)
    session.commit()

    append_workflow_event(
        session,
        workflow_run_id=workflow.workflow_run_id,
        ticket_id=ticket.ticket_id,
        trace_id=workflow.trace_id,
        event_type="state_transition",
        from_state=None,
        to_state="PROVISIONING_REQUESTED",
        message="Tenant provisioning workflow started",
    )

    AgentQueue(session).enqueue(workflow.workflow_run_id, STATE_AGENT_MAP["PROVISIONING_REQUESTED"])

    return {
        "ticket_id": ticket.ticket_id,
        "workflow_run_id": workflow.workflow_run_id,
    }


@router.post("")
def create_tenant(body: TenantCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(Tenant).where(Tenant.tenant_key == body.tenant_key)).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"tenant_key '{body.tenant_key}' already exists")

    tenant = Tenant(
        tenant_key=body.tenant_key,
        name=body.name,
        snowflake_connection_alias=body.snowflake_connection_alias,
        dbt_repo_url=body.dbt_repo_url,
        status="requested",
    )
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    ids = _enqueue_provisioning(session, tenant)

    return {
        "tenant_id": tenant.tenant_id,
        "tenant_key": tenant.tenant_key,
        "status": tenant.status,
        **ids,
    }


@router.get("")
def list_tenants(session: Session = Depends(get_session)):
    tenants = session.exec(select(Tenant).order_by(Tenant.created_at.desc())).all()
    result = []
    for t in tenants:
        run = session.exec(
            select(WorkflowRun)
            .where(WorkflowRun.tenant_id == t.tenant_id)
            .order_by(WorkflowRun.started_at.desc())
        ).first()
        result.append({
            "tenant_id": t.tenant_id,
            "tenant_key": t.tenant_key,
            "name": t.name,
            "status": t.status,
            "last_error": t.last_error,
            "workspace_root": t.workspace_root,
            "created_at": t.created_at,
            "workflow_run_id": run.workflow_run_id if run else None,
            "workflow_status": run.status if run else None,
        })
    return result


@router.get("/{tenant_id}")
def get_tenant(tenant_id: str, session: Session = Depends(get_session)):
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    run = session.exec(
        select(WorkflowRun)
        .where(WorkflowRun.tenant_id == tenant_id)
        .order_by(WorkflowRun.started_at.desc())
    ).first()
    return {
        "tenant_id": tenant.tenant_id,
        "tenant_key": tenant.tenant_key,
        "name": tenant.name,
        "status": tenant.status,
        "last_error": tenant.last_error,
        "workspace_root": tenant.workspace_root,
        "dbt_repo_url": tenant.dbt_repo_url,
        "created_at": tenant.created_at,
        "workflow_run_id": run.workflow_run_id if run else None,
        "workflow_status": run.status if run else None,
    }


@router.post("/{tenant_id}/provision")
def retry_provision(tenant_id: str, session: Session = Depends(get_session)):
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    if tenant.status not in ("error", "requested"):
        raise HTTPException(status_code=409, detail=f"cannot retry provisioning from status '{tenant.status}'")

    tenant.status = "requested"
    tenant.last_error = None
    session.add(tenant)
    session.commit()

    ids = _enqueue_provisioning(session, tenant)
    return {"tenant_id": tenant_id, **ids}


@router.post("/{tenant_id}/reset")
def reset_tenant(tenant_id: str, session: Session = Depends(get_session)):
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    if tenant.status not in ("ready", "error", "disabled"):
        raise HTTPException(status_code=409, detail=f"cannot reset tenant from status '{tenant.status}'")

    if tenant.workspace_root and os.path.exists(tenant.workspace_root):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        archived = f"{tenant.workspace_root}.archived.{ts}"
        os.rename(tenant.workspace_root, archived)

    tenant.status = "requested"
    tenant.last_error = None
    tenant.workspace_root = None
    session.add(tenant)
    session.commit()

    ids = _enqueue_provisioning(session, tenant)
    return {"tenant_id": tenant_id, **ids}
