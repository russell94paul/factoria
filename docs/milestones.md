# Factoria Milestones

Use this log to capture Claude’s plan and progress. Fill in each block as milestones are proposed/approved/completed.

## Milestone Template
Milestone N: <name>
Owner: Claude Code
Scope:
Success criteria:
Dependencies:
Artifacts to touch:
Runner jobs:
Status: planned / in-progress / done
Notes:

---

## Milestone 1: Agent Loop to Real Artefacts

Owner: Claude Code
Status: done
Notes: Smoke run via dev_seed.py passed; artefacts listed in run output.

### Scope

Replace every stub/placeholder in the agent execution surface with real behaviour so that a single ticket run progresses from `TICKET_INTAKE` to `DONE` end-to-end, each workflow state writes its canonical workspace artefact, runner jobs carry meaningful payloads, and `workflow_events` captures real evidence (not placeholder strings).

No UI changes, no new workflow states, no schema changes — the goal is to make the existing plumbing produce real output.

### Success Criteria

1. **Each state writes the correct artefact** into the ticket workspace under `workspaces/tenants/<tenant>/tickets/<ticket>/`:
   - `TICKET_INTAKE` → `docs/intake_summary.md`
   - `DESIGN_REVIEW` → `docs/design.md` (+ optionally `outputs/design_spec.json`)
   - `PROFILING` → `outputs/profile_report.json` + `docs/profiling.md`
   - `BUILD` → `dbt_changes/models/**`, `dbt_changes/tests/schema.yml`, `outputs/compile_summary.json`
   - `QA` → `outputs/run_results.json` + `docs/qa_report.md`
   - `PR_CREATION` → `docs/pr_summary.md` (with PR URL, even if mocked)

2. **Runner jobs fire with meaningful payloads** at the correct states:
   - `PROFILING`: `snowflake_sql` job(s) with real query payloads
   - `BUILD`: `workspace_write_files` job (bounded to `dbt_changes/`) + `dbt_compile` job with orchestrator-computed selection set
   - `QA`: `dbt_build` job with orchestrator-computed `--select` scope (never unconstrained)
   - `PR_CREATION`: `git_commit_push` + `gh_create_pr` jobs (mocked credentials acceptable for now)

3. **Orchestrator events reflect reality**: `workflow_events` rows for each state capture `state_transition`, `agent_completed`, and `artifact_created` event types with `payload_json` referencing real artefact IDs and runner job IDs — not placeholder values.

4. **Artefacts registered via `ArtifactService`**: every artefact written to the workspace has a corresponding `artifacts` DB row so the web layer can surface it without code changes.

5. **Smoke run succeeds**: running `python api/app/scripts/dev_seed.py` (or equivalent) creates a ticket, starts the workflow, and the ticket reaches `DONE` without manual DB edits. State transitions are observable in `workflow_events`.

### Dependencies

- `docs/agent_operating_model.md` — canonical artefact names, locations, and tool allowlists per agent (read before touching any agent code)
- `api/app/services/agent_runner.py` — primary implementation target; replace placeholder logic with real prompts + runner orchestration
- `api/app/services/openclaw_service.py` — implement real Claude session calls with ticket/workspace context
- `api/app/services/runner_client.py` + `runner_job_service.py` — flesh out payloads and job logging for `snowflake_sql`, `workspace_write_files`, `dbt_compile`, `dbt_build`, `git_commit_push`, `gh_create_pr`
- `api/app/services/artifact_service.py` — ensure all new artefacts register with correct `artifact_type`, `artifact_role`, `file_path`, and `checksum_sha256`
- `api/app/workflows/ticket_to_pr.py` — `WORKFLOW_GRAPH` and `STATE_AGENT_MAP` must stay intact; orchestrator selection-set logic added here

### Artefacts to Touch (code files)

| File | Change |
|---|---|
| `api/app/services/agent_runner.py` | Replace stubs with per-state prompts, artefact writers, and runner job calls |
| `api/app/services/openclaw_service.py` | Implement real `start_agent` call with ticket JSON + prior artefacts + workspace paths as context |
| `api/app/services/runner_client.py` | Add/flesh out methods for all 6 job types with correct request/response schemas |
| `api/app/services/runner_job_service.py` | Ensure job IDs are logged and `runner_jobs` rows are created per submission |
| `api/app/services/artifact_service.py` | Confirm `register_artifact` writes all required fields; add any missing artefact type constants |
| `api/app/services/orchestrator.py` | Add selection-set computation; ensure `mark_agent_complete` checks for artefact existence before advancing |
| `api/app/scripts/dev_seed.py` | Create or update to seed a ticket and kick the workflow; print artefact paths on completion |

### Runner Jobs Required

| Job type | Triggered at state | Payload must include |
|---|---|---|
| `snowflake_sql` | `PROFILING` | `connection`, `query` (real profiling SQL), `workspace` |
| `workspace_write_files` | `BUILD` | `files` list with `path`/`content`/`sha256`, bounded to `dbt_changes/` |
| `dbt_compile` | `BUILD` | `workspace`, `select` (orchestrator-computed), `target` |
| `dbt_build` | `QA` | `workspace`, `select` (orchestrator-computed, never unconstrained), `target` |
| `git_commit_push` | `PR_CREATION` | `workspace`, `branch`, `commit_message`, `files` |
| `gh_create_pr` | `PR_CREATION` | `repo`, `branch`, `title`, `body` (QA evidence summary) |

### Guardrails

- No shell commands from FastAPI or agents — all execution via `RunnerClient`.
- `workspace_write_files` writes only under allowed subpaths (`docs/`, `outputs/`, `logs/`, `dbt_changes/`) using `WORKSPACES_ROOT` + `workspace_rel` helpers.
- Runner jobs are idempotent; repeated profiling/builds must not corrupt workspaces; all jobs are logged via `RunnerJobService`.
- Artefact file names and locations must match the table in `docs/agent_operating_model.md` exactly.
- `dbt_build` must always include a `--select` scope; unconstrained builds are forbidden.

### Suggested Task Order

1. **Prompt + context plumbing** — implement `OpenClawClient.start_agent` with real ticket/workspace context per state; define per-agent system prompts referencing the artefact contracts.
2. **Artefact writers per state** — wire each agent’s output into the correct workspace path and call `ArtifactService.register_artifact`.
3. **Runner job integration** — flesh out `RunnerClient` methods for all 6 job types; add request/response schemas and error handling.
4. **State advancement + gating** — `orchestrator.mark_agent_complete` validates artefact presence before transition; add selection-set computation for BUILD/QA.
5. **Smoke automation** — `dev_seed.py` creates a ticket and runs the workflow; prints artefact directory listing on completion.

### Acceptance Evidence

- [ ] Screenshot or log of a ticket moving through all states with artefact links populated.
- [ ] Artefact directory listing under `workspaces/tenants/<tenant>/tickets/<ticket>/docs|outputs|dbt_changes` showing all 10 canonical files.
- [ ] `runner_jobs` table rows for `snowflake_sql`, `dbt_compile`, `dbt_build`, `git_commit_push`, `gh_create_pr` with non-placeholder `request_payload_json`.
- [ ] `workflow_events` rows for each state transition and agent completion with real `artifact_id` references in `payload_json`.
- [ ] `dev_seed.py` (or equivalent) exits 0 and prints workspace artefact paths.

### Notes

- Mocked Snowflake/GitHub credentials are acceptable for Milestone 1; the runner job payloads just need to be structurally correct and logged.
- Human approval gates (`DESIGN_REVIEW`, `READY_FOR_REVIEW`) can be bypassed in the dev seed script via a direct orchestrator call — the gate logic itself should not be removed.
- Do not start on UI polish (Milestone 2) or live credential wiring (Milestone 3) until this milestone’s acceptance evidence is checked off.

---

## Milestone 2: Surface Artefacts in the Next.js UI

Owner: Claude Code
Status: done

### Scope

Scaffold a Next.js application in `web/` and build three views that make the Milestone 1 artefact pipeline visible to a human reviewer without touching the terminal:

1. **Kanban board** — tickets as cards in columns matching workflow states; gate approval buttons inline.
2. **Ticket detail drawer** — artefact viewer (Markdown + JSON rendered), agent timeline (state transitions + agent sessions), and runner job list.
3. **Create-ticket form** — minimal form to create a new ticket and watch it run.

The backend API already has the necessary endpoints for most of this; a small number of new read-only endpoints must be added to serve artefact content and agent session data.

No new workflow states, no schema changes, no Snowflake/GitHub credential wiring — all data comes from the existing SQLite DB and workspace files written by Milestone 1.

### Success Criteria

1. **Kanban board renders** all tickets grouped by `state` in the correct column order (`TICKET_INTAKE → DESIGN_REVIEW → PROFILING → BUILD → QA → READY_FOR_REVIEW → PR_CREATION → DONE`). Cards show ticket title, state, and elapsed time.
2. **Gate approval works from the UI** — clicking "Approve" on a `DESIGN_REVIEW` or `READY_FOR_REVIEW` card calls the existing `POST /workflows/{id}/gates/{gate}/approve` endpoint and the card moves to the next column without a page reload.
3. **Ticket drawer opens** on card click and shows:
   - All artefacts for the run, grouped by role (design_doc, profiling_report, dbt_model, qa_evidence, pr_summary).
   - Artefact content rendered in-page: Markdown files as HTML, JSON files as formatted code blocks.
   - Agent timeline: ordered list of `workflow_events` rows (state transitions + agent_completed + artifact_created) with timestamps.
4. **Create-ticket form** submits to `POST /tickets` and the new card appears on the board.
5. **Board auto-refreshes** (polling every 3 s is acceptable; WebSocket is a stretch goal) so a running `dev_seed.py` smoke run is visible as cards moving across the board in real time.
6. **PR link is clickable** on `DONE`/`PR_CREATION` cards that have a `docs/pr_summary.md` artefact containing a PR URL.

### Dependencies

**New API endpoints required (read-only):**

| Endpoint | Purpose |
|---|---|
| `GET /tickets/{id}/artifacts` | List all `Artifact` rows for the ticket’s current run |
| `GET /artifacts/{id}/content` | Serve the raw file content of an artefact from the workspace volume |
| `GET /workflows/{id}/sessions` | List `AgentSession` rows for a run (for timeline) |

**Existing endpoints consumed as-is:**

| Endpoint | Used for |
|---|---|
| `GET /tickets` | Kanban board initial load |
| `GET /tickets/{id}` | Ticket detail |
| `GET /workflows/{id}` | Workflow state + full event log |
| `POST /tickets` | Create-ticket form |
| `POST /workflows/{id}/gates/{gate}/approve` | Gate approval buttons |

**Frontend stack** (to be scaffolded in `web/`):
- Next.js 14 (App Router) with TypeScript
- Tailwind CSS for layout/styling
- `react-markdown` for rendering Markdown artefacts
- No additional state-management library needed at this scope

### Artefacts / Files to Touch

| Location | Change |
|---|---|
| `web/` | Scaffold new Next.js app (currently empty directory) |
| `web/src/app/page.tsx` | Kanban board root page |
| `web/src/app/tickets/[id]/page.tsx` | Ticket detail / drawer page |
| `web/src/lib/api.ts` | Typed fetch helpers for all consumed endpoints |
| `web/src/components/KanbanBoard.tsx` | Column + card layout |
| `web/src/components/TicketCard.tsx` | Individual card with state badge + gate button |
| `web/src/components/TicketDrawer.tsx` | Slide-over panel: artefact viewer + timeline tabs |
| `web/src/components/ArtifactViewer.tsx` | Renders Markdown or JSON artefact content |
| `web/src/components/AgentTimeline.tsx` | Ordered list of workflow events |
| `api/app/routes/artifacts.py` | New route: list artefacts + serve content |
| `api/app/routes/sessions.py` | New route: list agent sessions per run |
| `api/app/main.py` | Register two new routers |

### Suggested Task Order

1. **Add two new API routes** (`artifacts.py`, `sessions.py`) and register them — needed before any frontend work can be tested end-to-end.
2. **Scaffold Next.js app** in `web/` (`npx create-next-app@14 --typescript --tailwind --app --src-dir --no-eslint .`).
3. **Build `api.ts`** typed fetch helpers for all 7 endpoints.
4. **Kanban board** — `KanbanBoard` + `TicketCard` with polling; gate approval button wired.
5. **Ticket drawer** — `TicketDrawer` with two tabs: Artefacts (`ArtifactViewer`) and Timeline (`AgentTimeline`).
6. **Create-ticket form** — inline modal on the board page.
7. **Smoke walkthrough** — run `dev_seed.py` while the board is open; verify cards move and artefacts appear without manual refresh.

### Acceptance Evidence

- [ ] Screenshot of Kanban board showing a completed ticket in the `DONE` column.
- [ ] Screenshot of the ticket drawer open on a `DONE` ticket, artefact tab showing rendered `docs/design.md` and `docs/qa_report.md`.
- [ ] Screenshot of the timeline tab showing `state_transition` and `artifact_created` events in order.
- [ ] Screen recording (or written log) of a `dev_seed.py` run visible as live card movement on the board (polling).
- [ ] Gate approval flow: ticket at `DESIGN_REVIEW` → click Approve in UI → card moves to `PROFILING` without page reload.

### Notes

- `api` container mounts the workspace volume read-only; artefact content can be served directly from disk via `GET /artifacts/{id}/content` reading from `file_path` stored in the `Artifact` DB row.
- Do not implement WebSocket streaming in M2 — polling every 3 s is sufficient and keeps scope tight. WebSocket is listed as a stretch goal for M3/M4.
- Keep UI functional over polished — this is a hackathon demo, not a production product. A clean Tailwind layout is sufficient; avoid reaching for heavy component libraries.
- Do not touch `agent_runner.py`, `orchestrator.py`, or runner logic — M2 is read-only from the backend’s perspective (plus the two small new read-only routes).

---

## Milestone 3: Real Data Layer with DuckDB

Owner: Claude Code
Status: done
Notes: DuckDB integration verified; runner builds, compiles, and tests real SQL. Jinja stripping added in runner. BuilderAgent failure after DuckDB integration fixed (Jinja syntax stripped before DuckDB execution).

### Scope

Replace the mock `snowflake_sql` runner job with a real DuckDB-backed execution engine so that profiling, build, and QA operate on actual in-process data rather than hard-coded stub rows. DuckDB stands in for Snowflake throughout this milestone — the same SQL dialect, the same job interface, no real Snowflake credentials required.

A seed dataset (CSV or Parquet files) is loaded into a per-workspace DuckDB database at the start of each run. The profiling agent runs real SQL against that database and gets real results back. The build agent’s dbt model SQL is executed via DuckDB, producing a real output table. The QA agent runs `dbt build` against DuckDB and receives real pass/fail counts.

No changes to the workflow state machine, orchestrator, agent prompts, or UI. The runner job interface (`snowflake_sql`, `dbt_compile`, `dbt_build`) stays identical — only the handler implementations change inside `runner/app/main.py`.

### Success Criteria

1. **Seed data loads**: at run start, the runner creates (or re-uses) a DuckDB database at `<workspace>/db/factoria.duckdb` and loads seed tables (`RAW.ORDERS`, `RAW.CUSTOMERS`) from bundled CSV/Parquet fixtures.
2. **`snowflake_sql` executes real queries**: `handle_snowflake_sql` opens the workspace DuckDB database, runs the supplied SQL, and returns actual result rows — not mock values. Row counts, null rates, and distinct counts reflect the seed data.
3. **`dbt_compile` validates model SQL**: rather than writing a stub JSON, the handler parses the dbt model SQL from `dbt_changes/models/` and executes a `CREATE OR REPLACE VIEW` (or `CREATE TABLE AS SELECT`) in DuckDB to confirm the SQL is valid. Writes `outputs/compile_summary.json` with real node metadata.
4. **`dbt_build` materialises the model**: executes the full model SQL against DuckDB, materialises the output table, runs the schema tests from `dbt_changes/tests/schema.yml` (not-null and unique checks as SQL assertions), and writes `outputs/run_results.json` with real pass/fail counts per test.
5. **Profiling artefact contains real numbers**: `outputs/profile_report.json` and `docs/profiling.md` reflect the actual row counts, null rates, and distinct counts from the seed tables — not the hardcoded values from M1.
6. **QA artefact reflects real test results**: `docs/qa_report.md` quotes the actual test pass/fail counts from `run_results.json`.
7. **`dev_seed.py` smoke run succeeds end-to-end**: ticket reaches `DONE`, workspace contains a real `db/factoria.duckdb`, and `run_results.json` shows at least one test executed and passed.

### Dependencies

- `runner/app/main.py` — primary implementation target; replace `handle_snowflake_sql`, `handle_dbt_compile`, `handle_dbt_build` with DuckDB-backed implementations.
- `runner/app/fixtures/` (new) — seed CSV/Parquet files for `RAW.ORDERS` and `RAW.CUSTOMERS`; bundled with the runner Docker image.
- `runner/requirements.txt` (or `runner/app/requirements.txt`) — add `duckdb` dependency.
- `runner/Dockerfile` — no changes needed if `requirements.txt` is updated.
- `api/app/services/agent_runner.py` — no changes needed; profiling SQL queries and dbt_changes model files are already generated correctly in M1.
- `docs/agent_operating_model.md` — canonical artefact paths; must not be changed.

### Seed Dataset

| Table | Columns | Row count (approx.) |
|---|---|---|
| `RAW.ORDERS` | `order_id`, `customer_id`, `order_date`, `order_amount`, `customer_segment` | 500 rows |
| `RAW.CUSTOMERS` | `customer_id`, `customer_name`, `customer_segment`, `signup_date` | 100 rows |

Seed files live at `runner/app/fixtures/raw_orders.csv` and `runner/app/fixtures/raw_customers.csv`. The runner loads them into DuckDB schemas named `RAW` (uppercase) to match the SQL generated by the profiling and build agents.

### Files to Touch

| File | Change |
|---|---|
| `runner/app/main.py` | Replace `handle_snowflake_sql`, `handle_dbt_compile`, `handle_dbt_build` with DuckDB implementations; add `_get_or_create_db()` helper |
| `runner/app/fixtures/raw_orders.csv` | New: seed data for `RAW.ORDERS` |
| `runner/app/fixtures/raw_customers.csv` | New: seed data for `RAW.CUSTOMERS` |
| `runner/requirements.txt` | Add `duckdb` |

Files NOT touched: `agent_runner.py`, `orchestrator.py`, `workflow_events.py`, all API routes, all models, UI.

### Suggested Task Order

1. **Add `duckdb` to runner dependencies** and confirm the runner image builds.
2. **Create seed CSV fixtures** with realistic but minimal data (500 orders, 100 customers).
3. **Implement `_get_or_create_db(workspace)`** — opens `<workspace>/db/factoria.duckdb`, creates `RAW` schema, loads seed tables from fixtures if not already present.
4. **Replace `handle_snowflake_sql`** — call `_get_or_create_db`, execute the supplied SQL with `duckdb.connect`, return real rows in the existing result shape.
5. **Replace `handle_dbt_compile`** — read the model `.sql` file from `dbt_changes/models/`, execute `CREATE OR REPLACE VIEW` in DuckDB to validate, write `compile_summary.json` with real node info.
6. **Replace `handle_dbt_build`** — materialise the model as a table (`CREATE OR REPLACE TABLE … AS SELECT …`), run not-null and unique assertions from `schema.yml` as SQL, write `run_results.json` with real pass/fail counts.
7. **Smoke run** via `dev_seed.py` — verify `db/factoria.duckdb` exists in the workspace and `run_results.json` contains real row counts.

### Acceptance Evidence

- [ ] `runner/app/fixtures/` contains `raw_orders.csv` and `raw_customers.csv` with non-trivial data.
- [ ] `outputs/profile_report.json` contains real row counts and null rates matching the seed data (not the hardcoded `{"row_count": 10000}` stub).
- [ ] `db/factoria.duckdb` exists under the workspace after a smoke run.
- [ ] `outputs/run_results.json` shows at least one test result with `"status": "success"` and a real `rows_affected` count.
- [ ] `dev_seed.py` exits 0 and lists `db/factoria.duckdb` in the workspace artefact listing.
- [ ] Runner logs for the `snowflake_sql` job show the actual SQL executed and the real row count returned.

### Notes

- DuckDB is a drop-in replacement for Snowflake SQL for this scope — it supports the same analytical SQL dialect used by the profiling and build agents. No agent prompt changes are needed.
- The `dbt_compile` and `dbt_build` handlers do not invoke the real `dbt` CLI — they replicate the compile/build/test logic directly in Python using DuckDB. This keeps the runner dependency-light and avoids needing a dbt project scaffold.
- Schema tests (`not_null`, `unique`) are translated to SQL assertions: `SELECT COUNT(*) FROM model WHERE col IS NULL` for not-null, `SELECT COUNT(*) - COUNT(DISTINCT col) FROM model` for unique. A count > 0 is a failure.
- Do not start on live Snowflake credential wiring (Milestone 4) until this milestone’s acceptance evidence is checked off.

---

## Milestone 4: Tenant Provisioning + Resilient Workflow Engine

Owner: Claude Code
Status: in-progress

### Scope

1. **Tenant model + `TENANT_PROVISIONING` workflow** — create/reset a tenant from the API in seconds for hackathon demos.
2. **Structured error handling** — every failure path emits error events, populates `last_error`, marks workflows `failed`, offers retry without DB edits.
3. **`RunnerJob` table** — track every runner job with idempotency, retry chain, and status.

No changes to `ticket_to_pr` graph, existing agent handlers, or web/ frontend.

### Success Criteria

1. `POST /tenants` → tenant created, provisioning workflow starts, status moves `requested → provisioning_running → ready`.
2. `GET /tenants/{id}` shows `status`, `last_error`, `workspace_root`, and latest `workflow_run_id`.
3. **Failure path**: stop runner mid-provisioning → `status=error`, `last_error` populated → `POST /tenants/{id}/provision` → recovery to `ready`.
4. **Reset**: `POST /tenants/{id}/reset` → workspace archived → fresh provisioning run starts.
5. `GET /workflows/{failed_run_id}` → event stream contains `event_type="error"` + `severity="ERROR"` rows.
6. `SELECT * FROM runner_job` — populated rows for every job type executed.
7. `python -m app.scripts.dev_seed_tenant` exits 0, workspace listing includes `bootstrap/` files + `db/factoria.duckdb`.

### Files Touched

| File | Change |
|---|---|
| `api/app/models/tenant.py` | Implemented (was empty stub) |
| `api/app/models/runner_job.py` | Implemented (was empty stub) |
| `api/app/models/ticket.py` | Added `last_error` |
| `api/app/models/workflow_run.py` | Added `tenant_id`, `last_error`, `error_code` |
| `api/app/models/workflow_event.py` | Added `severity` |
| `api/app/db.py` | Imported + registered Tenant, RunnerJob |
| `api/app/workflows/tenant_provisioning.py` | New |
| `api/app/services/orchestrator.py` | Dynamic graph dispatch, `fail_workflow()` |
| `api/app/services/workflow_events.py` | Added `severity` param |
| `api/app/workers/agent_worker.py` | Fixed task failure handling |
| `api/app/services/agent_runner.py` | Error hardening, `_run_job_tracked()`, `TenantProvisioningAgent` |
| `api/app/routes/tenants.py` | New (5 endpoints) |
| `api/app/main.py` | Registered tenants router |
| `runner/app/main.py` | 4 new provisioning job handlers |
| `api/app/scripts/dev_seed_tenant.py` | New smoke script |

### Acceptance Evidence

- [ ] `rm /workspace/factoria.db && docker compose up --build` — all services start clean.
- [ ] `POST /tenants {"tenant_key":"retail_001","name":"Retail Demo"}` → `status: requested`.
- [ ] Poll `GET /tenants/{id}` — status moves `requested → provisioning_running → ready`.
- [ ] `GET /workflows/{run_id}` — event stream has `state_transition`, `artifact_created`, no `error` events.
- [ ] Failure + retry path verified.
- [ ] `POST /tenants/{id}/reset` → workspace archived → fresh provisioning run starts.
- [ ] `python -m app.scripts.dev_seed_tenant` exits 0.
- [ ] `GET /workflows/{failed_run_id}` → `event_type="error"` + `severity="ERROR"` rows present.
- [ ] `runner_job` table populated with rows for all 4 job types.

---

## Milestone 4: Tenant Provisioning + Resilient Workflow Engine — Status: done

Notes: All 16 files implemented. Tenant CRUD + provisioning workflow, fail_workflow(), RunnerJob tracking, TenantProvisioningAgent, 4 DuckDB-backed runner handlers.

---

## Milestone 5: Data & Requirements Intake (DuckDB-only)

Owner: Claude Code
Status: done

### Scope

Enable a ticket to carry structured requirements and uploaded source data (CSV/Parquet/JSON), ingest that data into a per-ticket DuckDB catalog, and feed all downstream agents (profiling, build, QA) from that catalog — entirely within DuckDB, no Snowflake calls.

### New Workflow State

`DATA_INGESTION` inserted before `TICKET_INTAKE`:
```
DATA_INGESTION → TICKET_INTAKE → DESIGN_REVIEW → PROFILING → BUILD → QA → READY_FOR_REVIEW → PR_CREATION → DONE
```

`DataIngestionAgent` runs `load_ticket_data` + `get_data_dictionary` runner jobs, writes `docs/requirements.md` + `outputs/data_dictionary.json`.

### Success Criteria

1. `POST /tickets` with `sources`, `grain`, `metrics`, `constraints` fields persists them on the ticket model.
2. `POST /tickets/{id}/uploads` accepts CSV/Parquet/JSON and stores files under `uploads/`.
3. After `DATA_INGESTION` completes, `catalog.duckdb` exists at `tenants/<tenant>/tickets/<ticket>/duckdb/catalog.duckdb`.
4. `GET /tickets/{id}/uploads` returns uploaded files with inferred `schema_json` (populated post-ingestion).
5. `GET /tickets/{id}/data-preview?table=X` returns ≤ 20 rows from the catalog.
6. `docs/requirements.md` and `outputs/data_dictionary.json` artefacts are registered.
7. `PROFILING` agent queries the ticket-level catalog (not a fresh per-run DuckDB).
8. Ticket drawer "data" tab shows uploaded files, schemas, and inline table preview.
9. `python -m app.scripts.dev_seed_ticket_data` exits 0, confirms catalog.duckdb + prints preview rows.

### Files Touched

| File | Change |
|---|---|
| `api/app/models/ticket.py` | Added `sources_json`, `grain`, `metrics_json`, `constraints_json` |
| `api/app/models/uploaded_file.py` | New model |
| `api/app/db.py` | Registered `UploadedFile` |
| `api/app/schemas/ticket_schema.py` | Extended with requirement fields |
| `api/app/services/workspace_manager.py` | Added `get_ticket_workspace`, `get_uploads_dir`, `get_catalog_path` |
| `api/app/workflows/ticket_to_pr.py` | Added `DATA_INGESTION` state + `DataIngestionAgent` |
| `api/app/routes/tickets.py` | Added upload/list/preview endpoints; ticket starts at DATA_INGESTION |
| `api/app/services/agent_runner.py` | `_run_data_ingestion`, `_build_profiling_queries`, catalog_path in profiling |
| `runner/app/main.py` | `load_ticket_data`, `get_data_dictionary`, `data_preview`; catalog_path in snowflake_sql |
| `web/src/lib/api.ts` | `UploadedFile`, `DataPreviewResult` types; upload/preview functions |
| `web/src/components/KanbanBoard.tsx` | Added `DATA_INGESTION` column |
| `web/src/components/TicketCard.tsx` | Added `DATA_INGESTION` color |
| `web/src/components/TicketDrawer.tsx` | Added "data" tab with schema + preview |
| `web/src/components/CreateTicketModal.tsx` | Requirements fields + drag-drop file upload |
| `api/app/scripts/dev_seed_ticket_data.py` | New smoke script |

### Acceptance Evidence

- [ ] `docker compose up --build` — all services start, `rm /workspace/factoria.db` first.
- [ ] Create ticket via UI with 2 CSVs attached — ticket appears in `DATA_INGESTION` column.
- [ ] Ticket moves to `TICKET_INTAKE` automatically after ingestion.
- [ ] Ticket drawer "data" tab shows files + schemas + preview rows.
- [ ] `outputs/data_dictionary.json` visible in artifacts tab.
- [ ] `python -m app.scripts.dev_seed_ticket_data` exits 0, prints preview rows, confirms catalog.duckdb.

---

## M6 — Demo Prep

**Status:** done

**Scope:** Reusable demo dataset bundle, manual demo runbook, seed script quality-of-life improvements.

**Dataset note:** The initial dataset used pre-modeled `dim_*/fact_*` CSVs. These were replaced with five **RAW source tables** (`raw_customers`, `raw_campaign_spend`, `raw_orders`, `raw_order_items`, `raw_web_sessions`) so the demo mirrors the real workflow: operator uploads un-modeled data, agents derive the star schema. The RAW tables include intentional quirks (duplicate customer emails, nullable join keys, daily-grain spend) that the DesignAgent should surface and handle.

### Deliverables

1. `demo_data/raw_marketing_data/` — 5 RAW CSVs (~744 rows total) + `README.md` with schema docs, quirks, derived-model targets, and suggested demo ticket JSON.
2. `scripts/prepare_demo_zip.py` — packages CSVs into `dist/raw_marketing_data.zip` (stdlib only).
3. `docs/manual_demo.md` — full step-by-step runbook: stack startup → ticket creation (UI + API) → gate approval → artefact inspection → demo reset; calls out derived models and talking points per stage.
4. `dev_seed_tenant.py` + `dev_seed_ticket_data.py` — `AUTO_APPROVE_GATES` env var (default `true`); `--skip-ticket` flag.
5. `dist/` added to `.gitignore`.

### Verification Commands

```bash
# Package RAW CSVs into a zip for hand-off
python scripts/prepare_demo_zip.py
# -> dist/raw_marketing_data.zip  (~12 KB, 5 RAW CSVs + README)

# Provision tenant only — no ticket workflow
cd api && AUTO_APPROVE_GATES=false python -m app.scripts.dev_seed_tenant --skip-ticket

# Create ticket + upload files, stop before polling (manual gate flow)
cd api && AUTO_APPROVE_GATES=false python -m app.scripts.dev_seed_ticket_data --skip-ticket
```

See `docs/manual_demo.md` for the full step-by-step demo runbook.

### Files Touched

| File | Change |
|---|---|
| `demo_data/raw_marketing_data/` | Renamed from `marketing_star_schema/`; 5 RAW source CSVs + updated README |
| `scripts/prepare_demo_zip.py` | Updated path/zip name to `raw_marketing_data` |
| `docs/manual_demo.md` | Updated for RAW upload flow and new bundle name |
| `runner/app/main.py` | `handle_load_ticket_data` strips `raw_` prefix: `raw_orders.csv` → `raw.ORDERS` |
| `api/app/services/agent_runner.py` | Stem matching updated to strip `RAW_` prefix; writes `outputs/raw_tables.json` |
| `web/src/components/CreateTicketModal.tsx` | Data viewer: collapsible per-file panels with schema + 20-row preview |
| `api/app/scripts/dev_seed_tenant.py` | `AUTO_APPROVE_GATES` env var + `--skip-ticket` flag |
| `api/app/scripts/dev_seed_ticket_data.py` | Same; unicode `->` fix for Windows |
| `.gitignore` | Added `dist/` |

