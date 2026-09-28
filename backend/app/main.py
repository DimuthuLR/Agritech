"""
FastAPI application entry point.

Run locally with:
    ./py.bat -m uvicorn app.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before yield) and once at shutdown (after yield)."""
    print(f"[startup] {settings.app_name} booting in env={settings.app_env}")
    yield
    print("[shutdown] bye")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: allow the future Vue dev server (Vite on port 5173) to call this API.
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