import os
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

    try:
        record["status"] = "running"

        if request.job == "workspace_write_files":
            record["result"] = handle_workspace_write_files(request.workspace, request.args, record)
        elif request.job == "echo":
            record["result"] = handle_echo(request.args, record)
        else:
            raise HTTPException(status_code=400, detail="unknown job")

        record["status"] = "succeeded"
    except HTTPException as exc:
        record["status"] = "failed"
        record["error"] = exc.detail
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        raise
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = str(exc)
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        raise HTTPException(status_code=500, detail="job failed") from exc

    record["finished_at"] = datetime.now(timezone.utc).isoformat()

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
    destination.write_text(content)
    written_files.append(str(destination.relative_to(WORKSPACES_ROOT)))
    record["logs"].append(f"wrote {destination}")

    return {"files_written": written_files}


def handle_echo(args: Dict[str, Any], record: Dict[str, Any]):

    message = args.get("message", "")
    record["logs"].append(message)

    return {"message": message}


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