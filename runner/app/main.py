import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

WORKSPACES_ROOT = Path(os.getenv("WORKSPACES_ROOT", "/workspace")).resolve()
ALLOWED_EXTENSIONS = {".sql", ".yml", ".yaml", ".md", ".json"}

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
    """Mock Snowflake SQL execution. Returns row data shaped like real profiling output."""
    query = args.get("query", "")
    connection = args.get("connection", "default")

    record["logs"].append(f"[snowflake:{connection}] executing query")
    record["logs"].append(f"  {query[:120]}{'...' if len(query) > 120 else ''}")

    # Derive mock results based on query content
    query_lower = query.lower()
    if "count" in query_lower and "null" in query_lower:
        rows = [{"column": "order_id", "null_count": 0, "total_count": 10000, "null_rate": 0.0}]
    elif "count(distinct" in query_lower:
        rows = [{"column": "customer_id", "distinct_count": 3500, "total_count": 10000}]
    elif "count(*)" in query_lower:
        rows = [{"row_count": 10000}]
    else:
        rows = [{"result": "ok"}]

    result = {
        "connection": connection,
        "query": query,
        "row_count": len(rows),
        "rows": rows,
        "execution_ms": 142,
    }

    # Write log to workspace
    target_root = resolve_workspace(workspace)
    logs_dir = target_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "snowflake_sql.json"
    existing = json.loads(log_file.read_text()) if log_file.exists() else []
    existing.append(result)
    log_file.write_text(json.dumps(existing, indent=2))
    record["logs"].append(f"wrote {log_file}")

    return result


def handle_dbt_compile(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Mock dbt compile. Writes outputs/compile_summary.json to workspace."""
    select = args.get("select", "")
    project_dir = args.get("project_dir", "dbt_changes")

    record["logs"].append(f"[dbt compile] select={select!r} project_dir={project_dir!r}")

    target_root = resolve_workspace(workspace)
    outputs_dir = target_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "status": "success",
        "select": select,
        "project_dir": project_dir,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "nodes_compiled": [select] if select else [],
        "errors": [],
    }

    summary_path = outputs_dir / "compile_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    record["logs"].append(f"wrote {summary_path}")

    rel = str(summary_path.relative_to(WORKSPACES_ROOT))
    return {"status": "success", "compile_summary_path": rel, "nodes_compiled": summary["nodes_compiled"]}


def handle_dbt_build(workspace: str, args: Dict[str, Any], record: Dict[str, Any]):
    """Mock dbt build. Writes outputs/run_results.json in dbt format to workspace."""
    select = args.get("select", "")
    project_dir = args.get("project_dir", "dbt_changes")

    record["logs"].append(f"[dbt build] select={select!r} project_dir={project_dir!r}")

    target_root = resolve_workspace(workspace)
    outputs_dir = target_root / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    node_id = f"model.factoria.{select}" if select else "model.factoria.unknown"
    run_results = {
        "metadata": {
            "dbt_schema_version": "https://schemas.getdbt.com/dbt/run-results/v4/manifest.json",
            "dbt_version": "1.7.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "invocation_id": str(uuid.uuid4()),
        },
        "args": {"select": [select], "project_dir": project_dir},
        "results": [
            {
                "status": "success",
                "timing": [
                    {"name": "compile", "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": datetime.now(timezone.utc).isoformat()},
                    {"name": "execute", "started_at": datetime.now(timezone.utc).isoformat(), "completed_at": datetime.now(timezone.utc).isoformat()},
                ],
                "thread_id": "Thread-1",
                "execution_time": 1.23,
                "adapter_response": {"_message": "SUCCESS 1", "rows_affected": 1},
                "message": "SUCCESS 1",
                "failures": None,
                "unique_id": node_id,
            }
        ],
        "elapsed_time": 1.45,
    }

    results_path = outputs_dir / "run_results.json"
    results_path.write_text(json.dumps(run_results, indent=2))
    record["logs"].append(f"wrote {results_path}")

    rel = str(results_path.relative_to(WORKSPACES_ROOT))
    passed = sum(1 for r in run_results["results"] if r["status"] == "success")
    failed = sum(1 for r in run_results["results"] if r["status"] != "success")
    return {"status": "success", "run_results_path": rel, "passed": passed, "failed": failed}


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
