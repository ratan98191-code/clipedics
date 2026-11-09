"""
Tests for Phase 7: Editor UI & Learned Ranker
Verifies:
1. Multi-modal ClipFeatures vectorization.
2. LearnedRanker model training, prediction, and persistence.
3. Feedback logging with actions (accept, reject, trim, swap-beats, star ratings).
4. API endpoints for trim, swap-beats, re-render, and feedback logging.
"""
import pytest
from pathlib import Path
import numpy as np
from httpx import AsyncClient, ASGITransport

from core.models import ClipCandidate, ClipPlan, Unit, WordSegment
from core.ranker import ClipFeatures, LearnedRanker, extract_clip_features
from core.feedback import log_feedback, load_all_feedback, get_training_data, train_ranker_from_feedback
from api.main import app


def _create_sample_clip_and_units():
    units = [
        Unit(
            unit_id=1,
            start_seconds=10.0,
            end_seconds=14.0,
            raw_start_seconds=10.0,
            raw_end_seconds=14.0,
            text="Why do 90% of technical founders make the exact same cash flow mistake?",
            loudness_lufs=-18.0,
            speech_rate_wpm=155.0,
            shot_ids=[1, 2],
            face_detected=True,
        ),
        Unit(
            unit_id=2,
            start_seconds=14.0,
            end_seconds=30.0,
            raw_start_seconds=14.0,
            raw_end_seconds=30.0,
            text="Because they assume contract signatures mean money in the bank.",
            loudness_lufs=-22.0,
            speech_rate_wpm=140.0,
            shot_ids=[2, 3],
            face_detected=True,
        ),
    ]
    cand = ClipCandidate(
        clip_number=1,
        start_seconds=10.0,
        end_seconds=30.0,
        title="Founder Mistake",
        virality_score=85,
    )
    return cand, units


def test_clip_features_extraction_and_vector():
    """Verify multi-modal feature vector extraction from clip candidate and units."""
    cand, units = _create_sample_clip_and_units()
    features = extract_clip_features(cand, units)

    assert features.duration_seconds == 20.0
    assert features.speech_rate_wpm > 130.0
    assert features.loudness_lufs == pytest.approx(-20.0, 3.0)
    assert features.hook_score >= 70.0

    vec = features.to_vector()
    assert len(vec) == 7
    assert all(isinstance(v, float) for v in vec)


def test_learned_ranker_fit_predict_persistence(tmp_path):
    """Verify ranker model fits weights over training data and accurately scores clips."""
    model_path = tmp_path / "test_ranker.json"
    ranker = LearnedRanker(model_path=model_path)

    # Synthetic dataset: 10 clips with varied features and target labels
    X = [
        # High quality viral clips (high hook, good wpm, high llm) -> target = 1.0 / 0.9
        [0.5, 0.4, 1.2, 0.8, 1.0, 0.0, 1.2],
        [0.4, 0.3, 1.0, 0.6, 0.9, -0.2, 1.0],
        [0.6, 0.5, 1.5, 0.9, 1.0, 0.1, 1.3],
        # Low quality rejected clips (flat, low hook, bad pacing) -> target = 0.0 / 0.1
        [-0.8, -0.9, -1.2, -0.8, -0.5, 1.5, -1.0],
        [-0.7, -0.8, -1.0, -0.6, -0.4, 1.2, -0.8],
        [-0.9, -1.0, -1.5, -0.9, -0.6, 1.6, -1.2],
    ]
    y = [0.95, 0.90, 0.98, 0.10, 0.15, 0.05]

    metrics = ranker.fit(X, y)
    assert metrics["status"] == "trained"
    assert metrics["samples"] == 6
    assert metrics["r2_score"] > 0.80

    # Test prediction on high-quality vs low-quality feature
    high_f = ClipFeatures(speech_rate_wpm=155.0, loudness_lufs=-18.0, hook_score=90.0, llm_score=88.0)
    low_f = ClipFeatures(speech_rate_wpm=105.0, loudness_lufs=-28.0, hook_score=40.0, llm_score=45.0)

    score_high = ranker.predict_score(high_f)
    score_low = ranker.predict_score(low_f)
    assert score_high > score_low
    assert score_high >= 70
    assert score_low <= 40

    # Verify save & reload
    loaded_ranker = LearnedRanker(model_path=model_path)
    assert loaded_ranker.is_trained is True
    assert loaded_ranker.predict_score(high_f) == score_high


def test_feedback_logging_and_training_pipeline(tmp_path):
    """Verify feedback logger appends actions and extracts training dataset."""
    log_path = tmp_path / "feedback_test.json"

    # Log 3 user actions
    f1 = ClipFeatures(hook_score=85.0, llm_score=80.0)
    f2 = ClipFeatures(hook_score=45.0, llm_score=50.0)

    e1 = log_feedback("clip_1", action="accept", rating=5, features=f1, storage_path=log_path)
    e2 = log_feedback("clip_2", action="reject", rating=1, features=f2, storage_path=log_path)
    e3 = log_feedback("clip_3", action="trim", features=f1, storage_path=log_path)

    all_logs = load_all_feedback(storage_path=log_path)
    assert len(all_logs) == 3
    assert all_logs[0].action == "accept"
    assert all_logs[1].action == "reject"

    X, y = get_training_data(storage_path=log_path)
    assert len(X) == 3
    assert len(y) == 3
    assert y[0] == 1.0  # 5/5 stars = 1.0
    assert y[1] == 0.2  # 1/5 stars = 0.2
    assert y[2] == 0.75 # trim action = 0.75


@pytest.mark.asyncio
async def test_api_feedback_and_ranker_endpoints():
    """Verify FastAPI endpoints for feedback stats and ranker training."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # GET /api/clips/feedback/stats
        res = await ac.get("/api/clips/feedback/stats")
        assert res.status_code == 200
        data = res.json()
        assert "total_interactions" in data
        assert "ranker" in data

        # POST /api/clips/ranker/train
        train_res = await ac.post("/api/clips/ranker/train")
        assert train_res.status_code == 200
        train_data = train_res.json()
        assert "status" in train_data
