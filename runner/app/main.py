from fastapi import FastAPI

app = FastAPI(title="Factoria Runner")

@app.get("/health")
def health():
    return {"runner": "ok"}

@app.post("/run")
def run_job(job: dict):
    return {
        "status": "received",
        "job": job
    }