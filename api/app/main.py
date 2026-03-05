from fastapi import FastAPI
from app.routes import health, tickets
from app.db import create_db_and_tables

app = FastAPI(
    title="Factoria API",
    version="0.1"
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()


app.include_router(health.router)
app.include_router(tickets.router)