"""
Clipedics – Editorial Feedback & Interaction Logging (Phase 7: Human-in-the-Loop)
Records user actions (accept, reject, trim, swap-beats, ratings) alongside
multi-modal feature vectors to feed the online learned ranker.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from pydantic import BaseModel

from core.ranker import ClipFeatures, LearnedRanker

FEEDBACK_FILE = Path("data/feedback_logs.json")


class FeedbackEntry(BaseModel):
    """A single logged user action with attached features."""
    clip_id: str
    action: str                        # "accept" | "reject" | "edit" | "trim" | "swap_beats" | "rate"
    rating: Optional[int] = None       # 1 to 5 stars
    features: Optional[ClipFeatures] = None
    notes: Optional[str] = ""
    timestamp: str = ""

    def target_value(self) -> float:
        """Map action or rating to 0.0 - 1.0 target for training."""
        if self.rating is not None:
            return float(self.rating) / 5.0
        if self.action in ("accept", "download", "export"):
            return 1.0
        if self.action == "reject":
            return 0.0
        if self.action in ("edit", "trim", "swap_beats"):
            return 0.75  # Kept with modifications
        return 0.50


def log_feedback(
    clip_id: str,
    action: str,
    rating: Optional[int] = None,
    features: Optional[ClipFeatures] = None,
    notes: str = "",
    storage_path: Optional[Path] = None,
) -> FeedbackEntry:
    """Record an interaction event to persistent JSON storage."""
    path = storage_path or FEEDBACK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = FeedbackEntry(
        clip_id=clip_id,
        action=action,
        rating=rating,
        features=features or ClipFeatures(),
        notes=notes,
        timestamp=datetime.now().isoformat(),
    )

    all_logs = load_all_feedback(path)
    all_logs.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump([e.model_dump() for e in all_logs], f, indent=2)

    return entry


def load_all_feedback(storage_path: Optional[Path] = None) -> list[FeedbackEntry]:
    """Load all historical feedback entries from disk."""
    path = storage_path or FEEDBACK_FILE
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [FeedbackEntry.model_validate(d) for d in data]
    except Exception:
        return []


def get_training_data(storage_path: Optional[Path] = None) -> tuple[list[list[float]], list[float]]:
    """Convert logged feedback into X feature vectors and y targets."""
    entries = load_all_feedback(storage_path)
    X = []
    y = []
    for e in entries:
        if e.features:
            X.append(e.features.to_vector())
            y.append(e.target_value())
    return X, y


def train_ranker_from_feedback(storage_path: Optional[Path] = None) -> dict:
    """Train the learned ranker over all logged feedback."""
    X, y = get_training_data(storage_path)
    ranker = LearnedRanker()
    metrics = ranker.fit(X, y)
    return metrics
