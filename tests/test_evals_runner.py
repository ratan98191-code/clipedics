"""
Tests for evals.run runner and metric signatures.
Ensures evaluate_video calls all metric functions with matching arguments
and that signatures never drift.
"""
from __future__ import annotations
import json
import numpy as np
from pathlib import Path
from scipy.io import wavfile
import pytest

from core.models import Transcript, TranscriptSegment, WordSegment, ClipCandidate
from evals.run import evaluate_video, load_transcript, load_audio, load_crop_path


def test_evaluate_video_missing_transcript(tmp_path: Path):
    """When transcript.json is missing, returns clean error without crashing."""
    fake_meta = {"id": "non_existent_video", "genre": "podcast"}
    result = evaluate_video(fake_meta, cache_dir=tmp_path, gt_dir=tmp_path)
    assert result["id"] == "non_existent_video"
    assert "transcript.json missing — skipping video" in result["errors"]
    assert result["silence_rate"] == "N/A"


def test_evaluate_video_all_metrics_signatures(tmp_path: Path, monkeypatch):
    """Create a minimal real fixture and ensure all 6 metric calls succeed with zero signature errors."""
    vid_id = "test_vid_01"
    cache_dir = tmp_path / "cache"
    gt_dir = tmp_path / "ground_truth"
    v_cache = cache_dir / vid_id
    v_cache.mkdir(parents=True, exist_ok=True)

    # Mock select_clips to return deterministic candidate without hitting live LLM API
    mock_candidates = [
        ClipCandidate(clip_number=1, start_seconds=0.5, end_seconds=3.6, title="Test Clip"),
        ClipCandidate(clip_number=2, start_seconds=10.0, end_seconds=11.5, title="Second Clip"),
    ]
    monkeypatch.setattr("evals.run.select_clips", lambda *args, **kwargs: mock_candidates)

    # 1. 16kHz audio with silence & burst
    sr = 16000
    dur_s = 60.0
    samples = int(sr * dur_s)
    audio = np.random.normal(0, 0.002, samples).astype(np.float32)
    # add tone between 10s and 20s
    t = np.linspace(0, 10.0, sr * 10, endpoint=False)
    audio[10 * sr : 20 * sr] += 0.3 * np.sin(2 * np.pi * 200 * t).astype(np.float32)
    pcm = (audio * 32767).astype(np.int16)
    wavfile.write(str(v_cache / "audio.wav"), sr, pcm)

    # 2. Transcript
    words = [
        {"word": "Hello.", "start": 0.5, "end": 1.2},
        {"word": "This", "start": 2.0, "end": 2.4},
        {"word": "is", "start": 2.5, "end": 2.8},
        {"word": "a", "start": 2.9, "end": 3.0},
        {"word": "test.", "start": 3.1, "end": 3.6},
        {"word": "Important", "start": 10.0, "end": 10.8},
        {"word": "topic.", "start": 10.9, "end": 11.5},
    ]
    transcript_data = {
        "text": "Hello. This is a test. Important topic.",
        "language": "en",
        "duration_seconds": dur_s,
        "segments": [
            {
                "start": 0.5,
                "end": 3.6,
                "text": "Hello. This is a test.",
                "words": words[:5],
            },
            {
                "start": 10.0,
                "end": 11.5,
                "text": "Important topic.",
                "words": words[5:],
            },
        ],
    }
    (v_cache / "transcript.json").write_text(json.dumps(transcript_data), encoding="utf-8")

    # 3. Crop path (30 fps * 60s = 1800 frames)
    crop_path = [656] * int(dur_s * 30)
    (v_cache / "crop_path.json").write_text(json.dumps(crop_path), encoding="utf-8")

    # 4. Ground truth clips
    (gt_dir / "clips").mkdir(parents=True, exist_ok=True)
    gt_clips = [
        {"start_seconds": 0.5, "end_seconds": 3.6, "source": "creator_short"},
        {"start_seconds": 10.0, "end_seconds": 12.0, "source": "blind_human"},
    ]
    (gt_dir / "clips" / f"{vid_id}.json").write_text(json.dumps(gt_clips), encoding="utf-8")

    # 5. Ground truth word timing
    (gt_dir / "word_timing").mkdir(parents=True, exist_ok=True)
    gt_words = [
        {"word": "Hello", "start": 0.52, "end": 1.21},
        {"word": "test", "start": 3.12, "end": 3.62},
    ]
    (gt_dir / "word_timing" / f"{vid_id}.json").write_text(json.dumps(gt_words), encoding="utf-8")

    # 6. Ground truth reframe
    (gt_dir / "reframe").mkdir(parents=True, exist_ok=True)
    gt_reframe = [
        {
            "frame_idx": 30,
            "timestamp": 1.0,
            "active_speaker_box": [620, 180, 1180, 840],
            "layout_mode": "center_crop",
        },
        {
            "frame_idx": 60,
            "timestamp": 2.0,
            "active_speaker_box": [620, 180, 1180, 840],
            "layout_mode": "center_crop",
        },
    ]
    (gt_dir / "reframe" / f"{vid_id}.json").write_text(json.dumps(gt_reframe), encoding="utf-8")

    # Execute evaluate_video
    video_meta = {"id": vid_id, "genre": "podcast"}
    result = evaluate_video(video_meta, cache_dir=cache_dir, gt_dir=gt_dir)

    # Verify no metric signature errors occurred
    assert result["id"] == vid_id
    assert result["errors"] == []
    assert isinstance(result["silence_rate"], float)
    assert isinstance(result["sentence_boundary_rate"], float)
    assert isinstance(result["word_timing_mae_ms"], float)
    assert isinstance(result["clip_recall"], float)
    assert isinstance(result["clip_iou"], float)
    assert isinstance(result["in_crop_rate"], float)
    assert isinstance(result["crop_jitter_px_per_s"], float)
    assert result["n_clips_selected"] >= 1
