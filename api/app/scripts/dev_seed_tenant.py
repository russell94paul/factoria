"""
dev_seed_tenant.py — Smoke-test script for Milestone 4.

Creates a tenant, polls the provisioning workflow to completion (with one
automatic retry on first failure), then optionally creates a data-engineering
ticket and runs it through to DONE.

Usage (from repo root, with API running on localhost:8000):
    python -m app.scripts.dev_seed_tenant

Flags:
    --skip-ticket       Provision the tenant only; do not create/run a ticket workflow.

Environment variables:
    API_BASE            API base URL (default: http://localhost:8000)
    WORKSPACES_ROOT     Path to workspace root (default: ./workspace)
    AUTO_APPROVE_GATES  Set to "false" to log gates but not auto-approve them.
                        Defaults to "true" so CI stays stable.
"""

import os
import sys
import time
from pathlib import Path

import requests

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
POLL_INTERVAL = 2
TIMEOUT = 180
WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "./workspace"))

AUTO_APPROVE_GATES = os.getenv("AUTO_APPROVE_GATES", "true").lower() not in ("false", "0", "no")

GATED_STATES = {"DESIGN_REVIEW", "READY_FOR_REVIEW"}
TERMINAL_WF_STATUSES = {"succeeded", "failed", "cancelled"}
TERMINAL_TENANT_STATUSES = {"ready", "error", "disabled"}


def poll_workflow(workflow_run_id: str, timeout: int, label: str) -> dict:
    """Poll a workflow run until terminal or timeout. Returns final workflow dict."""
    deadline = time.time() + timeout
    approved_gates: set[str] = set()
    wf = {}

    while time.time() < deadline:
        resp = requests.get(f"{API_BASE}/workflows/{workflow_run_id}", timeout=10)
        if resp.status_code != 200:
            print(f"[{label}] ERROR polling workflow: {resp.status_code}")
            time.sleep(POLL_INTERVAL)
            continue

        wf = resp.json()
        current_state = wf.get("current_state", "?")
        status = wf.get("status", "?")
        print(f"[{label}] state={current_state:<25} status={status}")

        if current_state in GATED_STATES and current_state not in approved_gates:
            if AUTO_APPROVE_GATES:
                print(f"[{label}] approving gate: {current_state}")
                gate_resp = requests.post(
                    f"{API_BASE}/workflows/{workflow_run_id}/gates/{current_state}/approve",
                    timeout=10,
                )
                if gate_resp.status_code == 200:
                    approved_gates.add(current_state)
                    print(f"[{label}] gate approved -> {gate_resp.json().get('state')}")
                else:
                    print(f"[{label}] gate approval failed: {gate_resp.status_code} {gate_resp.text}")
            else:
                print(f"[{label}] gate {current_state} waiting — AUTO_APPROVE_GATES=false, approve manually")

        if status in TERMINAL_WF_STATUSES:
            return wf

        time.sleep(POLL_INTERVAL)

    print(f"\n[{label}] TIMEOUT after {timeout}s")
    return wf


def poll_tenant(tenant_id: str, timeout: int, label: str) -> dict:
    deadline = time.time() + timeout
    tenant = {}

    while time.time() < deadline:
        resp = requests.get(f"{API_BASE}/tenants/{tenant_id}", timeout=10)
        if resp.status_code != 200:
            print(f"[{label}] ERROR polling tenant: {resp.status_code}")
            time.sleep(POLL_INTERVAL)
            continue

        tenant = resp.json()
        status = tenant.get("status", "?")
        wf_status = tenant.get("workflow_status", "?")
        print(f"[{label}] tenant_status={status:<25} workflow_status={wf_status}")

        if status in TERMINAL_TENANT_STATUSES:
            return tenant

        time.sleep(POLL_INTERVAL)

    print(f"\n[{label}] TIMEOUT after {timeout}s")
    return tenant


def main():
    skip_ticket = "--skip-ticket" in sys.argv

    print(f"[seed_tenant] API: {API_BASE}")
    print(f"[seed_tenant] AUTO_APPROVE_GATES: {AUTO_APPROVE_GATES}")
    print(f"[seed_tenant] skip_ticket: {skip_ticket}")
    print()

    # --- Step 1: Create or fetch tenant ---
    resp = requests.post(f"{API_BASE}/tenants", json={
        "tenant_key": "retail_001",
        "name": "Retail Demo",
    }, timeout=10)

    if resp.status_code == 409:
        print("[seed_tenant] tenant 'retail_001' already exists — fetching it")
        tenants = requests.get(f"{API_BASE}/tenants", timeout=10).json()
        tenant_row = next((t for t in tenants if t["tenant_key"] == "retail_001"), None)
        if not tenant_row:
            print("[seed_tenant] ERROR: could not find existing tenant")
            sys.exit(1)
        tenant_id = tenant_row["tenant_id"]
        workflow_run_id = tenant_row.get("workflow_run_id")
    elif resp.status_code != 200:
        print(f"[seed_tenant] ERROR creating tenant: {resp.status_code} {resp.text}")
        sys.exit(1)
    else:
        data = resp.json()
        tenant_id = data["tenant_id"]
        workflow_run_id = data["workflow_run_id"]

    print(f"[seed_tenant] tenant_id       : {tenant_id}")
    print(f"[seed_tenant] workflow_run_id : {workflow_run_id}")
    print()

    # --- Step 2: Poll provisioning ---
    tenant = poll_tenant(tenant_id, TIMEOUT, "provision")
    print()

    if tenant.get("status") == "error":
        print("[seed_tenant] provisioning failed, attempting one retry...")
        retry_resp = requests.post(f"{API_BASE}/tenants/{tenant_id}/provision", timeout=10)
        if retry_resp.status_code != 200:
            print(f"[seed_tenant] ERROR starting retry: {retry_resp.status_code} {retry_resp.text}")
            sys.exit(1)
        print(f"[seed_tenant] retry workflow_run_id: {retry_resp.json().get('workflow_run_id')}")
        print()
        tenant = poll_tenant(tenant_id, TIMEOUT, "provision-retry")
        print()

    if tenant.get("status") != "ready":
        print(f"[seed_tenant] FAILED — tenant status={tenant.get('status')} last_error={tenant.get('last_error')}")
        sys.exit(1)

    print("[seed_tenant] Tenant is READY")

    if skip_ticket:
        print("[seed_tenant] --skip-ticket set — stopping after tenant provisioning.")
        print("[seed_tenant] Done.")
        return

    print()

    # --- Step 3: Create ticket ---
    resp = requests.post(f"{API_BASE}/tickets", json={
        "ticket_kind": "DATA_ENGINEERING",
        "title": "Add fct_daily_orders from RAW.ORDERS and RAW.CUSTOMERS",
        "description": (
            "Create a gold-layer fact model `fct_daily_orders` at daily grain. "
            "Include daily_revenue (sum of order_amount) and order_count by customer_segment. "
            "Add not_null + unique tests and open a PR."
        ),
    }, timeout=10)

    if resp.status_code != 200:
        print(f"[seed_tenant] ERROR creating ticket: {resp.status_code} {resp.text}")
        sys.exit(1)

    tdata = resp.json()
    ticket_id = tdata["ticket_id"]
    ticket_wf_id = tdata["workflow_run_id"]
    print(f"[seed_tenant] ticket_id       : {ticket_id}")
    print(f"[seed_tenant] ticket wf_run_id: {ticket_wf_id}")
    print()

    # --- Step 4: Poll ticket workflow ---
    wf = poll_workflow(ticket_wf_id, TIMEOUT, "ticket")
    print()

    if not AUTO_APPROVE_GATES and wf.get("status") != "succeeded":
        print(f"[seed_tenant] Workflow paused at gate (AUTO_APPROVE_GATES=false). Approve manually.")
        print(f"[seed_tenant] Current state: {wf.get('current_state')}  status: {wf.get('status')}")
        print("[seed_tenant] Done (partial).")
        return

    if wf.get("status") != "succeeded":
        print(f"[seed_tenant] FAILED — ticket workflow ended status={wf.get('status')}")
        events = wf.get("events", [])
        for ev in events[-5:]:
            print(f"       seq={ev.get('seq')} type={ev.get('event_type')} msg={ev.get('message')}")
        sys.exit(1)

    print("[seed_tenant] Ticket workflow SUCCEEDED")
    print()

    # --- Step 5: Artefact listing ---
    print("=" * 60)
    print("Tenant workspace artefacts")
    print("=" * 60)

    tenant_detail = requests.get(f"{API_BASE}/tenants/{tenant_id}", timeout=10).json()

    bootstrap_dirs = list(WORKSPACES_ROOT.glob(f"tenants/{tenant_id}/**/bootstrap"))
    for bd in bootstrap_dirs:
        print(f"\nBootstrap dir: {bd}")
        for p in sorted(bd.rglob("*")):
            if p.is_file():
                print(f"  {p.relative_to(bd)}  ({p.stat().st_size} bytes)")

    ticket_dirs = list(WORKSPACES_ROOT.glob(f"tenants/{tenant_id}/tickets/{ticket_id}/runs/*"))
    if ticket_dirs:
        workspace = ticket_dirs[0]
        print(f"\nTicket workspace: {workspace}")
        for p in sorted(workspace.rglob("*")):
            if p.is_file():
                print(f"  {p.relative_to(workspace)}  ({p.stat().st_size} bytes)")

    db_files = list(WORKSPACES_ROOT.glob(f"tenants/{tenant_id}/**/factoria.duckdb"))
    if db_files:
        print(f"\n[seed_tenant] DuckDB confirmed: {db_files[0]}")
    else:
        print("\n[seed_tenant] WARNING: factoria.duckdb not found")

    print()
    print("[seed_tenant] Done.")


if __name__ == "__main__":
    main()
