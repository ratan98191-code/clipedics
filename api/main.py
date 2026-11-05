"""
Clipedics – FastAPI Application Entry Point

Endpoints:
  POST   /api/projects          → Create project + queue Celery job
  GET    /api/projects          → List all projects
  GET    /api/projects/{id}     → Get project with clips
  DELETE /api/projects/{id}     → Delete project

  GET    /api/clips/{id}        → Get single clip metadata
  PATCH  /api/clips/{id}        → Update clip title/caption/hashtags
  GET    /api/clips/{id}/download → Redirect to output MP4

  GET    /api/jobs/{id}         → SSE stream of real-time progress
  GET    /api/jobs/{id}/status  → JSON snapshot of job status

  GET    /health                → Health check
"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.database import init_db
from api.routers import projects, clips, jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise DB tables."""
    await init_db()
    yield


app = FastAPI(
    title="Clipedics API",
    description="Personal AI video clip generator studio",
    version="0.5.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(clips.router, prefix="/api/clips", tags=["clips"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])

# ── Static output files (serve rendered clips directly) ───────────────────────
_OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
os.makedirs(_OUTPUT_DIR, exist_ok=True)
app.mount("/output", StaticFiles(directory=_OUTPUT_DIR), name="output")


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "mode": "personal", "version": "0.5.0"}


@app.get("/api/system/status", tags=["system"])
async def system_status():
    """Return local studio engine health and configuration status."""
    return {
        "status": "online",
        "mode": "personal_studio",
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "default_whisper_model": os.getenv("WHISPER_MODEL", "base"),
        "output_dir": os.path.abspath(os.getenv("OUTPUT_DIR", "./output")),
    }

