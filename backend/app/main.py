"""
FastAPI application entry point.

Run locally with:
    ./py.bat -m uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db, engine
from app.api.v1.auth import router as auth_router
from app.api.v1.tenants import router as tenants_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before yield) and once at shutdown (after yield)."""
    print(f"[startup] {settings.app_name} booting in env={settings.app_env}")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[startup] database connection OK")
    except Exception as e:
        print(f"[startup] WARNING: database not reachable: {e}")
    yield
    print("[shutdown] bye")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe. Returns 200 if the process is up."""
    return {"status": "ok", "env": settings.app_env}


@app.get("/health/db", tags=["meta"])
async def health_db(db: Session = Depends(get_db)):
    """Deep health check: verifies we can round-trip a query to Postgres."""
    one = db.execute(text("SELECT 1")).scalar_one()
    server_time = db.execute(text("SELECT NOW()")).scalar_one()
    return {
        "db": "ok",
        "roundtrip": one,
        "server_time": server_time.isoformat(),
    }


# --- API v1 routers ---
app.include_router(auth_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")