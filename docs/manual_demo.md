# Factoria — Manual Demo Runbook

This guide walks through a full end-to-end demo using the marketing RAW source dataset.
The operator uploads five un-modeled CSV files; the agent workflow derives the star schema
(dim_customer, dim_campaign, fct_orders, fct_campaign_performance, fct_web_sessions),
generates dbt models + tests, runs QA, and opens a mock PR.

Estimated time: ~10 minutes for the full flow.

---

## 1. Start the Stack

```bash
# From repo root — delete the database first to get a clean schema
rm -f workspace/factoria.db

docker compose up --build
```

Wait for all four services to log `ready`:
- `api` → `Application startup complete`
- `runner` → `Application startup complete`
- `worker` → `Agent worker started`
- `web` → `Ready on http://localhost:3000`

Open **http://localhost:3000** in the browser.

---

## 2. (Optional) Provision a Tenant First

If you want a named tenant rather than the default workspace:

```bash
curl -s -X POST http://localhost:8000/tenants \
  -H "Content-Type: application/json" \
  -d '{"tenant_key": "acme_demo", "name": "ACME Demo Tenant"}' | jq .
```

Poll until `"status": "ready"`:
```bash
curl -s http://localhost:8000/tenants | jq '.[0] | {status, workspace_root}'
```

---

## 3. Prepare the Demo Data Zip

```bash
python scripts/prepare_demo_zip.py
# -> dist/raw_marketing_data.zip  (~12 KB, 5 RAW CSVs + README)
```

The zip contains five **raw source files** — not pre-modeled dims/facts. The agents derive the star schema from these inputs.

---

## 4. Create a Ticket via the UI

Click **+ New Ticket** on the Kanban board.

Fill in:

| Field | Value |
|---|---|
| **Title** | `Marketing ROI — Revenue and Conversions by Campaign and Channel` |
| **Description** | `From five raw source tables, build a gold-layer star schema: deduplicate customers, aggregate campaign spend, join orders to sessions, and compute attributed revenue, conversion rate, and ROI per campaign per month.` |
| **Grain** | `one row per campaign per channel per month` |
| **Metrics** (one per line) | `attributed_revenue: sum of raw_orders.amount_usd where campaign_id matches, excluding refunds and cancellations` *(newline)* `session_count: count of raw_web_sessions` *(newline)* `conversion_rate: sum(converted) / count(session_id)` *(newline)* `campaign_roi: attributed_revenue / sum(raw_campaign_spend.spend_usd) per campaign` |
| **Constraints** (one per line) | `Exclude cancelled and returned orders` *(newline)* `Deduplicate raw_customers by customer_email — keep the row with the latest signup_ts` *(newline)* `Only include sessions from 2023-01-01 onwards` *(newline)* `Attribute revenue to a campaign only when raw_orders.campaign_id is not null` |

Drag-and-drop the RAW CSV files **in this order**:
1. `raw_customers.csv`
2. `raw_campaign_spend.csv`
3. `raw_orders.csv`
4. `raw_order_items.csv`
5. `raw_web_sessions.csv`

Click **Create Ticket**. The files are uploaded immediately; the ticket appears in the `DATA_INGESTION` column.

### Equivalent via API (JSON snippet)

```bash
# Step 1 — create the ticket
TICKET=$(curl -s -X POST http://localhost:8000/tickets \
  -H "Content-Type: application/json" \
  -d '{
    "ticket_kind": "DATA_ENGINEERING",
    "title": "Marketing ROI — Revenue and Conversions by Campaign and Channel",
    "description": "From five raw source tables, build a gold-layer star schema.",
    "grain": "one row per campaign per channel per month",
    "metrics": [
      "attributed_revenue: sum of raw_orders.amount_usd where campaign_id matches, excluding refunds and cancellations",
      "session_count: count of raw_web_sessions",
      "conversion_rate: sum(converted) / count(session_id)",
      "campaign_roi: attributed_revenue / sum(raw_campaign_spend.spend_usd) per campaign"
    ],
    "constraints": [
      "Exclude cancelled and returned orders (status IN (cancelled, returned))",
      "Deduplicate raw_customers by customer_email — keep the row with the latest signup_ts",
      "Only include sessions from 2023-01-01 onwards",
      "Attribute revenue to a campaign only when raw_orders.campaign_id is not null"
    ]
  }')
echo $TICKET | jq .
TICKET_ID=$(echo $TICKET | jq -r .ticket_id)

# Step 2 — upload files (in order)
for f in demo_data/raw_marketing_data/raw_customers.csv \
          demo_data/raw_marketing_data/raw_campaign_spend.csv \
          demo_data/raw_marketing_data/raw_orders.csv \
          demo_data/raw_marketing_data/raw_order_items.csv \
          demo_data/raw_marketing_data/raw_web_sessions.csv; do
  echo "Uploading $f ..."
  curl -s -X POST "http://localhost:8000/tickets/$TICKET_ID/uploads" \
    -F "file=@$f" | jq '{file_id, filename, size_bytes}'
done
```

---

## 5. Watch DATA_INGESTION

In the browser the ticket card shows `DATA_INGESTION`. The worker is:
- Loading each RAW CSV into `catalog.duckdb` as `RAW.RAW_CUSTOMERS`, `RAW.RAW_ORDERS`, etc.
- Inferring column schemas (types, null counts)
- Writing `docs/requirements.md` and `outputs/data_dictionary.json`

**Demo talking point:** *"The agent automatically discovered the schema of each raw file — including the duplicate customer emails and nullable join keys — and will use those real column names and quirks when designing the star schema."*

### Verify ingestion via API

```bash
# List uploaded files with inferred schemas
curl -s "http://localhost:8000/tickets/$TICKET_ID/uploads" | jq '.[] | {filename, schema_json}'

# Preview 20 rows from RAW_ORDERS
curl -s "http://localhost:8000/tickets/$TICKET_ID/data-preview?table=RAW_ORDERS" | jq '{columns, rows: (.rows | length)}'
```

Or click the ticket card → **Data** tab → **Preview** button next to any file.

---

## 6. Progress Through the Workflow

After `DATA_INGESTION` the card moves automatically to `TICKET_INTAKE` and continues through `DESIGN_REVIEW`.

### Gate 1: DESIGN_REVIEW

The card will show an **Approve →** button.

**Demo talking point:** *"The DesignAgent read the raw schemas and the requirements, identified the deduplication problem in raw_customers, and proposed the five derived models. Click Artifacts to show design.md before approving."*

Click **Artifacts** tab → open `design.md` → walk through:
- Deduplication logic for `dim_customer`
- Daily → campaign-level aggregation for `dim_campaign`
- Join strategy for `fct_orders` and `fct_campaign_performance`

Click **Approve →**.

The card moves to `PROFILING`. The profiler queries the real uploaded data in `catalog.duckdb` — row counts, null rates, and cardinality will reflect the actual RAW files.

### Profiling → Build → QA

These run automatically. Watch the card progress in real time (board auto-refreshes every 3 s).

**Demo talking point during BUILD:** *"The dbt model SQL is generated using the actual column names inferred at ingestion time — including the deduplication CTE for dim_customer and the campaign spend aggregation."*

### Gate 2: READY_FOR_REVIEW

Open `docs/qa_report.md` in Artifacts to show dbt test results (not_null + unique on all dim PKs, referential integrity on fct_orders), then Approve.

The card moves to `PR_CREATION` → `DONE`.

---

## 7. Inspect Final Artefacts

Click the `DONE` ticket → **Artifacts** tab. Point out:
- `docs/requirements.md` — structured requirements + raw table schemas captured at intake
- `outputs/data_dictionary.json` — column stats (null rates, cardinality) from real RAW data
- `docs/design.md` — star schema design: 2 dims + 3 fcts, deduplication rationale
- `outputs/profile_report.json` — real row counts from catalog (note: raw_customers has 110 rows → dim_customer ~80 after dedup)
- `outputs/run_results.json` — dbt test pass/fail counts
- `docs/pr_summary.md` — mock PR with branch and commit SHA

---

## 8. Reset for the Next Demo Run

```bash
# Stop, wipe workspace and DB, restart
docker compose down
rm -rf workspace/tenants workspace/factoria.db
docker compose up
```

Or if you provisioned a named tenant:
```bash
curl -s -X POST http://localhost:8000/tenants/acme_demo/reset | jq .
```

---

## Smoke Scripts Reference

| Script | Purpose |
|---|---|
| `python -m app.scripts.dev_seed_tenant` | Full automated run: provision tenant + ticket workflow |
| `python -m app.scripts.dev_seed_ticket_data` | Full automated run: create ticket, upload 2 sample CSVs, poll to DONE |
| `AUTO_APPROVE_GATES=false python -m app.scripts.dev_seed_ticket_data` | Upload files only — stops at gates, does not auto-approve |
| `AUTO_APPROVE_GATES=false python -m app.scripts.dev_seed_tenant --skip-ticket` | Provision tenant only — no ticket workflow |
| `python scripts/prepare_demo_zip.py` | Package RAW CSVs into `dist/raw_marketing_data.zip` |

> **Note:** `dev_seed_ticket_data.py` uploads its own small in-memory CSVs (sales/products), not the marketing dataset. For the full marketing demo use the UI or the API snippet above.
