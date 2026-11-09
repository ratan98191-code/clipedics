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
    """Create all tables (dev/test). In prod, use Alembic migrations.

    Also applies lightweight inline migrations for columns added without a
    full Alembic revision, so existing databases (which pre-date those columns)
    don't crash on SELECT.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_inline_migrations)


def _safe_add_column(conn, table: str, column: str, col_def: str) -> None:
    """ADD COLUMN if it does not already exist (SQLite + Postgres safe)."""
    try:
        import sqlalchemy
        conn.execute(sqlalchemy.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
        conn.commit()
    except Exception:
        pass  # column already exists or unsupported


def _apply_inline_migrations(conn) -> None:
    """Add any missing columns that were introduced without an Alembic migration.
    Idempotent: fails silently if the column already exists.
    """
    _safe_add_column(conn, "clips", "clip_plan_json", "TEXT DEFAULT NULL")


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

