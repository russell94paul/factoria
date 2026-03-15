# Factoria Hackathon — Claude Bootstrap

## Current State Snapshot
- **Architecture + docs are locked in.** The runner-split design, workflow graph, and agent operating model live under `docs/` (read `AI_CONTEXT.md`, `agent_operating_model.md`, `design.md`, `system_data_model.md`).
- **Backend scaffolding exists.** FastAPI routes, models, and services are in `api/app/**`. The workflow graph + gate logic sit in `api/app/workflows/ticket_to_pr.py` and `api/app/services/orchestrator.py`.
- **Execution surface is stubbed.** `api/app/services/agent_runner.py` currently calls `OpenClawClient.start_agent(...)` and drops placeholder artefacts instead of real agent output. Runner jobs (`workspace_write_files`, `dbt_compile`, `dbt_build`, git/PR) are wired but intentionally minimal.
- **Gateway + runner clients exist** (`OpenClawClient`, `RunnerClient`, `RunnerJobService`) but they need real prompts, artefact handling, and error plumbing to make an end-to-end run believable.

## Immediate Milestone — "Agent Loop to Real Artefacts"
Deliver the first demonstrable ticket run that produces actual artefacts for each workflow state and exercises the runner jobs in sequence.

### Definition of Done
1. **Each state writes the correct artefact** into the ticket workspace (`docs/intake_summary.md`, `docs/design.md`, `outputs/profile_report.json`, `dbt_changes/**`, `docs/qa_report.md`, `docs/pr_summary.md`).
2. **Runner jobs fire with meaningful payloads.** Profiling invokes `snowflake_sql` jobs, BUILD triggers `workspace_write_files` + `dbt_compile`, QA triggers `dbt_build`, PR triggers git + PR jobs (even if mocked).
3. **Orchestrator events reflect reality.** `workflow_events` captures `state_transition`, `agent_completed`, and `artifact_created` details drawn from the real artefacts, not placeholders.
4. **UI/consumer contract preserved.** Artefacts are registered via `ArtifactService` so the web layer can surface them without code changes.
5. **Smoke run:** `python app/scripts/dev_seed.py` (or equivalent) + `pytest app/tests/workflows/test_ticket_to_pr.py` (if present) succeed, and a manual ticket run moves from `TICKET_INTAKE` → `DONE` without manual DB edits.

### Guardrails / Constraints
- **No shell commands from FastAPI or agents.** All execution goes through `RunnerClient` (snowflake, dbt, git, gh).
- **Path safety.** Use `WORKSPACES_ROOT` + `workspace_rel` helpers; never hardcode `/workspace` strings.
- **Idempotent runner jobs.** Make sure repeated profiling/builds don’t corrupt workspaces; log job IDs via `RunnerJobService`.
- **Artefact contracts match docs.** File names + locations must align with the table in `docs/agent_operating_model.md`.

### Files to Read / Touch First
1. `docs/agent_operating_model.md` — artefact names + tool allowlists.
2. `api/app/services/agent_runner.py` — replace placeholder logic with real prompts + runner orchestration.
3. `api/app/services/openclaw_service.py` — implement real calls into the gateway/agents (Claude sessions, prompts, context packaging).
4. `api/app/services/runner_client.py` + `runner_job_service.py` — ensure payloads/job logging cover new job types.
5. `api/app/services/artifact_service.py` — make sure new artefacts register with correct metadata.

### Suggested Task Breakdown for Claude
1. **Prompt + context plumbing**
- Define per-agent prompts/config in `gateway/openclaw/agents` (or config JSON) referencing the docs list above.
- Implement `OpenClawClient.start_agent` to call `/v1/responses` or `/agent/run` with workflow/ticket context (ticket JSON, prior artefacts, workspace paths).
2. **Artefact writers per state**
- Intake/Design: capture Claude output as Markdown in `docs/`.
- Profiling: store JSON/Markdown summarising Snowflake runner results under `outputs/` + `docs/`.
- Builder: write actual files into `dbt_changes/models/**` + `schema.yml` + capture compile summary JSON.
- QA: parse runner `dbt_build` output to create `docs/qa_report.md` + `outputs/run_results.json`.
3. **Runner job integration**
- Flesh out `RunnerClient` methods for snowflake/dbt/git jobs (request/response schema, error handling) and call them from AgentRunner at the right states.
4. **State advancement + gating**
- Ensure `AgentRunner.mark_agent_complete` only advances when artefacts exist; add retries/failure paths as needed.
5. **Smoke automation**
- Add or update a dev script (`scripts/dev_seed.py`) to create a ticket, kick the workflow, and print artefact paths for manual inspection.

### Acceptance Evidence Checklist
- Screenshot or log of a ticket moving through all states with artefact links populated.
- Artefact directory listing under `workspaces/tenants/<tenant>/tickets/<ticket>/docs|outputs|dbt_changes` showing the files above.
- Runner job log entries for snowflake + dbt + git/PR with non-placeholder payloads.
- `workflow_events` table rows for each state transition + agent completion referencing real artefact IDs.

## Future Milestones (context only)
- **Milestone 2:** Surface the artefacts + runner logs in the Next.js UI (Kanban cards, artefact viewer, agent timeline, trace view).
- **Milestone 3:** Wire GitHub + Snowflake credentials for the live demo tenant, enable PR creation + dashboards.
- **Milestone 4:** Harden error handling + add multi-tenant provisioning flows for on-stage resets.

Stay disciplined: finish Milestone 1 end-to-end before touching UI polish or extra agents. Once the artefact pipeline is real, the rest of the demo story becomes believable.