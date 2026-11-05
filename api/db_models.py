"""
Clipedics – SQLAlchemy Database Models
Defines: User, Project, Clip, Job tables.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ── User ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Billing
    plan: Mapped[str] = mapped_column(String(32), default="free")
    # free | pro | agency
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subscription_status: Mapped[str] = mapped_column(String(32), default="inactive")
    # inactive | active | past_due | canceled
    clips_used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    quota_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    projects: Mapped[list["Project"]] = relationship("Project", back_populates="user", cascade="all, delete-orphan")


# ── Project ───────────────────────────────────────────────────────────────────

class Project(Base):
    """One processing run for a video source."""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="Untitled Project")
    input_source: Mapped[str] = mapped_column(Text)          # URL or file path
    video_title: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # pending | queued | downloading | transcribing | clipping | rendering | done | error
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="projects")
    clips: Mapped[list["Clip"]] = relationship("Clip", back_populates="project", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="project", cascade="all, delete-orphan")


# ── Clip ──────────────────────────────────────────────────────────────────────

class Clip(Base):
    """A single generated clip within a project."""
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    clip_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512), default="")
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    virality_score: Mapped[int] = mapped_column(Integer, default=0)
    virality_rationale: Mapped[str] = mapped_column(Text, default="")
    hook_sentence: Mapped[str] = mapped_column(Text, default="")
    suggested_caption: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[list] = mapped_column(JSON, default=list)
    raw_mp4_path: Mapped[str] = mapped_column(Text, default="")
    output_mp4_path: Mapped[str] = mapped_column(Text, default="")
    thumbnail_path: Mapped[str] = mapped_column(Text, default="")
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped["Project"] = relationship("Project", back_populates="clips")

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


# ── Job ───────────────────────────────────────────────────────────────────────

class Job(Base):
    """Celery background job tracking."""
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)       # 0–100
    step: Mapped[str] = mapped_column(String(128), default="")      # current step label
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    project: Mapped["Project"] = relationship("Project", back_populates="jobs")
