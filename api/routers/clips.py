"""
Clips router — read/update individual clips, download rendered MP4.
GET   /api/clips/{id}          → clip metadata
PATCH /api/clips/{id}          → update title/caption/hashtags
GET   /api/clips/{id}/download → redirect to static MP4 file
"""
from __future__ import annotations
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.database import get_session
from api.db_models import Clip
from api.schemas import ClipRead, ClipUpdate

router = APIRouter()


@router.get("/{clip_id}", response_model=ClipRead)
async def get_clip(clip_id: str, db: AsyncSession = Depends(get_session)):
    clip = await _get_or_404(clip_id, db)
    return _to_schema(clip)


@router.patch("/{clip_id}", response_model=ClipRead)
async def update_clip(
    clip_id: str,
    body: ClipUpdate,
    db: AsyncSession = Depends(get_session),
):
    """Update editable fields on a clip."""
    clip = await _get_or_404(clip_id, db)
    if body.title is not None:
        clip.title = body.title
    if body.suggested_caption is not None:
        clip.suggested_caption = body.suggested_caption
    if body.hashtags is not None:
        clip.hashtags = body.hashtags
    await db.commit()
    await db.refresh(clip)
    return _to_schema(clip)


@router.get("/{clip_id}/download")
async def download_clip(clip_id: str, db: AsyncSession = Depends(get_session)):
    """Stream the rendered MP4 for download."""
    clip = await _get_or_404(clip_id, db)
    mp4_path = clip.output_mp4_path or clip.raw_mp4_path
    if not mp4_path or not Path(mp4_path).exists():
        raise HTTPException(status_code=404, detail="Clip file not found on disk")
    return FileResponse(
        mp4_path,
        media_type="video/mp4",
        filename=f"clip_{clip.clip_number}_{clip.title[:30]}.mp4",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(clip_id: str, db: AsyncSession) -> Clip:
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


def _to_schema(c: Clip) -> ClipRead:
    return ClipRead(
        id=c.id,
        project_id=c.project_id,
        clip_number=c.clip_number,
        title=c.title,
        start_seconds=c.start_seconds,
        end_seconds=c.end_seconds,
        duration_seconds=c.duration_seconds,
        virality_score=c.virality_score,
        virality_rationale=c.virality_rationale,
        hook_sentence=c.hook_sentence,
        suggested_caption=c.suggested_caption,
        hashtags=c.hashtags or [],
        raw_mp4_path=c.raw_mp4_path,
        output_mp4_path=c.output_mp4_path,
        thumbnail_path=c.thumbnail_path,
        success=c.success,
        error=c.error,
        created_at=c.created_at,
    )

