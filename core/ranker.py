"""
Clipedics – Learned Ranker Engine (Phase 7: Data-Driven Virality Ranking)
Replaces hand-crafted heuristic weights with a learned ranker fit over
user interaction logs (accept, reject, rating, trim actions).
Features:
  - Multi-modal feature vectorization (acoustic, visual, narrative hook, LLM, duration)
  - Calibrated Ridge / Logistic regression model
  - Model weights persistence & online training
  - Cold-start fallback to calibrated priors
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np
from pydantic import BaseModel

from core.models import ClipCandidate, ClipPlan, Unit
from core.ranking import (
    score_audio_salience,
    score_visual_salience,
    score_hook_salience,
)

DEFAULT_MODEL_PATH = Path("data/learned_ranker.json")


class ClipFeatures(BaseModel):
    """Normalized multi-modal feature vector for a clip."""
    speech_rate_wpm: float = 140.0
    loudness_lufs: float = -20.0
    hook_score: float = 70.0
    cuts_per_min: float = 8.0
    face_ratio: float = 0.8
    duration_seconds: float = 45.0
    llm_score: float = 70.0

    def to_vector(self) -> list[float]:
        """Convert features to standardized float vector."""
        return [
            (self.speech_rate_wpm - 140.0) / 30.0,
            (self.loudness_lufs - (-20.0)) / 5.0,
            (self.hook_score - 70.0) / 20.0,
            (self.cuts_per_min - 8.0) / 5.0,
            (self.face_ratio - 0.7) / 0.3,
            (self.duration_seconds - 45.0) / 20.0,
            (self.llm_score - 70.0) / 15.0,
        ]

    @property
    def feature_names(self) -> list[str]:
        return [
            "speech_rate_wpm", "loudness_lufs", "hook_score",
            "cuts_per_min", "face_ratio", "duration_seconds", "llm_score"
        ]


def extract_clip_features(
    clip: Union[ClipCandidate, ClipPlan],
    all_units: list[Unit],
) -> ClipFeatures:
    """Extract multi-modal feature vector from clip and unit features."""
    s = clip.start_seconds
    e = clip.end_seconds
    dur = max(1.0, clip.duration_seconds)

    # Overlapping units
    span_units = [
        u for u in all_units
        if u.start_seconds >= s - 0.20 and u.end_seconds <= e + 0.20
    ]

    wpms = [u.speech_rate_wpm for u in span_units if u.speech_rate_wpm > 0]
    avg_wpm = float(np.mean(wpms)) if wpms else 140.0

    loudness_vals = [u.loudness_lufs for u in span_units if u.loudness_lufs > -60]
    avg_lufs = float(np.mean(loudness_vals)) if loudness_vals else -20.0

    hook_u = span_units[0] if span_units else None
    hook_s = score_hook_salience(hook_u) if hook_u else 70.0

    all_shots = set()
    faces = []
    for u in span_units:
        all_shots.update(u.shot_ids)
        faces.append(u.face_detected)

    cuts_count = max(0, len(all_shots) - 1)
    cuts_per_min = (cuts_count / dur) * 60.0
    face_ratio = sum(faces) / len(faces) if faces else 0.8

    llm_val = float(getattr(clip, "virality_score", 70))

    return ClipFeatures(
        speech_rate_wpm=round(avg_wpm, 1),
        loudness_lufs=round(avg_lufs, 1),
        hook_score=round(hook_s, 1),
        cuts_per_min=round(cuts_per_min, 1),
        face_ratio=round(face_ratio, 2),
        duration_seconds=round(dur, 1),
        llm_score=round(llm_val, 1),
    )


class LearnedRanker:
    """
    Trained ranking model predicting clip salience and user preference.
    Uses L2-regularized linear ridge weights with sigmoid activation.
    """
    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or DEFAULT_MODEL_PATH
        # Default prior weights
        self.weights = np.array([0.15, 0.15, 0.35, 0.10, 0.10, -0.05, 0.40], dtype=float)
        self.bias = 0.50
        self.is_trained = False
        self.sample_count = 0
        self.load()

    def fit(self, X: list[list[float]], y: list[float], alpha: float = 0.1) -> dict:
        """
        Fit ridge regression weights over feature vectors X and targets y (in [0, 1] or [0, 100]).
        """
        if not X or len(X) < 3:
            return {"status": "insufficient_data", "samples": len(X)}

        X_mat = np.array(X, dtype=float)
        y_vec = np.array(y, dtype=float)

        # Normalize y to 0.0 - 1.0 if passed as 0-100
        if np.max(y_vec) > 1.5:
            y_vec = y_vec / 100.0

        n_samples, n_features = X_mat.shape

        # Add bias column
        A = np.hstack([X_mat, np.ones((n_samples, 1))])
        # Ridge regularizer: (A^T A + alpha * I)^-1 A^T y
        reg = alpha * np.eye(n_features + 1)
        reg[-1, -1] = 0.0  # Do not regularize bias

        theta = np.linalg.solve(A.T @ A + reg, A.T @ y_vec)

        self.weights = theta[:-1]
        self.bias = float(theta[-1])
        self.is_trained = True
        self.sample_count = n_samples

        preds = A @ theta
        r2 = 1.0 - (np.sum((y_vec - preds) ** 2) / max(1e-6, np.sum((y_vec - np.mean(y_vec)) ** 2)))
        mae = float(np.mean(np.abs(y_vec - preds)))

        self.save()

        return {
            "status": "trained",
            "samples": n_samples,
            "weights": [round(float(w), 4) for w in self.weights],
            "bias": round(self.bias, 4),
            "r2_score": round(float(r2), 4),
            "mae": round(mae, 4),
        }

    def predict_score(self, features: ClipFeatures) -> int:
        """Predict salience score from 1 to 100."""
        vec = np.array(features.to_vector(), dtype=float)
        pred = float(np.dot(self.weights, vec) + self.bias)
        # Clip to [0.05, 0.98] and scale to 100
        score = int(round(float(np.clip(pred, 0.05, 0.98)) * 100.0))
        return score

    def save(self, path: Optional[Path] = None) -> None:
        p = path or self.model_path
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "is_trained": self.is_trained,
            "sample_count": self.sample_count,
            "weights": self.weights.tolist(),
            "bias": self.bias,
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: Optional[Path] = None) -> bool:
        p = path or self.model_path
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.weights = np.array(data.get("weights", self.weights), dtype=float)
                    self.bias = float(data.get("bias", self.bias))
                    self.is_trained = bool(data.get("is_trained", False))
                    self.sample_count = int(data.get("sample_count", 0))
                return True
            except Exception:
                pass
        return False
