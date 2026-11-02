"""
Clipedics – Celery Application Factory
Broker: Redis (default redis://localhost:6379/0)
Result backend: Redis
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "clipedics",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.pipeline"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,   # one task at a time (GPU-heavy)
    task_acks_late=True,            # ack after completion, survive crashes
    result_expires=86400,           # 24h result retention
)

