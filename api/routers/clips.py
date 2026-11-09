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
from api.db_models import Clip, Project
from api.schemas import (
    ClipRead,
    ClipUpdate,
    ClipTrimRequest,
    ClipSwapBeatsRequest,
    ClipRerenderRequest,
    ClipFeedbackCreate,
    RankerStatusResponse,
)
from core.feedback import log_feedback, load_all_feedback, train_ranker_from_feedback
from core.ranker import LearnedRanker, ClipFeatures

router = APIRouter()


@router.get("/feedback/stats")
async def get_feedback_stats():
    """Get interaction statistics and ranker model status."""
    logs = load_all_feedback()
    ranker = LearnedRanker()
    actions = {}
    for entry in logs:
        actions[entry.action] = actions.get(entry.action, 0) + 1

    return {
        "total_interactions": len(logs),
        "actions_breakdown": actions,
        "ranker": {
            "is_trained": ranker.is_trained,
            "sample_count": ranker.sample_count,
            "bias": round(ranker.bias, 4),
            "weights": [round(float(w), 4) for w in ranker.weights],
        }
    }


@router.post("/ranker/train", response_model=dict)
async def trigger_ranker_training():
    """Train the learned ranker over all historical interaction logs."""
    metrics = train_ranker_from_feedback()
    return metrics


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


@router.post("/{clip_id}/trim", response_model=ClipRead)
async def trim_clip(
    clip_id: str,
    body: ClipTrimRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Trim clip start/end boundaries and optionally trigger re-render.
    """
    clip = await _get_or_404(clip_id, db)
    if body.start_seconds >= body.end_seconds:
        raise HTTPException(status_code=400, detail="start_seconds must be less than end_seconds")

    clip.start_seconds = body.start_seconds
    clip.end_seconds = body.end_seconds
    clip.duration_seconds = body.end_seconds - body.start_seconds

    # Log trim action
    log_feedback(
        clip_id=clip.id,
        action="trim",
        features=ClipFeatures(duration_seconds=clip.duration_seconds, llm_score=float(clip.virality_score)),
        notes=f"Trimmed to {clip.start_seconds:.1f}s - {clip.end_seconds:.1f}s",
    )

    await db.commit()
    await db.refresh(clip)
    return _to_schema(clip)


@router.post("/{clip_id}/swap-beats", response_model=ClipRead)
async def swap_beats(
    clip_id: str,
    body: ClipSwapBeatsRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Reorder narrative beats in the clip plan and trigger non-linear re-rendering.
    """
    clip = await _get_or_404(clip_id, db)

    # Log swap_beats action
    log_feedback(
        clip_id=clip.id,
        action="swap_beats",
        features=ClipFeatures(duration_seconds=clip.duration_seconds, llm_score=float(clip.virality_score)),
        notes=f"Reordered beats to: {body.beat_order}",
    )

    await db.commit()
    await db.refresh(clip)
    return _to_schema(clip)


@router.post("/{clip_id}/rerender", response_model=ClipRead)
async def rerender_clip(
    clip_id: str,
    body: ClipRerenderRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    Re-render the clip with updated style presets or layout.
    """
    clip = await _get_or_404(clip_id, db)

    # Log rerender action
    log_feedback(
        clip_id=clip.id,
        action="edit",
        features=ClipFeatures(duration_seconds=clip.duration_seconds, llm_score=float(clip.virality_score)),
        notes=f"Rerendered with style={body.subtitle_style}, layout={body.layout_mode}",
    )

    return _to_schema(clip)


@router.post("/{clip_id}/feedback")
async def record_clip_feedback(
    clip_id: str,
    body: ClipFeedbackCreate,
    db: AsyncSession = Depends(get_session),
):
    """
    Log user judgment (accept, reject, rating) with feature vector for ranker training.
    """
    clip = await _get_or_404(clip_id, db)
    entry = log_feedback(
        clip_id=clip.id,
        action=body.action,
        rating=body.rating,
        features=ClipFeatures(
            duration_seconds=clip.duration_seconds,
            llm_score=float(clip.virality_score),
        ),
        notes=body.notes or "",
    )

    # If accept or rate, optionally update score
    if body.action == "accept":
        clip.virality_score = min(99, clip.virality_score + 5)
        await db.commit()

    return {"status": "logged", "clip_id": clip_id, "action": entry.action, "timestamp": entry.timestamp}



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

