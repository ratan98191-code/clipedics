"""
Clipedics – Database Session Factory
Supports SQLite (dev) and Postgres (prod) via DATABASE_URL env var.
"""
from __future__ import annotations
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from api.db_models import Base

# ── URL resolution ────────────────────────────────────────────────────────────
# Dev default: async SQLite
_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./clipedics.db")
# Celery tasks need a sync engine (no async)
_SYNC_URL = _DATABASE_URL.replace("sqlite+aiosqlite", "sqlite").replace("postgresql+asyncpg", "postgresql+psycopg2")

# ── Async engine (FastAPI) ────────────────────────────────────────────────────
async_engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in _DATABASE_URL else {},
)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Sync engine (Celery workers) ──────────────────────────────────────────────
sync_engine = create_engine(
    _SYNC_URL,
    connect_args={"check_same_thread": False} if "sqlite" in _SYNC_URL else {},
)


async def init_db() -> None:
    """Create all tables (dev/test). In prod, use Alembic migrations."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session() -> Session:
    """Celery dependency: yields a sync DB session."""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(sync_engine, expire_on_commit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

