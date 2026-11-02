"""
Projects router — CRUD for processing jobs.
POST /api/projects  → ingest source + queue Celery pipeline
GET  /api/projects  → list with status
GET  /api/projects/{id} → full detail with clips
DELETE /api/projects/{id}
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from api.database import get_session
from api.db_models import Project, Job, Clip
from api.schemas import ProjectCreate, ProjectRead, ProjectList

router = APIRouter()


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new project and immediately queue the Clipedics pipeline via Celery.
    Returns the project with status='queued'.
    """
    project = Project(
        input_source=body.input_source,
        title=f"Project — {body.input_source[:60]}",
        status="queued",
    )
    db.add(project)
    await db.flush()

    job = Job(project_id=project.id, status="queued", step="waiting")
    db.add(job)
    await db.commit()
    await db.refresh(project)
    await db.refresh(job)

    # Queue Celery task (import here to avoid circular imports at startup)
    try:
        from workers.pipeline import run_pipeline
        celery_result = run_pipeline.delay(
            project_id=project.id,
            job_id=job.id,
            input_source=body.input_source,
            num_clips=body.num_clips,
            min_seconds=body.min_seconds,
            max_seconds=body.max_seconds,
            subtitle_style=body.subtitle_style or "hormozi",
            reframe=body.reframe if body.reframe is not None else True,
            whisper_model=body.whisper_model,
        )
        # Persist Celery task ID
        job.celery_task_id = celery_result.id
        await db.commit()
    except Exception as e:
        # If Celery/Redis not available, mark as error but still return project
        project.status = "error"
        project.error_message = f"Failed to queue task: {e}"
        await db.commit()

    # Re-fetch with clips (empty at this point)
    return await _get_project_full(project.id, db)


@router.get("", response_model=list[ProjectList])
async def list_projects(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
):
    """List projects ordered by newest first."""
    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit)
    )
    projects = result.scalars().all()

    out = []
    for p in projects:
        count_result = await db.execute(
            select(func.count()).select_from(Clip).where(Clip.project_id == p.id)
        )
        clips_count = count_result.scalar() or 0
        out.append(ProjectList(
            id=p.id,
            title=p.title,
            video_title=p.video_title,
            status=p.status,
            created_at=p.created_at,
            clips_count=clips_count,
        ))
    return out


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, db: AsyncSession = Depends(get_session)):
    """Get a single project with all its clips."""
    return await _get_project_full(project_id, db)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_session)):
    """Delete a project and all its clips/jobs (cascade)."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_project_full(project_id: str, db: AsyncSession) -> ProjectRead:
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    clips_result = await db.execute(
        select(Clip).where(Clip.project_id == project_id).order_by(Clip.clip_number)
    )
    clips = clips_result.scalars().all()

    job_result = await db.execute(
        select(Job).where(Job.project_id == project_id).order_by(Job.created_at.desc())
    )
    latest_job = job_result.scalars().first()

    return ProjectRead(
        id=project.id,
        title=project.title,
        input_source=project.input_source,
        video_title=project.video_title,
        status=project.status,
        error_message=project.error_message,
        job_progress=latest_job.progress if latest_job else 0,
        job_step=latest_job.step if latest_job else project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        clips=[_clip_to_schema(c) for c in clips],
    )


def _clip_to_schema(c: Clip):
    from api.schemas import ClipRead
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

