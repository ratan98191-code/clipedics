"""
Clipedics – Pydantic API Schemas (Request / Response)
Separate from SQLAlchemy models in db_models.py.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ── Shared ────────────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Clip schemas ──────────────────────────────────────────────────────────────

class ClipRead(OrmBase):
    id: str
    project_id: str
    clip_number: int
    title: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    virality_score: int
    virality_rationale: str
    hook_sentence: str
    suggested_caption: str
    hashtags: list[str]
    raw_mp4_path: str
    output_mp4_path: str
    thumbnail_path: str
    success: bool
    error: str
    created_at: datetime


class ClipUpdate(BaseModel):
    title: Optional[str] = None
    suggested_caption: Optional[str] = None
    hashtags: Optional[list[str]] = None


# ── Project schemas ───────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    input_source: str           # YouTube URL or file path
    num_clips: Optional[int] = None
    min_seconds: Optional[int] = None
    max_seconds: Optional[int] = None
    subtitle_style: Optional[str] = "hormozi"
    reframe: Optional[bool] = True
    whisper_model: Optional[str] = None


class ProjectRead(OrmBase):
    id: str
    title: str
    input_source: str
    video_title: str
    status: str
    error_message: Optional[str]
    job_progress: Optional[int] = None
    job_step: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    clips: list[ClipRead] = []


class ProjectList(OrmBase):
    id: str
    title: str
    video_title: str
    status: str
    created_at: datetime
    clips_count: int = 0


# ── Job schemas ───────────────────────────────────────────────────────────────

class JobRead(OrmBase):
    id: str
    project_id: str
    celery_task_id: Optional[str]
    status: str
    progress: int
    step: str
    created_at: datetime
    updated_at: datetime

