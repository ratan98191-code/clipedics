"""
Jobs router — SSE real-time progress stream + JSON status snapshot.

GET /api/jobs/{id}         → Server-Sent Events stream (real-time progress)
GET /api/jobs/{id}/status  → JSON snapshot (polling fallback)
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.database import get_session
from api.db_models import Job
from api.schemas import JobRead

router = APIRouter()


@router.get("/{job_id}/status", response_model=JobRead)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_session)):
    """Polling endpoint — returns current job state as JSON."""
    job = await _get_or_404(job_id, db)
    return JobRead.model_validate(job)


@router.get("/{job_id}")
async def stream_job(job_id: str, db: AsyncSession = Depends(get_session)):
    """
    Server-Sent Events stream — pushes progress updates every 2 seconds.
    Clients subscribe and get live step/progress data without polling.

    Event format:
      data: {"status": "rendering", "progress": 72, "step": "Rendering clip 3/5"}
    """
    # Validate job exists first
    job = await _get_or_404(job_id, db)

    async def event_generator():
        terminal_states = {"done", "error"}
        while True:
            # Re-fetch fresh state each iteration (async session can't be shared across awaits)
            async with db.begin():
                result = await db.execute(select(Job).where(Job.id == job_id))
                current = result.scalar_one_or_none()

            if current is None:
                yield _sse_event({"error": "Job not found"})
                break

            payload = {
                "job_id": current.id,
                "project_id": current.project_id,
                "status": current.status,
                "progress": current.progress,
                "step": current.step,
                "updated_at": current.updated_at.isoformat() if current.updated_at else None,
            }
            yield _sse_event(payload)

            if current.status in terminal_states:
                break

            await asyncio.sleep(2)  # poll DB every 2s (Vizard-style)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Nginx: disable buffering
        },
    )


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_or_404(job_id: str, db: AsyncSession) -> Job:
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

