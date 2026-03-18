from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import health, tickets, workflows, artifacts, sessions, tenants
from app.db import create_db_and_tables

app = FastAPI(
    title="Factoria API",
    version="0.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


app.include_router(health.router)
app.include_router(tickets.router)
app.include_router(workflows.router)
app.include_router(artifacts.router)
app.include_router(sessions.router)
app.include_router(tenants.router)