"""
dev_seed.py — Smoke-test script for Milestone 1.

Creates a ticket, polls the workflow to completion, auto-approves both
human gates, then prints the artefact listing.

Usage (from repo root, with API running on localhost:8000):
    python -m app.scripts.dev_seed

Or with a custom API base URL:
    API_BASE=http://localhost:8000 python -m app.scripts.dev_seed
"""

import os
import sys
import time
from pathlib import Path

import requests

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
POLL_INTERVAL = 2       # seconds between status checks
TIMEOUT = 180           # seconds before giving up
WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "./workspace"))

GATED_STATES = {"DESIGN_REVIEW", "READY_FOR_REVIEW"}
TERMINAL_STATES = {"succeeded", "failed", "cancelled"}


def main():
    print(f"[seed] API: {API_BASE}")

    # --- Create ticket ---
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
        print(f"[seed] ERROR creating ticket: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    ticket_id = data["ticket_id"]
    workflow_run_id = data["workflow_run_id"]
    print(f"[seed] ticket_id       : {ticket_id}")
    print(f"[seed] workflow_run_id : {workflow_run_id}")
    print()

    # --- Poll workflow ---
    deadline = time.time() + TIMEOUT
    approved_gates: set[str] = set()

    while time.time() < deadline:
        resp = requests.get(f"{API_BASE}/workflows/{workflow_run_id}", timeout=10)
        if resp.status_code != 200:
            print(f"[seed] ERROR polling workflow: {resp.status_code}")
            time.sleep(POLL_INTERVAL)
            continue

        wf = resp.json()
        current_state = wf.get("current_state", "?")
        status = wf.get("status", "?")

        print(f"[seed] state={current_state:<20} status={status}")

        # Auto-approve gates
        if current_state in GATED_STATES and current_state not in approved_gates:
            print(f"[seed] approving gate: {current_state}")
            gate_resp = requests.post(
                f"{API_BASE}/workflows/{workflow_run_id}/gates/{current_state}/approve",
                timeout=10,
            )
            if gate_resp.status_code == 200:
                approved_gates.add(current_state)
                print(f"[seed] gate approved -> {gate_resp.json().get('state')}")
            else:
                print(f"[seed] gate approval failed: {gate_resp.status_code} {gate_resp.text}")

        if status in TERMINAL_STATES:
            break

        time.sleep(POLL_INTERVAL)
    else:
        print(f"\n[seed] TIMEOUT after {TIMEOUT}s — last state={current_state} status={status}")
        sys.exit(1)

    print()

    if status != "succeeded":
        print(f"[seed] FAILED — workflow ended with status={status}")
        events = wf.get("events", [])
        for ev in events[-5:]:
            print(f"       seq={ev.get('seq')} type={ev.get('event_type')} msg={ev.get('message')}")
        sys.exit(1)

    print("[seed] Workflow SUCCEEDED")
    print()

    # --- Print artefact listing ---
    print("=" * 60)
    print("Artefact listing")
    print("=" * 60)

    # Try to find workspace directory
    workspace_dirs = list(WORKSPACES_ROOT.glob(f"tenants/*/tickets/{ticket_id}/runs/{workflow_run_id}"))
    if not workspace_dirs:
        # Fallback: search for any run dir for this ticket
        workspace_dirs = list(WORKSPACES_ROOT.glob(f"tenants/*/tickets/{ticket_id}/runs/*"))

    if not workspace_dirs:
        print(f"[seed] Workspace not found under {WORKSPACES_ROOT}")
        print("       (Run from repo root or set WORKSPACES_ROOT)")
    else:
        workspace = workspace_dirs[0]
        print(f"Workspace: {workspace}\n")
        for p in sorted(workspace.rglob("*")):
            if p.is_file():
                size = p.stat().st_size
                print(f"  {p.relative_to(workspace)}  ({size} bytes)")

    print()
    print("[seed] Done.")


if __name__ == "__main__":
    main()
