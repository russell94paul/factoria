import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import duckdb
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "/workspace")).resolve()
ALLOWED_EXTENSIONS = {".sql", ".yml", ".yaml", ".md", ".json"}
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _strip_jinja(sql: str) -> str:
    """Strip Jinja blocks so plain SQL can be executed by DuckDB.

    Handles the patterns produced by _render_dbt_model in agent_runner.py:
      {{ config(...) }}               → removed
      {{ source('schema', 'table') }} → SCHEMA.TABLE
      {{ ref('model') }}              → model
      {% ... %}                       → removed
    """
    # {{ config(...) }} — may span multiple lines
    sql = re.sub(r"\{\{[\s]*config\s*\(.*?\)\s*\}\}", "", sql, flags=re.DOTALL)

    # {{ source('schema', 'table') }} → SCHEMA.TABLE
    def _source(m: re.Match) -> str:
        return f"{m.group(1).strip().upper()}.{m.group(2).strip().upper()}"

    sql = re.sub(
        r"\{\{\s*source\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*\)\s*\}\}",
        _source,
        sql,
    )

    # {{ ref('model') }} → model
    sql = re.sub(r"\{\{\s*ref\s*\(\s*['\"](\w+)['\"]\s*\)\s*\}\}", r"\1", sql)

    # {% ... %} tags
    sql = re.sub(r"\{%.*?%\}", "", sql, flags=re.DOTALL)

    # any remaining {{ ... }}
    sql = re.sub(r"\{\{.*?\}\}", "", sql, flags=re.DOTALL)

    return sql.strip()

app = FastAPI(title="Factoria Runner")


class RunRequest(BaseModel):
    job: str
    workspace: str
    args: Dict[str, Any] = {}


JOBS: Dict[str, Dict[str, Any]] = {}


@app.get("/health")
def health():
    return {"runner": "ok"}


@app.post("/run")
def run_job(request: RunRequest):
    job_id = str(uuid.uuid4())

    record = {
        "job_id": job_id,
        "job": request.job,
        "workspace": request.workspace,
        "args": request.args,
        "status": "received",
        "logs": [],
        "result": None,
        "error": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }

    JOBS[job_id] = record
    print(f"[runner] {job_id} -> {request.job} ({request.workspace})")

    try:
        record["status"] = "running"

        if request.job == "workspace_write_files":
            record["result"] = handle_workspace_write_files(request.workspace, request.args, record)
        elif request.job == "snowflake_sql":
            record["result"] = handle_snowflake_sql(request.workspace, request.args, record)
        elif request.job == "dbt_compile":
            record["result"] = handle_dbt_compile(request.workspace, request.args, record)
        elif request.job == "dbt_build":
            record["result"] = handle_dbt_build(request.workspace, request.args, record)
        elif request.job == "git_commit_push":
            record["result"] = handle_git_commit_push(request.workspace, request.args, record)
        elif request.job == "gh_create_pr":
            record["result"] = handle_gh_create_pr(request.workspace, request.args, record)
        elif request.job == "load_ticket_data":
            record["result"] = handle_load_ticket_data(request.workspace, request.args, record)
        elif request.job == "get_data_dictionary":
            record["result"] = handle_get_data_dictionary(request.workspace, request.args, record)
        elif request.job == "data_preview":
            record["result"] = handle_data_preview(request.workspace, request.args, record)
        elif request.job == "snowflake_provision":
            record["result"] = handle_snowflake_provision(request.workspace, request.args, record)
        elif request.job == "snowflake_seed_demo_data":
            record["result"] = handle_snowflake_seed_demo_data(request.workspace, request.args, record)
        elif request.job == "dbt_bootstrap":
            record["result"] = handle_dbt_bootstrap(request.workspace, request.args, record)
        elif request.job == "dbt_smoke":
            record["result"] = handle_dbt_smoke(request.workspace, request.args, record)
        elif request.job == "echo":
            record["result"] = handle_echo(request.args, record)
        else:
            raise HTTPException(status_code=400, detail=f"unknown job: {request.job}")

        record["status"] = "succeeded"
    except HTTPException as exc:
        print(f"[runner] {job_id} FAILED: {exc.detail}")
        record["status"] = "failed"
        record["error"] = exc.detail
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        raise
    except Exception as exc:
        print(f"[runner] {job_id} FAILED: {exc}")
        record["status"] = "failed"
        record["error"] = str(exc)
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        raise HTTPException(status_code=500, detail="job failed") from exc

    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(f"[runner] {job_id} -> {record['status']}")

    return {
        "job_id": job_id,
        "status": record["status"],
        "result": record["result"],
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/jobs/{job_id}/logs")
def get_job_logs(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "logs": job["logs"]}


# ---------------------------------------------------------------------------
# DuckDB helper
# ---------------------------------------------------------------------------

def _get_or_create_db(workspace_path: Path) -> duckdb.DuckDBPyConnection:
    """Open (or create) the per-workspace DuckDB database and seed RAW tables."""
    db_dir = workspace_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "factoria.duckdb"

    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE SCHEMA IF NOT EXISTS RAW")

    existing = {
        r[0].upper()
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE UPPER(table_schema) = 'RAW'"
        ).fetchall()
    }

    if "ORDERS" not in existing:
        orders_csv = (FIXTURES_DIR / "raw_orders.csv").as_posix()
        conn.execute(
            f"CREATE TABLE RAW.ORDERS AS SELECT * FROM read_csv_auto('{orders_csv}')"
        )
        n = conn.execute("SELECT COUNT(*) FROM RAW.ORDERS").fetchone()[0]
        print(f"[duckdb] loaded RAW.ORDERS ({n} rows)")

    if "CUSTOMERS" not in existing:
        customers_csv = (FIXTURES_DIR / "raw_customers.csv").as_posix()
        conn.execute(
            f"CREATE TABLE RAW.CUSTOMERS AS SELECT * FROM read_csv_auto('{customers_csv}')"
        )
        n = conn.execute("SELECT COUNT(*) FROM RAW.CUSTOMERS").fetchone()[0]
        print(f"[duckdb] loaded RAW.CUSTOMERS ({n} rows)")

    return conn


# ---------------------------------------------------------------------------
# Job handlers
# ---------------------------------------------------------------------------

def handle_workspace_write_files(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    files: List[Dict[str, Any]] = args.get("files", [])

    if not files:
        raise HTTPException(status_code=400, detail="no files provided")

    target_root = resolve_workspace(workspace)
    written_files = []

    for file_payload in files:
        path = file_payload.get("path")
        content = file_payload.get("content", "")

        if not path:
            raise HTTPException(status_code=400, detail="file path missing")

        safe_path = validate_relative_path(path)
        ext = safe_path.suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"extension '{ext}' not allowed")

        destination = target_root / safe_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        written_files.append(str(destination.relative_to(WORKSPACES_ROOT)))
        record["logs"].append(f"wrote {destination}")

    return {"files_written": written_files}


def handle_snowflake_sql(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Execute SQL against the workspace DuckDB database (DuckDB stands in for Snowflake).

    If args["catalog_path"] is provided (path relative to WORKSPACES_ROOT), that DuckDB
    file is opened instead of the per-run db. This allows profiling queries to run
    against the ticket-level catalog populated by load_ticket_data.
    """
    query = args.get("query", "")
    connection = args.get("connection", "default")
    catalog_path_rel = args.get("catalog_path")

    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    record["logs"].append(f"[duckdb:{connection}] executing query")
    record["logs"].append(f"  {query[:200]}{'...' if len(query) > 200 else ''}")

    target_root = resolve_workspace(workspace)

    if catalog_path_rel:
        catalog_abs = (WORKSPACES_ROOT / catalog_path_rel).resolve()
        if not str(catalog_abs).startswith(str(WORKSPACES_ROOT)):
            raise HTTPException(status_code=400, detail="catalog_path outside root")
        record["logs"].append(f"[duckdb] using catalog: {catalog_abs}")
        conn = duckdb.connect(str(catalog_abs))
    else:
        conn = _get_or_create_db(target_root)

    t0 = datetime.now(timezone.utc)
    try:
        rel = conn.execute(query)
        columns = [d[0] for d in rel.description]
        rows = [dict(zip(columns, row)) for row in rel.fetchall()]
    except Exception as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=f"DuckDB query failed: {exc}")
    t1 = datetime.now(timezone.utc)
    conn.close()

    execution_ms = int((t1 - t0).total_seconds() * 1000)
    record["logs"].append(f"returned {len(rows)} row(s) in {execution_ms}ms")

    result = {
        "connection": connection,
        "query": query,
        "row_count": len(rows),
        "rows": rows,
        "execution_ms": execution_ms,
    }

    # Append to workspace query log
    logs_dir = target_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "snowflake_sql.json"
    existing_log = json.loads(log_file.read_text()) if log_file.exists() else []
    existing_log.append(result)
    log_file.write_text(json.dumps(existing_log, indent=2))

    return result


def handle_dbt_compile(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Validate model SQL against DuckDB by attempting a CREATE VIEW dry-run."""
    select = args.get("select", "")
    project_dir = args.get("project_dir", "dbt_changes")

    record["logs"].append(f"[dbt compile] select={select!r} project_dir={project_dir!r}")

    target_root = resolve_workspace(workspace)
    models_dir = target_root / project_dir / "models"

    conn = _get_or_create_db(target_root)
    nodes_compiled: List[str] = []
    errors: List[Dict[str, str]] = []

    sql_files = list(models_dir.rglob("*.sql")) if models_dir.exists() else []
    record["logs"].append(f"[dbt compile] found {len(sql_files)} model file(s)")

    for sql_file in sql_files:
        model_name = sql_file.stem
        if select and select not in model_name:
            continue

        model_sql = _strip_jinja(sql_file.read_text(encoding="utf-8")).rstrip(";").strip()
        view_name = f"__validate_{model_name}"
        try:
            conn.execute(f"CREATE OR REPLACE VIEW {view_name} AS {model_sql}")
            conn.execute(f"DROP VIEW IF EXISTS {view_name}")
            nodes_compiled.append(f"model.factoria.{model_name}")
            record["logs"].append(f"[dbt compile] ✓ {model_name}")
        except Exception as exc:
            errors.append({"model": model_name, "error": str(exc)})
            record["logs"].append(f"[dbt compile] ✗ {model_name}: {exc}")

    conn.close()

    summary = {
        "status": "success" if not errors else "error",
        "select": select,
        "project_dir": project_dir,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "nodes_compiled": nodes_compiled,
        "errors": errors,
    }

    outputs_dir = target_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    summary_path = outputs_dir / "compile_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    record["logs"].append(f"wrote {summary_path}")

    if errors:
        raise HTTPException(status_code=400, detail=f"dbt compile errors: {errors}")

    return {
        "status": "success",
        "compile_summary_path": str(summary_path.relative_to(WORKSPACES_ROOT)),
        "nodes_compiled": nodes_compiled,
    }


def handle_dbt_build(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Materialise dbt models and run schema tests against DuckDB."""
    select = args.get("select", "")
    project_dir = args.get("project_dir", "dbt_changes")

    record["logs"].append(f"[dbt build] select={select!r} project_dir={project_dir!r}")

    target_root = resolve_workspace(workspace)
    models_dir = target_root / project_dir / "models"
    tests_dir = target_root / project_dir / "tests"
    schema_file = tests_dir / "schema.yml"

    conn = _get_or_create_db(target_root)
    results: List[Dict[str, Any]] = []

    # --- Step 1: materialise models ---
    sql_files = list(models_dir.rglob("*.sql")) if models_dir.exists() else []
    record["logs"].append(f"[dbt build] found {len(sql_files)} model file(s)")

    for sql_file in sql_files:
        model_name = sql_file.stem
        if select and select not in model_name:
            continue

        model_sql = _strip_jinja(sql_file.read_text(encoding="utf-8")).rstrip(";").strip()
        t0 = datetime.now(timezone.utc)
        try:
            conn.execute(f"CREATE OR REPLACE TABLE {model_name} AS {model_sql}")
            row_count = conn.execute(f"SELECT COUNT(*) FROM {model_name}").fetchone()[0]
            elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
            record["logs"].append(f"[dbt build] ✓ {model_name} ({row_count} rows, {elapsed:.2f}s)")
            results.append({
                "unique_id": f"model.factoria.{model_name}",
                "status": "success",
                "message": f"SUCCESS {row_count}",
                "timing": [{"name": "execute", "started_at": t0.isoformat(),
                             "completed_at": datetime.now(timezone.utc).isoformat()}],
                "thread_id": "Thread-1",
                "execution_time": elapsed,
                "adapter_response": {"_message": f"SUCCESS {row_count}", "rows_affected": row_count},
                "failures": None,
            })
        except Exception as exc:
            elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
            record["logs"].append(f"[dbt build] ✗ {model_name}: {exc}")
            results.append({
                "unique_id": f"model.factoria.{model_name}",
                "status": "error",
                "message": str(exc),
                "timing": [],
                "thread_id": "Thread-1",
                "execution_time": elapsed,
                "adapter_response": {},
                "failures": 1,
            })

    # --- Step 2: run schema tests ---
    if schema_file.exists():
        try:
            schema = yaml.safe_load(schema_file.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            record["logs"].append(f"[dbt build] could not parse schema.yml: {exc}")
            schema = {}

        for model_def in schema.get("models", []):
            model_name = model_def.get("name", "")
            for col_def in model_def.get("columns", []):
                col_name = col_def.get("name", "")
                for test in col_def.get("tests", []):
                    test_name = test if isinstance(test, str) else list(test.keys())[0]
                    test_uid = f"test.factoria.{model_name}.{col_name}.{test_name}"
                    t0 = datetime.now(timezone.utc)
                    try:
                        if test_name == "not_null":
                            fail_count = conn.execute(
                                f'SELECT COUNT(*) FROM "{model_name}" WHERE "{col_name}" IS NULL'
                            ).fetchone()[0]
                        elif test_name == "unique":
                            fail_count = conn.execute(
                                f'SELECT COUNT(*) - COUNT(DISTINCT "{col_name}") FROM "{model_name}"'
                            ).fetchone()[0]
                        else:
                            fail_count = 0

                        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
                        status = "pass" if fail_count == 0 else "fail"
                        record["logs"].append(
                            f"[dbt test] {test_name}({model_name}.{col_name}): {status} (failures={fail_count})"
                        )
                        results.append({
                            "unique_id": test_uid,
                            "status": status,
                            "message": f"{'PASS' if fail_count == 0 else 'FAIL'} {fail_count}",
                            "timing": [{"name": "execute", "started_at": t0.isoformat(),
                                        "completed_at": datetime.now(timezone.utc).isoformat()}],
                            "thread_id": "Thread-1",
                            "execution_time": elapsed,
                            "adapter_response": {"_message": "PASS" if fail_count == 0 else "FAIL",
                                                 "rows_affected": fail_count},
                            "failures": fail_count if fail_count > 0 else None,
                        })
                    except Exception as exc:
                        elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
                        record["logs"].append(f"[dbt test] ✗ {test_uid}: {exc}")
                        results.append({
                            "unique_id": test_uid,
                            "status": "error",
                            "message": str(exc),
                            "timing": [],
                            "thread_id": "Thread-1",
                            "execution_time": elapsed,
                            "adapter_response": {},
                            "failures": 1,
                        })

    conn.close()

    run_results = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/run-results/v4/manifest.json",
            "dbt_version": "1.7.0-duckdb",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "invocation_id": str(uuid.uuid4()),
        },
        "args": {"select": [select], "project_dir": project_dir},
        "results": results,
        "elapsed_time": sum(r.get("execution_time", 0) for r in results),
    }

    outputs_dir = target_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    results_path = outputs_dir / "run_results.json"
    results_path.write_text(json.dumps(run_results, indent=2))
    record["logs"].append(f"wrote {results_path}")

    passed = sum(1 for r in results if r["status"] in ("success", "pass"))
    failed = sum(1 for r in results if r["status"] in ("error", "fail"))
    record["logs"].append(f"[dbt build] passed={passed} failed={failed}")

    return {
        "status": "success" if failed == 0 else "partial",
        "run_results_path": str(results_path.relative_to(WORKSPACES_ROOT)),
        "passed": passed,
        "failed": failed,
    }


def handle_git_commit_push(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Mock git commit + push. Returns branch and commit SHA."""
    branch = args.get("branch", "autode/unknown")
    commit_message = args.get("commit_message", "chore: automated commit")
    files = args.get("files", [])

    record["logs"].append(f"[git] branch={branch!r}")
    record["logs"].append(f"[git] commit: {commit_message}")
    for f in files:
        record["logs"].append(f"[git]   + {f}")

    commit_sha = uuid.uuid4().hex[:8]
    record["logs"].append(f"[git] pushed {commit_sha} to origin/{branch}")

    return {
        "branch": branch,
        "commit_sha": commit_sha,
        "files_committed": len(files),
        "remote": "origin",
    }


def handle_gh_create_pr(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Mock GitHub PR creation. Returns PR URL and number."""
    repo = args.get("repo", "org/repo")
    branch = args.get("branch", "autode/unknown")
    title = args.get("title", "Automated PR")

    pr_number = 100 + (hash(branch) % 900)
    pr_url = f"https://github.com/{repo}/pull/{pr_number}"

    record["logs"].append(f"[gh] created PR #{pr_number}: {title}")
    record["logs"].append(f"[gh] {pr_url}")

    return {
        "pr_url": pr_url,
        "pr_number": pr_number,
        "repo": repo,
        "branch": branch,
        "title": title,
    }


def _safe_stem(filename: str) -> str:
    """Convert a filename stem to a DuckDB-safe uppercase table name."""
    stem = Path(filename).stem.upper().replace("-", "_").replace(" ", "_")
    # Strip non-alphanumeric/underscore chars
    stem = re.sub(r"[^A-Z0-9_]", "_", stem)
    if stem and stem[0].isdigit():
        stem = f"T_{stem}"
    return stem or "UNKNOWN"


def _open_catalog(catalog_path_rel: str) -> duckdb.DuckDBPyConnection:
    """Open a catalog DuckDB file by path relative to WORKSPACES_ROOT."""
    catalog_abs = (WORKSPACES_ROOT / catalog_path_rel).resolve()
    if not str(catalog_abs).startswith(str(WORKSPACES_ROOT)):
        raise HTTPException(status_code=400, detail="catalog_path outside root")
    catalog_abs.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(catalog_abs))
    conn.execute("CREATE SCHEMA IF NOT EXISTS RAW")
    return conn


def handle_load_ticket_data(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Load uploaded CSV/Parquet/JSON files into the ticket-level catalog.duckdb.

    Args:
        catalog_path: path relative to WORKSPACES_ROOT for the catalog .duckdb file
        file_paths: list of file paths relative to WORKSPACES_ROOT
    """
    catalog_path_rel = args.get("catalog_path", "")
    file_paths: List[str] = args.get("file_paths", [])

    if not catalog_path_rel:
        raise HTTPException(status_code=400, detail="catalog_path is required")

    conn = _open_catalog(catalog_path_rel)
    tables_loaded: Dict[str, Any] = {}

    for rel_path in file_paths:
        abs_path = (WORKSPACES_ROOT / rel_path).resolve()
        if not abs_path.exists():
            record["logs"].append(f"[load] SKIP {rel_path} — not found")
            continue

        stem = _safe_stem(abs_path.name)
        # Strip leading RAW_ prefix so raw_orders.csv → raw.ORDERS (not raw.RAW_ORDERS)
        table_name = stem[4:] if stem.startswith("RAW_") else stem
        suffix = abs_path.suffix.lower()
        posix = abs_path.as_posix()

        try:
            if suffix == ".csv":
                conn.execute(
                    f"CREATE OR REPLACE TABLE RAW.{table_name} AS "
                    f"SELECT * FROM read_csv_auto('{posix}')"
                )
            elif suffix == ".parquet":
                conn.execute(
                    f"CREATE OR REPLACE TABLE RAW.{table_name} AS "
                    f"SELECT * FROM read_parquet('{posix}')"
                )
            elif suffix in (".json", ".jsonl"):
                conn.execute(
                    f"CREATE OR REPLACE TABLE RAW.{table_name} AS "
                    f"SELECT * FROM read_json_auto('{posix}')"
                )
            else:
                record["logs"].append(f"[load] SKIP {rel_path} — unsupported extension {suffix}")
                continue

            # Infer columns
            cols_result = conn.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE UPPER(table_schema)='RAW' AND UPPER(table_name)=UPPER('{table_name}')"
            ).fetchall()
            cols = [{"name": r[0], "type": r[1]} for r in cols_result]
            row_count = conn.execute(f"SELECT COUNT(*) FROM RAW.{table_name}").fetchone()[0]

            tables_loaded[table_name] = cols
            record["logs"].append(f"[load] raw.{table_name.lower()} — {row_count} rows, {len(cols)} cols from {abs_path.name}")
        except Exception as exc:
            record["logs"].append(f"[load] ERROR loading {abs_path.name}: {exc}")

    conn.close()
    return {"catalog_path": catalog_path_rel, "tables": tables_loaded, "files_processed": len(file_paths)}


def handle_get_data_dictionary(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Return column stats for all RAW tables in catalog.duckdb.

    Args:
        catalog_path: path relative to WORKSPACES_ROOT
        summary_only: if True, return table names only (no per-column stats)
    """
    catalog_path_rel = args.get("catalog_path", "")
    summary_only = args.get("summary_only", False)

    if not catalog_path_rel:
        raise HTTPException(status_code=400, detail="catalog_path is required")

    catalog_abs = (WORKSPACES_ROOT / catalog_path_rel).resolve()
    if not catalog_abs.exists():
        return {"tables": {}, "catalog_path": catalog_path_rel}

    conn = duckdb.connect(str(catalog_abs), read_only=True)

    tables_result = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE UPPER(table_schema)='RAW'"
    ).fetchall()
    table_names = [r[0] for r in tables_result]

    if summary_only:
        conn.close()
        return {"tables": {t: [] for t in table_names}, "catalog_path": catalog_path_rel}

    tables: Dict[str, Any] = {}
    for tbl in table_names:
        try:
            row_count = conn.execute(f"SELECT COUNT(*) FROM RAW.{tbl}").fetchone()[0]
            cols_result = conn.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE UPPER(table_schema)='RAW' AND UPPER(table_name)=UPPER('{tbl}')"
            ).fetchall()
            col_stats = []
            for col_name, col_type in cols_result:
                stat: Dict[str, Any] = {"name": col_name, "type": col_type}
                try:
                    null_count = conn.execute(
                        f'SELECT COUNT(*) FROM RAW.{tbl} WHERE "{col_name}" IS NULL'
                    ).fetchone()[0]
                    stat["null_count"] = null_count
                    stat["null_pct"] = round(null_count / row_count * 100, 1) if row_count else 0
                except Exception:
                    pass
                col_stats.append(stat)
            tables[tbl] = {"row_count": row_count, "columns": col_stats}
        except Exception as exc:
            tables[tbl] = {"error": str(exc)}

    conn.close()
    record["logs"].append(f"[data_dict] {len(tables)} tables analysed")
    return {"tables": tables, "catalog_path": catalog_path_rel}


def handle_data_preview(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Return up to 20 rows from a RAW table in catalog.duckdb.

    The workspace arg here is the catalog path relative to WORKSPACES_ROOT
    (the route passes catalog_rel directly as the workspace arg).
    """
    table_name = args.get("table_name", "")
    limit = min(int(args.get("limit", 20)), 100)

    if not table_name:
        raise HTTPException(status_code=400, detail="table_name is required")

    # workspace is the catalog path in this handler
    catalog_abs = (WORKSPACES_ROOT / workspace).resolve()
    if not str(catalog_abs).startswith(str(WORKSPACES_ROOT)):
        raise HTTPException(status_code=400, detail="catalog_path outside root")
    if not catalog_abs.exists():
        raise HTTPException(status_code=404, detail="catalog not found — run data ingestion first")

    conn = duckdb.connect(str(catalog_abs), read_only=True)
    try:
        safe_table = re.sub(r"[^A-Za-z0-9_]", "", table_name)
        rel = conn.execute(f"SELECT * FROM RAW.{safe_table} LIMIT {limit}")
        columns = [d[0] for d in rel.description]
        rows = [dict(zip(columns, row)) for row in rel.fetchall()]
        conn.close()
    except Exception as exc:
        conn.close()
        raise HTTPException(status_code=400, detail=f"preview failed: {exc}")

    record["logs"].append(f"[preview] RAW.{table_name} — {len(rows)} rows")
    return {"table": table_name, "columns": columns, "rows": rows}


def handle_snowflake_provision(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Create per-tenant DuckDB schema. Idempotent via sentinel file."""
    tenant_key = args.get("tenant_key", "default")
    target_root = resolve_workspace(workspace)
    bootstrap_dir = target_root / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    sentinel = bootstrap_dir / "provision_done.json"

    if sentinel.exists():
        record["logs"].append(f"[provision] already done for {tenant_key}, skipping")
        return json.loads(sentinel.read_text())

    db_dir = target_root / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "factoria.duckdb"

    conn = duckdb.connect(str(db_path))
    schema_name = tenant_key.upper().replace("-", "_")
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    conn.execute("CREATE SCHEMA IF NOT EXISTS RAW")
    conn.close()

    result = {
        "tenant_key": tenant_key,
        "schema": schema_name,
        "db_path": str(db_path.relative_to(WORKSPACES_ROOT)),
        "provisioned_at": datetime.now(timezone.utc).isoformat(),
    }
    sentinel.write_text(json.dumps(result, indent=2))
    record["logs"].append(f"[provision] created schema {schema_name} in {db_path}")
    return result


def handle_snowflake_seed_demo_data(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Load fixture CSVs into RAW schema. Idempotent via sentinel file."""
    tenant_key = args.get("tenant_key", "default")
    target_root = resolve_workspace(workspace)
    bootstrap_dir = target_root / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    sentinel = bootstrap_dir / "seed_report.json"

    if sentinel.exists():
        record["logs"].append(f"[seed] already seeded for {tenant_key}, skipping")
        return json.loads(sentinel.read_text())

    conn = _get_or_create_db(target_root)

    orders_count = conn.execute("SELECT COUNT(*) FROM RAW.ORDERS").fetchone()[0]
    customers_count = conn.execute("SELECT COUNT(*) FROM RAW.CUSTOMERS").fetchone()[0]
    conn.close()

    result = {
        "tenant_key": tenant_key,
        "tables_seeded": ["RAW.ORDERS", "RAW.CUSTOMERS"],
        "row_counts": {"RAW.ORDERS": orders_count, "RAW.CUSTOMERS": customers_count},
        "seeded_at": datetime.now(timezone.utc).isoformat(),
    }
    sentinel.write_text(json.dumps(result, indent=2))
    record["logs"].append(f"[seed] RAW.ORDERS={orders_count} RAW.CUSTOMERS={customers_count}")
    return result


def handle_dbt_bootstrap(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Write dbt profiles.yml and dbt_project.yml stubs. Idempotent."""
    tenant_key = args.get("tenant_key", "default")
    dbt_repo_url = args.get("dbt_repo_url", "")
    target_root = resolve_workspace(workspace)
    bootstrap_dir = target_root / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)

    profiles_path = bootstrap_dir / "profiles.yml"
    project_path = bootstrap_dir / "dbt_project.yml"

    if profiles_path.exists() and project_path.exists():
        record["logs"].append(f"[dbt_bootstrap] already bootstrapped for {tenant_key}, skipping")
        return {"status": "skipped", "tenant_key": tenant_key}

    db_path = str((target_root / "db" / "factoria.duckdb").as_posix())

    profiles = {
        "factoria": {
            "target": "dev",
            "outputs": {
                "dev": {
                    "type": "duckdb",
                    "path": db_path,
                    "schema": "main",
                    "threads": 1,
                }
            },
        }
    }
    profiles_path.write_text(yaml.dump(profiles, default_flow_style=False))

    project_yml = f"""name: factoria
version: '1.0.0'
config-version: 2
profile: factoria
model-paths: ["models"]
test-paths: ["tests"]
target-path: "target"
clean-targets: ["target", "dbt_packages"]
models:
  factoria:
    materialized: table
"""
    project_path.write_text(project_yml)
    record["logs"].append(f"[dbt_bootstrap] wrote profiles.yml and dbt_project.yml for {tenant_key}")

    return {
        "status": "bootstrapped",
        "tenant_key": tenant_key,
        "dbt_repo_url": dbt_repo_url,
        "profiles_path": str(profiles_path.relative_to(WORKSPACES_ROOT)),
        "project_path": str(project_path.relative_to(WORKSPACES_ROOT)),
    }


def handle_dbt_smoke(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Run a smoke query against RAW.ORDERS. Writes smoke_result.json."""
    tenant_key = args.get("tenant_key", "default")
    target_root = resolve_workspace(workspace)
    bootstrap_dir = target_root / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    sentinel = bootstrap_dir / "smoke_result.json"

    if sentinel.exists():
        record["logs"].append(f"[dbt_smoke] already ran for {tenant_key}, skipping")
        return json.loads(sentinel.read_text())

    conn = _get_or_create_db(target_root)
    try:
        row = conn.execute("SELECT COUNT(*) AS order_count FROM RAW.ORDERS").fetchone()
        order_count = row[0] if row else 0
        conn.close()
    except Exception as exc:
        conn.close()
        raise HTTPException(status_code=500, detail=f"smoke query failed: {exc}")

    result = {
        "tenant_key": tenant_key,
        "query": "SELECT COUNT(*) AS order_count FROM RAW.ORDERS",
        "order_count": order_count,
        "status": "passed",
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    sentinel.write_text(json.dumps(result, indent=2))
    record["logs"].append(f"[dbt_smoke] order_count={order_count} — passed")
    return result


def handle_echo(args: Dict[str, Any], record: Dict[str, Any]):
    message = args.get("message", "")
    record["logs"].append(message)
    return {"message": message}


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def resolve_workspace(workspace: str) -> Path:
    if not workspace:
        raise HTTPException(status_code=400, detail="workspace missing")

    target = (WORKSPACES_ROOT / workspace).resolve()

    if not str(target).startswith(str(WORKSPACES_ROOT)):
        raise HTTPException(status_code=400, detail="workspace outside root")

    target.mkdir(parents=True, exist_ok=True)
    return target


def validate_relative_path(path: str) -> Path:
    candidate = Path(path)

    if candidate.is_absolute() or ".." in candidate.parts:
        raise HTTPException(status_code=400, detail="invalid file path")

    return candidate
