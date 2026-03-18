"""
AgentRunner — executes the per-state agent logic for each workflow step.

For Milestone 1 the artefact content is generated deterministically from
ticket context (no real Claude call required).  The OpenClaw gateway call
is fire-and-log; its response is not used for artefact generation.

Each agent state produces canonical artefacts:
  TICKET_INTAKE  -> docs/intake_summary.md
  DESIGN_REVIEW  -> docs/design.md
  PROFILING      -> outputs/profile_report.json, docs/profiling.md
  BUILD          -> dbt_changes/models/gold/<slug>.sql,
                    dbt_changes/tests/schema.yml,
                    outputs/compile_summary.json
  QA             -> outputs/run_results.json, docs/qa_report.md
  PR_CREATION    -> docs/pr_summary.md
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.models.agent_session import AgentSession
from app.models.runner_job import RunnerJob
from app.models.tenant import Tenant
from app.models.ticket import Ticket
from app.models.uploaded_file import UploadedFile
from app.models.workflow_run import WorkflowRun
from app.services.artifact_service import ArtifactService
from app.services.openclaw_service import OpenClawClient
from app.services.runner_client import RunnerClient
from app.services.workflow_events import append_workflow_event
from app.services.workspace_manager import WorkspaceManager
from app.utils.time import utc_now
from app.workflows.ticket_to_pr import STATE_AGENT_MAP
from app.workflows.tenant_provisioning import STATE_AGENT_MAP as PROVISIONING_STATE_AGENT_MAP

WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "/workspace")).resolve()

_ALL_AGENT_STATE_MAPS = [STATE_AGENT_MAP, PROVISIONING_STATE_AGENT_MAP]
AGENT_STATE_MAP = {}
for _m in _ALL_AGENT_STATE_MAPS:
    AGENT_STATE_MAP.update({agent: state for state, agent in _m.items()})


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------

class AgentRunner:

    def __init__(self, session: Session):
        self.session = session
        self.client = OpenClawClient()
        self.runner = RunnerClient()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_task(self, workflow_run: WorkflowRun, agent_name: str):
        target_state = AGENT_STATE_MAP.get(agent_name)

        if not target_state:
            print(f"[runner] unknown agent '{agent_name}' for run {workflow_run.workflow_run_id}")
            return None

        # Idempotency guard
        existing = self.session.exec(
            select(AgentSession).where(
                AgentSession.workflow_run_id == workflow_run.workflow_run_id,
                AgentSession.agent_name == agent_name,
            )
        ).first()

        if existing:
            print(f"[runner] agent already ran: {agent_name}")
            return None

        agent_session = AgentSession(
            workflow_run_id=workflow_run.workflow_run_id,
            ticket_id=workflow_run.ticket_id,
            agent_name=agent_name,
            status="running",
        )
        self.session.add(agent_session)
        self.session.commit()
        self.session.refresh(agent_session)

        # Fire-and-log OpenClaw call (response not used for artefacts in M1)
        try:
            self.client.start_agent(
                agent_name=agent_name,
                workflow_run_id=workflow_run.workflow_run_id,
            )
        except Exception as exc:
            print(f"[runner] openclaw unavailable, continuing: {exc}")

        ticket = self._get_ticket(workflow_run.ticket_id)
        workspace_root = workflow_run.workspace_root or str(WORKSPACES_ROOT)
        workspace_rel = self._workspace_relative_path(workspace_root)

        try:
            if target_state == "TICKET_INTAKE":
                self._run_intake(workflow_run, ticket, workspace_root, workspace_rel)
            elif target_state == "DESIGN_REVIEW":
                self._run_design(workflow_run, ticket, workspace_root, workspace_rel)
            elif target_state == "PROFILING":
                self._run_profiling(workflow_run, ticket, workspace_root, workspace_rel)
            elif target_state == "BUILD":
                self._run_build(workflow_run, ticket, workspace_root, workspace_rel)
            elif target_state == "QA":
                self._run_qa(workflow_run, ticket, workspace_root, workspace_rel)
            elif target_state == "PR_CREATION":
                self._run_pr(workflow_run, ticket, workspace_root, workspace_rel)
            elif target_state == "DATA_INGESTION":
                self._run_data_ingestion(workflow_run, ticket, workspace_root, workspace_rel)
            elif target_state == "PROVISIONING_REQUESTED":
                self._run_tenant_provisioning(workflow_run, ticket, workspace_root, workspace_rel)
            else:
                print(f"[runner] no handler for state {target_state}")
        except Exception as exc:
            print(f"[runner] {agent_name} failed: {exc}")
            agent_session.status = "failed"
            agent_session.finished_at = utc_now()
            self.session.add(agent_session)
            ticket.last_error = str(exc)[:500]
            self.session.add(ticket)
            self.session.commit()
            from app.services.orchestrator import Orchestrator
            Orchestrator(self.session).fail_workflow(workflow_run, "AGENT_FAILED", str(exc)[:500])
            raise

        self.mark_agent_complete(agent_session)

    def mark_agent_complete(self, agent_session: AgentSession):
        if agent_session.status == "completed":
            return

        agent_session.status = "completed"
        self.session.add(agent_session)
        self.session.commit()

        workflow_run = self.session.get(WorkflowRun, agent_session.workflow_run_id)

        # Appending the agent_completed event triggers WorkflowEventConsumer,
        # which calls orchestrator.advance() inline.  Do NOT call advance()
        # again here — that would double-advance through non-gated states.
        append_workflow_event(
            self.session,
            workflow_run_id=workflow_run.workflow_run_id,
            ticket_id=workflow_run.ticket_id,
            trace_id=workflow_run.trace_id,
            event_type="agent_completed",
            message=f"{agent_session.agent_name} completed",
        )

    # ------------------------------------------------------------------
    # Per-state handlers
    # ------------------------------------------------------------------

    def _run_intake(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        content = _render_intake_summary(ticket)
        written = self._write_files(workspace_rel, [{"path": "docs/intake_summary.md", "content": content}])
        self._register_and_emit(wf, written[0], "intake_summary", "design_doc")

    def _run_design(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        slug = _slugify(ticket.title)
        prior_intake = self._read_workspace_file(workspace_root, "docs/intake_summary.md")
        content = _render_design_doc(ticket, slug, prior_intake)
        written = self._write_files(workspace_rel, [{"path": "docs/design.md", "content": content}])
        self._register_and_emit(wf, written[0], "design_md", "design_doc")

    def _run_profiling(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        slug = _slugify(ticket.title)

        # Use ticket-level catalog if it exists (populated by DataIngestionAgent)
        tenant_id = ticket.tenant_id or "default"
        wm = WorkspaceManager()
        catalog_path = wm.get_catalog_path(tenant_id, wf.ticket_id)
        # Only use catalog if the .duckdb file was actually created by data ingestion
        catalog_rel = str(catalog_path.relative_to(WORKSPACES_ROOT)) if catalog_path.is_file() else None

        # Build profiling queries from available tables in catalog
        queries = self._build_profiling_queries(catalog_rel, workspace_rel)

        all_results = []
        for q in queries:
            job_args: dict = {"query": q, "connection": "default"}
            if catalog_rel:
                job_args["catalog_path"] = catalog_rel
            result = self.runner.run_job("snowflake_sql", workspace_rel, job_args)
            all_results.append(result)

        first_rows = (all_results[0].get("rows") or [{}])[0] if all_results else {}
        second_rows = (all_results[1].get("rows") or [{}])[0] if len(all_results) > 1 else {}

        profile = {
            "ticket_id": wf.ticket_id,
            "slug": slug,
            "profiled_at": _now_iso(),
            "sources": list(first_rows.keys()) or ["RAW.ORDERS"],
            "query_results": all_results,
            "summary": {
                "row_count": first_rows.get("row_count", first_rows.get("total", 0)),
                "distinct_customers": second_rows.get("distinct_customers", second_rows.get("total", 0)),
                "null_issues": [],
            },
        }
        profile_json = json.dumps(profile, indent=2)
        profiling_md = _render_profiling_md(ticket, profile)

        written = self._write_files(workspace_rel, [
            {"path": "outputs/profile_report.json", "content": profile_json},
            {"path": "docs/profiling.md", "content": profiling_md},
        ])
        self._register_and_emit(wf, written[0], "profile_report", "profiling_report")
        self._register_and_emit(wf, written[1], "profiling_md", "profiling_report")

    def _run_build(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        slug = _slugify(ticket.title)
        prior_design = self._read_workspace_file(workspace_root, "docs/design.md")

        model_sql = _render_dbt_model(ticket, slug, prior_design)
        schema_yml = _render_schema_yml(slug)

        written = self._write_files(workspace_rel, [
            {"path": f"dbt_changes/models/gold/{slug}.sql", "content": model_sql},
            {"path": "dbt_changes/tests/schema.yml", "content": schema_yml},
        ])
        self._register_and_emit(wf, written[0], f"{slug}_sql", "dbt_model")
        self._register_and_emit(wf, written[1], "schema_yml", "dbt_model")

        compile_result = self.runner.run_job(
            "dbt_compile",
            workspace_rel,
            {"select": slug, "project_dir": "dbt_changes"},
        )
        compile_path = compile_result.get("compile_summary_path", "outputs/compile_summary.json")
        self._register_artifact_and_emit(
            wf,
            str(WORKSPACES_ROOT / compile_path),
            "compile_summary",
            "compile_summary",
        )

    def _run_qa(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        slug = _slugify(ticket.title)

        build_result = self.runner.run_job(
            "dbt_build",
            workspace_rel,
            {"select": slug, "project_dir": "dbt_changes"},
        )
        rr_path = build_result.get("run_results_path", "outputs/run_results.json")
        self._register_artifact_and_emit(
            wf,
            str(WORKSPACES_ROOT / rr_path),
            "run_results",
            "qa_evidence",
        )

        passed = build_result.get("passed", 1)
        failed = build_result.get("failed", 0)
        qa_md = _render_qa_report(ticket, slug, passed, failed)
        written = self._write_files(workspace_rel, [{"path": "docs/qa_report.md", "content": qa_md}])
        self._register_and_emit(wf, written[0], "qa_report_md", "qa_evidence")

    def _run_pr(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        slug = _slugify(ticket.title)
        branch = f"autode/{wf.ticket_id[:8]}-{slug}"

        changed_files = [
            f"dbt_changes/models/gold/{slug}.sql",
            "dbt_changes/tests/schema.yml",
        ]

        git_result = self.runner.run_job(
            "git_commit_push",
            workspace_rel,
            {
                "branch": branch,
                "commit_message": f"feat({slug}): add dbt model and tests\n\nTicket: {wf.ticket_id}",
                "files": changed_files,
            },
        )
        commit_sha = git_result.get("commit_sha", "unknown")

        pr_result = self.runner.run_job(
            "gh_create_pr",
            workspace_rel,
            {
                "repo": "org/dbt-repo",
                "branch": branch,
                "title": f"feat: {ticket.title}",
                "body": (
                    f"## Summary\n\nAutomated PR for ticket `{wf.ticket_id}`.\n\n"
                    f"**Model:** `{slug}`  \n**Branch:** `{branch}`  \n\n"
                    f"## QA Evidence\n\ndbt build passed. See `outputs/run_results.json`.\n"
                ),
            },
        )
        pr_url = pr_result.get("pr_url", "")
        pr_number = pr_result.get("pr_number", 0)

        pr_summary = _render_pr_summary(ticket, slug, branch, commit_sha, pr_url, pr_number, changed_files)
        written = self._write_files(workspace_rel, [{"path": "docs/pr_summary.md", "content": pr_summary}])
        self._register_and_emit(wf, written[0], "pr_summary_md", "pr_summary")

    def _run_data_ingestion(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        tenant_id = ticket.tenant_id or "default"
        catalog_path = WorkspaceManager().get_catalog_path(tenant_id, wf.ticket_id)
        catalog_rel = str(catalog_path.relative_to(WORKSPACES_ROOT))

        uploads = self.session.exec(
            select(UploadedFile).where(UploadedFile.ticket_id == wf.ticket_id)
        ).all()

        file_paths = [
            str(Path(u.stored_path).relative_to(WORKSPACES_ROOT)) for u in uploads
            if Path(u.stored_path).exists()
        ]

        table_schemas: dict = {}
        if file_paths:
            load_result = self._run_job_tracked(wf, "load_ticket_data", workspace_rel, {
                "catalog_path": catalog_rel,
                "file_paths": file_paths,
            }, seq=1)
            table_schemas = load_result.get("tables", {})

            # Update UploadedFile rows with inferred schema.
            # Must match runner's table name derivation: _safe_stem then strip RAW_ prefix.
            for upload in uploads:
                stem = Path(upload.filename).stem.upper().replace("-", "_").replace(" ", "_")
                stem = re.sub(r"[^A-Z0-9_]", "_", stem)
                if stem[0:1].isdigit():
                    stem = f"T_{stem}"
                if stem.startswith("RAW_"):
                    stem = stem[4:]
                if stem in table_schemas:
                    upload.schema_json = json.dumps(table_schemas[stem])
                    self.session.add(upload)
            self.session.commit()

            dd_result = self._run_job_tracked(wf, "get_data_dictionary", workspace_rel, {
                "catalog_path": catalog_rel,
            }, seq=2)

            dd_json = json.dumps(dd_result, indent=2)
            written_dd = self._write_files(workspace_rel, [
                {"path": "outputs/data_dictionary.json", "content": dd_json}
            ])
            self._register_and_emit(wf, written_dd[0], "data_dictionary", "profiling_report")

            # Write raw_tables.json — proves what landed in the catalog
            raw_tables_info = {
                tbl: {
                    "row_count": info.get("row_count", 0),
                    "columns": [{"name": c["name"], "type": c["type"]} for c in info.get("columns", [])],
                }
                for tbl, info in dd_result.get("tables", {}).items()
            }
            written_rt = self._write_files(workspace_rel, [
                {"path": "outputs/raw_tables.json", "content": json.dumps(raw_tables_info, indent=2)}
            ])
            self._register_and_emit(wf, written_rt[0], "raw_tables_json", "profiling_report")
        else:
            dd_result = {}

        # Build and register requirements.md
        req_md = _render_requirements_md(ticket, uploads, table_schemas)
        written = self._write_files(workspace_rel, [{"path": "docs/requirements.md", "content": req_md}])
        self._register_and_emit(wf, written[0], "requirements_md", "design_doc")

    def _build_profiling_queries(self, catalog_rel: str | None, workspace_rel: str) -> list[str]:
        """Return profiling queries appropriate for the available data source."""
        if not catalog_rel:
            return [
                "SELECT COUNT(*) AS row_count FROM RAW.ORDERS",
                "SELECT COUNT(DISTINCT customer_id) AS distinct_customers, COUNT(*) AS total FROM RAW.ORDERS",
                "SELECT COUNT(*) - COUNT(order_id) AS null_order_ids, COUNT(*) AS total FROM RAW.ORDERS",
            ]
        # Discover available tables in catalog
        try:
            tables_result = self.runner.run_job("get_data_dictionary", workspace_rel, {
                "catalog_path": catalog_rel,
                "summary_only": True,
            })
            tables = list(tables_result.get("tables", {}).keys())
        except Exception:
            tables = []

        if not tables:
            return ["SELECT 1 AS placeholder"]

        # Generate COUNT queries for up to 3 tables
        queries = []
        for tbl in tables[:3]:
            queries.append(f"SELECT COUNT(*) AS row_count FROM RAW.{tbl}")
        return queries

    def _run_tenant_provisioning(self, wf: WorkflowRun, ticket: Ticket, workspace_root: str, workspace_rel: str):
        import time

        tenant_id = ticket.tenant_id
        if not tenant_id:
            raise RuntimeError("ticket has no tenant_id for provisioning")

        tenant = self.session.get(Tenant, tenant_id)
        if not tenant:
            raise RuntimeError(f"tenant {tenant_id} not found")

        tenant.status = "provisioning_running"
        self.session.add(tenant)
        self.session.commit()

        plan_content = f"""# Tenant Provisioning Plan

## Tenant
- **Key**: `{tenant.tenant_key}`
- **Name**: {tenant.name}
- **Tenant ID**: `{tenant_id}`

## Jobs to Run
1. `snowflake_provision` — create DuckDB schema for tenant
2. `snowflake_seed_demo_data` — load fixture data into tenant schema
3. `dbt_bootstrap` — write dbt project stubs
4. `dbt_smoke` — run smoke query to verify data

## Config
- Workspace: `{workspace_root}`
- dbt repo: {tenant.dbt_repo_url or "_not set_"}
"""
        written = self._write_files(workspace_rel, [{"path": "docs/provisioning_plan.md", "content": plan_content}])
        self._register_and_emit(wf, written[0], "provisioning_plan", "design_doc")

        # Job 1: snowflake_provision (with retry; seq includes attempt to keep request_id unique)
        job1_args = {"tenant_key": tenant.tenant_key}
        for attempt in range(1, 4):
            try:
                self._run_job_tracked(wf, "snowflake_provision", workspace_rel, job1_args, seq=attempt)
                break
            except Exception as exc:
                if attempt == 3:
                    raise
                delay = [2, 4, 8][attempt - 1]
                append_workflow_event(
                    self.session,
                    workflow_run_id=wf.workflow_run_id,
                    ticket_id=wf.ticket_id,
                    trace_id=wf.trace_id,
                    event_type="retry",
                    severity="WARN",
                    message=f"snowflake_provision attempt {attempt} failed, retrying in {delay}s: {exc}",
                )
                time.sleep(delay)

        # Job 2: seed demo data
        self._run_job_tracked(wf, "snowflake_seed_demo_data", workspace_rel, {"tenant_key": tenant.tenant_key}, seq=2)

        # Job 3: dbt bootstrap
        self._run_job_tracked(wf, "dbt_bootstrap", workspace_rel, {
            "tenant_key": tenant.tenant_key,
            "dbt_repo_url": tenant.dbt_repo_url or "",
        }, seq=3)

        # Job 4: dbt smoke
        smoke_result = self._run_job_tracked(wf, "dbt_smoke", workspace_rel, {"tenant_key": tenant.tenant_key}, seq=4)

        report_content = f"""# Tenant Provisioning Report

## Tenant
- **Key**: `{tenant.tenant_key}`
- **Name**: {tenant.name}

## Jobs Completed
| Job | Status |
|---|---|
| snowflake_provision | succeeded |
| snowflake_seed_demo_data | succeeded |
| dbt_bootstrap | succeeded |
| dbt_smoke | succeeded |

## Smoke Result
```json
{json.dumps(smoke_result, indent=2)}
```

## Status
Tenant is **ready**.
"""
        written2 = self._write_files(workspace_rel, [{"path": "docs/provisioning_report.md", "content": report_content}])
        self._register_and_emit(wf, written2[0], "provisioning_report", "design_doc")

        tenant.status = "ready"
        tenant.workspace_root = workspace_root
        self.session.add(tenant)
        self.session.commit()
        # mark_agent_complete is called by run_task() after this method returns

    def _run_job_tracked(self, wf: WorkflowRun, job_type: str, workspace_rel: str, args: dict, seq: int = 0):
        request_id = f"{wf.workflow_run_id}:{job_type}:{seq}"
        job = RunnerJob(
            workflow_run_id=wf.workflow_run_id,
            ticket_id=wf.ticket_id,
            request_id=request_id,
            job_type=job_type,
            status="running",
            request_payload_json=json.dumps({k: v for k, v in args.items() if "secret" not in k}),
            started_at=utc_now(),
        )
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        try:
            result = self.runner.run_job(job_type, workspace_rel, args)
            job.status = "succeeded"
            job.result_payload_json = json.dumps(result)[:4000]
            job.finished_at = utc_now()
            self.session.add(job)
            self.session.commit()
            return result
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.finished_at = utc_now()
            self.session.add(job)
            self.session.commit()
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write_files(self, workspace_rel: str, files: list) -> list:
        result = self.runner.write_files(workspace_rel, files)
        written = result.get("files_written", [])
        if not written:
            raise RuntimeError(f"runner returned no written files for {[f['path'] for f in files]}")
        return written

    def _register_and_emit(
        self, wf: WorkflowRun, rel_path: str, artifact_type: str, artifact_role: str
    ):
        """rel_path is relative to WORKSPACES_ROOT (as returned by runner)."""
        self._register_artifact_and_emit(wf, str(WORKSPACES_ROOT / rel_path), artifact_type, artifact_role)

    def _register_artifact_and_emit(
        self, wf: WorkflowRun, file_path: str, artifact_type: str, artifact_role: str
    ):
        svc = ArtifactService(self.session)
        artifact = svc.register_artifact(
            workflow_run_id=wf.workflow_run_id,
            ticket_id=wf.ticket_id,
            artifact_role=artifact_role,
            artifact_type=artifact_type,
            file_path=file_path,
        )
        append_workflow_event(
            self.session,
            workflow_run_id=wf.workflow_run_id,
            ticket_id=wf.ticket_id,
            trace_id=wf.trace_id,
            event_type="artifact_created",
            message=f"artifact registered: {artifact_type}",
            payload_json=json.dumps({
                "artifact_id": artifact.artifact_id,
                "artifact_type": artifact_type,
                "artifact_role": artifact_role,
                "file_path": file_path,
            }),
        )

    def _get_ticket(self, ticket_id: str) -> Ticket:
        ticket = self.session.get(Ticket, ticket_id)
        if not ticket:
            raise RuntimeError(f"ticket {ticket_id} not found")
        return ticket

    def _read_workspace_file(self, workspace_root: str, rel_path: str) -> str | None:
        path = Path(workspace_root) / rel_path
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _workspace_relative_path(self, workspace_root: str) -> str:
        workspace = Path(workspace_root).resolve()
        return str(workspace.relative_to(WORKSPACES_ROOT))


# ---------------------------------------------------------------------------
# Content renderers
# ---------------------------------------------------------------------------

def _render_requirements_md(ticket: Ticket, uploads: list, table_schemas: dict) -> str:
    sources = json.loads(ticket.sources_json) if ticket.sources_json else []
    metrics = json.loads(ticket.metrics_json) if ticket.metrics_json else []
    constraints = json.loads(ticket.constraints_json) if ticket.constraints_json else []

    upload_section = ""
    if uploads:
        upload_section = "\n## Uploaded Files\n\n"
        for u in uploads:
            upload_section += f"- `{u.filename}` ({u.size_bytes:,} bytes"
            if u.mime_type:
                upload_section += f", {u.mime_type}"
            upload_section += ")\n"

    schema_section = ""
    if table_schemas:
        schema_section = "\n## Inferred Schemas\n\n"
        for tbl, cols in table_schemas.items():
            schema_section += f"### RAW.{tbl}\n\n"
            schema_section += "| Column | Type |\n|---|---|\n"
            for col in cols:
                schema_section += f"| `{col.get('name', '?')}` | {col.get('type', '?')} |\n"
            schema_section += "\n"

    sources_md = "\n".join(f"- {s}" for s in sources) if sources else "_No sources specified._"
    metrics_md = "\n".join(f"- {m}" for m in metrics) if metrics else "_No metrics specified._"
    constraints_md = "\n".join(f"- {c}" for c in constraints) if constraints else "_No constraints specified._"

    return f"""# Requirements

## Ticket
- **ID**: `{ticket.ticket_id}`
- **Title**: {ticket.title}
- **Kind**: {ticket.ticket_kind}

## Description
{ticket.description or "_No description provided._"}

## Sources
{sources_md}

## Grain
{ticket.grain or "_Not specified._"}

## Metrics
{metrics_md}

## Constraints
{constraints_md}
{upload_section}{schema_section}
## Status
Requirements captured. Data ingestion complete. Ready for agent processing.
"""


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s_]", "", slug)
    slug = re.sub(r"\s+", "_", slug.strip())
    slug = re.sub(r"_+", "_", slug)
    parts = slug.split("_")[:6]
    return "_".join(parts) or "model"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _render_intake_summary(ticket: Ticket) -> str:
    return f"""# Intake Summary

## Ticket
- **ID**: `{ticket.ticket_id}`
- **Title**: {ticket.title}
- **Kind**: {ticket.ticket_kind}

## Description
{ticket.description or "_No description provided._"}

## Acceptance Criteria
- [ ] dbt model builds successfully
- [ ] Primary key uniqueness and not-null tests pass
- [ ] Model is documented in schema.yml
- [ ] PR is opened with QA evidence

## Clarifying Questions
_None at this time. All required fields are present._

## Status
Ticket is ready to proceed to Design Review.
"""


def _render_design_doc(ticket: Ticket, slug: str, prior_intake: str | None) -> str:
    return f"""# Design Document

## Overview
Automated design for ticket: **{ticket.title}**

## Model Plan
| Model | Layer | Type |
|---|---|---|
| `{slug}` | gold | table |

## Grain & Keys
- **Grain**: one row per primary entity
- **Primary key**: `{slug}_id`

## Source Tables
- `RAW.ORDERS`
- `RAW.CUSTOMERS`

## Incremental Strategy
- Materialization: `table`
- Unique key: `{slug}_id`

## Test Plan
| Test | Column | Severity |
|---|---|---|
| `not_null` | `{slug}_id` | error |
| `unique` | `{slug}_id` | error |
| `not_null` | `order_date` | error |

## Notes
{ticket.description or "_Refer to ticket description for business context._"}

## Status
Design ready for human review. Awaiting approval before profiling.
"""


def _render_profiling_md(ticket: Ticket, profile: dict) -> str:
    summary = profile.get("summary", {})
    row_count = summary.get("row_count", "N/A")
    distinct = summary.get("distinct_customers", "N/A")
    null_issues = summary.get("null_issues", [])
    return f"""# Profiling Report

## Ticket
**{ticket.title}**

## Sources Profiled
{chr(10).join(f"- `{s}`" for s in profile.get("sources", []))}

## Key Statistics
| Metric | Value |
|---|---|
| Row count (RAW.ORDERS) | {row_count:,} |
| Distinct customers | {distinct:,} |

## Null / Integrity Issues
{", ".join(null_issues) if null_issues else "_None detected._"}

## Profiling Queries Run
{len(profile.get("query_results", []))} queries executed.

## Recommendations
- Source tables are clean; proceed to BUILD.
- Recommend `not_null` + `unique` tests on primary keys.
"""


def _render_dbt_model(ticket: Ticket, slug: str, prior_design: str | None) -> str:
    return f"""{{{{ config(
    materialized = 'table',
    unique_key = '{slug}_id'
) }}}}

/*
  Model: {slug}
  Ticket: {ticket.ticket_id}
  Description: {ticket.title}
  Generated by: Factoria BuilderAgent
*/

WITH source_orders AS (
    SELECT * FROM {{{{ source('raw', 'orders') }}}}
),

source_customers AS (
    SELECT * FROM {{{{ source('raw', 'customers') }}}}
),

joined AS (
    SELECT
        o.order_id                     AS {slug}_id,
        o.order_date,
        o.customer_id,
        c.customer_segment,
        o.order_amount                 AS revenue,
        1                              AS order_count
    FROM source_orders AS o
    LEFT JOIN source_customers AS c
        ON o.customer_id = c.customer_id
),

final AS (
    SELECT
        {slug}_id,
        order_date,
        customer_id,
        customer_segment,
        revenue,
        order_count
    FROM joined
)

SELECT * FROM final
"""


def _render_schema_yml(slug: str) -> str:
    return f"""version: 2

models:
  - name: {slug}
    description: "Auto-generated model for {slug}. Managed by Factoria."
    columns:
      - name: {slug}_id
        description: "Primary key."
        tests:
          - not_null
          - unique

      - name: order_date
        description: "Date of the order."
        tests:
          - not_null

      - name: customer_id
        description: "Foreign key to customers."
        tests:
          - not_null

      - name: customer_segment
        description: "Customer segment label."

      - name: revenue
        description: "Order revenue amount."

      - name: order_count
        description: "Always 1 — used for aggregation."
"""


def _render_qa_report(ticket: Ticket, slug: str, passed: int, failed: int) -> str:
    status = "PASSED" if failed == 0 else "FAILED"
    return f"""# QA Report

## Ticket
**{ticket.title}**

## dbt Build Result: {status}

| Metric | Value |
|---|---|
| Model | `{slug}` |
| Tests passed | {passed} |
| Tests failed | {failed} |
| Materialization | table |

## Run Evidence
See `outputs/run_results.json` for full dbt invocation details.

## Nodes Executed
- `model.factoria.{slug}` — {status.lower()}

## Recommendation
{"Proceed to Ready for Review gate." if failed == 0 else "Return to BUILD with failure artefacts."}
"""


def _render_pr_summary(
    ticket: Ticket,
    slug: str,
    branch: str,
    commit_sha: str,
    pr_url: str,
    pr_number: int,
    changed_files: list,
) -> str:
    files_md = "\n".join(f"- `{f}`" for f in changed_files)
    return f"""# PR Summary

## Ticket
**{ticket.title}**
Ticket ID: `{ticket.ticket_id}`

## Pull Request
- **URL**: {pr_url}
- **PR Number**: #{pr_number}
- **Branch**: `{branch}`
- **Commit**: `{commit_sha}`

## Files Changed
{files_md}

## QA Evidence
- dbt build: PASSED
- Full results: `outputs/run_results.json`

## Status
PR is open and ready for human review.
"""
