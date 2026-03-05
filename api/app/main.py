from fastapi import FastAPI
from app.routes.health import router as health_router

app = FastAPI(title="Factoria API")

app.include_router(health_router)

@app.get("/")
def root():
    return {"service": "factoria-api"}