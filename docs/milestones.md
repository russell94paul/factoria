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
Status: planned

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

