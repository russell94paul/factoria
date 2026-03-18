"""
dev_seed_ticket_data.py — Smoke-test script for Milestone 5.

Creates a ticket with structured requirements, uploads two CSVs,
then optionally polls the workflow to DONE and prints a data preview
and artefact listing.

Usage (from repo root, with API running on localhost:8000):
    python -m app.scripts.dev_seed_ticket_data

Flags:
    --skip-ticket       Create the ticket and upload files, then stop.
                        Does not poll the workflow.

Environment variables:
    API_BASE            API base URL (default: http://localhost:8000)
    WORKSPACES_ROOT     Path to workspace root (default: ./workspace)
    AUTO_APPROVE_GATES  Set to "false" to log gate states without auto-approving.
                        Defaults to "true" so CI stays stable.
"""

import csv
import io
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
POLL_INTERVAL = 2
TIMEOUT = 240
WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "./workspace"))

AUTO_APPROVE_GATES = os.getenv("AUTO_APPROVE_GATES", "true").lower() not in ("false", "0", "no")

GATED_STATES = {"DESIGN_REVIEW", "READY_FOR_REVIEW"}
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


# ---------------------------------------------------------------------------
# Minimal CSV fixtures (generated in-memory)
# ---------------------------------------------------------------------------

def _make_sales_csv() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["sale_id", "product_id", "sale_date", "amount", "region"])
    for i in range(1, 51):
        w.writerow([
            f"S{i:04d}",
            f"P{(i % 10) + 1:02d}",
            f"2024-{((i % 12) + 1):02d}-{((i % 28) + 1):02d}",
            round(10.0 + (i * 7.3) % 490, 2),
            ["North", "South", "East", "West"][i % 4],
        ])
    return buf.getvalue().encode()


def _make_products_csv() -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["product_id", "product_name", "category", "unit_price"])
    products = [
        ("P01", "Widget A", "Hardware", 29.99),
        ("P02", "Widget B", "Hardware", 49.99),
        ("P03", "Gadget X", "Electronics", 99.99),
        ("P04", "Gadget Y", "Electronics", 149.99),
        ("P05", "Service P", "Software", 19.99),
        ("P06", "Service Q", "Software", 39.99),
        ("P07", "Tool Alpha", "Tools", 24.99),
        ("P08", "Tool Beta", "Tools", 44.99),
        ("P09", "Part One", "Parts", 9.99),
        ("P10", "Part Two", "Parts", 14.99),
    ]
    for pid, pname, cat, price in products:
        w.writerow([pid, pname, cat, price])
    return buf.getvalue().encode()


def main():
    skip_ticket = "--skip-ticket" in sys.argv

    print(f"[seed_data] API: {API_BASE}")
    print(f"[seed_data] AUTO_APPROVE_GATES: {AUTO_APPROVE_GATES}")
    print(f"[seed_data] skip_ticket: {skip_ticket}")
    print()

    # --- Step 1: Create ticket with requirements ---
    resp = requests.post(f"{API_BASE}/tickets", json={
        "ticket_kind": "DATA_ENGINEERING",
        "title": "Sales Performance Summary by Region and Category",
        "description": (
            "Build a gold-layer model aggregating sales revenue and volume "
            "by region and product category from the uploaded source files."
        ),
        "grain": "one row per region per product category per month",
        "metrics": [
            "total_revenue: sum of amount",
            "order_count: count of sale_id",
            "avg_order_value: avg of amount",
        ],
        "constraints": [
            "Exclude refunds (amount < 0)",
            "Include only 2024 data",
        ],
    }, timeout=10)

    if resp.status_code != 200:
        print(f"[seed_data] ERROR creating ticket: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    ticket_id = data["ticket_id"]
    workflow_run_id = data["workflow_run_id"]
    print(f"[seed_data] ticket_id       : {ticket_id}")
    print(f"[seed_data] workflow_run_id : {workflow_run_id}")
    print()

    # --- Step 2: Upload CSVs ---
    print("[seed_data] Uploading sales.csv …")
    up1 = requests.post(
        f"{API_BASE}/tickets/{ticket_id}/uploads",
        files={"file": ("sales.csv", _make_sales_csv(), "text/csv")},
        timeout=15,
    )
    if up1.status_code != 200:
        print(f"[seed_data] ERROR uploading sales.csv: {up1.status_code} {up1.text}")
        sys.exit(1)
    print(f"[seed_data] -> file_id: {up1.json()['file_id']}  size: {up1.json()['size_bytes']} bytes")

    print("[seed_data] Uploading products.csv …")
    up2 = requests.post(
        f"{API_BASE}/tickets/{ticket_id}/uploads",
        files={"file": ("products.csv", _make_products_csv(), "text/csv")},
        timeout=15,
    )
    if up2.status_code != 200:
        print(f"[seed_data] ERROR uploading products.csv: {up2.status_code} {up2.text}")
        sys.exit(1)
    print(f"[seed_data] -> file_id: {up2.json()['file_id']}  size: {up2.json()['size_bytes']} bytes")
    print()

    if skip_ticket:
        print("[seed_data] --skip-ticket set — stopping after uploads.")
        print(f"[seed_data] ticket_id: {ticket_id}")
        print(f"[seed_data] Verify uploads: GET {API_BASE}/tickets/{ticket_id}/uploads")
        print("[seed_data] Done (partial).")
        return

    # --- Step 3: Poll workflow ---
    deadline = time.time() + TIMEOUT
    approved_gates: set[str] = set()
    wf: dict = {}

    while time.time() < deadline:
        resp = requests.get(f"{API_BASE}/workflows/{workflow_run_id}", timeout=10)
        if resp.status_code != 200:
            print(f"[seed_data] ERROR polling workflow: {resp.status_code}")
            time.sleep(POLL_INTERVAL)
            continue

        wf = resp.json()
        state = wf.get("current_state", "?")
        status = wf.get("status", "?")
        print(f"[seed_data] state={state:<25} status={status}")

        if state in GATED_STATES and state not in approved_gates:
            if AUTO_APPROVE_GATES:
                print(f"[seed_data] approving gate: {state}")
                gate_resp = requests.post(
                    f"{API_BASE}/workflows/{workflow_run_id}/gates/{state}/approve",
                    timeout=10,
                )
                if gate_resp.status_code == 200:
                    approved_gates.add(state)
                    print(f"[seed_data] gate approved -> {gate_resp.json().get('state')}")
            else:
                print(f"[seed_data] gate {state} waiting — AUTO_APPROVE_GATES=false, approve manually")

        if status in TERMINAL_STATUSES:
            break

        time.sleep(POLL_INTERVAL)
    else:
        print(f"\n[seed_data] TIMEOUT after {TIMEOUT}s")
        sys.exit(1)

    print()

    if not AUTO_APPROVE_GATES and wf.get("status") != "succeeded":
        print(f"[seed_data] Workflow paused (AUTO_APPROVE_GATES=false). state={wf.get('current_state')}")
        print("[seed_data] Done (partial).")
        return

    if wf.get("status") != "succeeded":
        print(f"[seed_data] FAILED — status={wf.get('status')}")
        events = wf.get("events", [])
        for ev in events[-5:]:
            print(f"       seq={ev.get('seq')} type={ev.get('event_type')} msg={ev.get('message')}")
        sys.exit(1)

    print("[seed_data] Workflow SUCCEEDED")
    print()

    # --- Step 4: Data preview ---
    print("=" * 60)
    print("Data Preview — RAW.SALES")
    print("=" * 60)
    preview_resp = requests.get(
        f"{API_BASE}/tickets/{ticket_id}/data-preview?table=SALES",
        timeout=15,
    )
    if preview_resp.status_code == 200:
        preview = preview_resp.json()
        cols = preview.get("columns", [])
        rows = preview.get("rows", [])
        print(" | ".join(cols))
        print("-" * 60)
        for row in rows[:5]:
            print(" | ".join(str(row.get(c, "")) for c in cols))
        print(f"  … {len(rows)} rows total (showing 5)")
    else:
        print(f"[seed_data] preview unavailable: {preview_resp.status_code}")
    print()

    # --- Step 5: Upload schemas ---
    print("=" * 60)
    print("Uploaded File Schemas")
    print("=" * 60)
    uploads_resp = requests.get(f"{API_BASE}/tickets/{ticket_id}/uploads", timeout=10)
    if uploads_resp.status_code == 200:
        for f in uploads_resp.json():
            print(f"\n  {f['filename']} ({f['size_bytes']:,} bytes)")
            if f.get("schema_json"):
                for col in f["schema_json"]:
                    print(f"    {col['name']}: {col['type']}")
            else:
                print("    (schema pending ingestion)")
    print()

    # --- Step 6: Artefact listing ---
    print("=" * 60)
    print("Workspace Artefacts")
    print("=" * 60)
    run_dirs = list(WORKSPACES_ROOT.glob(f"tenants/*/tickets/{ticket_id}/runs/{workflow_run_id}"))
    if not run_dirs:
        run_dirs = list(WORKSPACES_ROOT.glob(f"tenants/*/tickets/{ticket_id}/runs/*"))

    if run_dirs:
        ws = run_dirs[0]
        print(f"Run workspace: {ws}")
        for p in sorted(ws.rglob("*")):
            if p.is_file():
                print(f"  {p.relative_to(ws)}  ({p.stat().st_size:,} bytes)")

    catalogs = list(WORKSPACES_ROOT.glob(f"tenants/*/tickets/{ticket_id}/duckdb/catalog.duckdb"))
    if catalogs:
        print(f"\n[seed_data] catalog.duckdb confirmed: {catalogs[0]}")
    else:
        print("\n[seed_data] WARNING: catalog.duckdb not found")

    print()
    print("[seed_data] Done.")


if __name__ == "__main__":
    main()
