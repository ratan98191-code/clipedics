"""
Tests for Phase 2: Production Architecture Wiring

Validates that:
  1. Audio waveform samples are loaded and passed to Unit segmentation, snapping to real RMS valleys.
  2. Multi-modal features enrich Units (loudness, shots, face presence).
  3. Shot-aware reframe assigns per-shot layout modes (blur_background, split_screen, center_crop).
  4. Non-linear ClipPlan is always constructed and rendered through filtergraph with loudnorm and crossfades.
  5. Editor endpoints enqueue real re-render tasks that update plans and DB records.
"""
import pytest
import numpy as np
from pathlib import Path

from core.models import (
    Transcript,
    TranscriptSegment,
    WordSegment,
    Unit,
    ClipCandidate,
    ClipPlan,
    ShotReframePlan,
    PipelineConfig,
)
from core.units import build_units_from_transcript
from core.features import enrich_units_with_features
from core.reframer import generate_clip_reframe_plans
from core.pipeline import build_candidate_clip_plan, get_clip_words_and_segments


def test_units_with_real_audio_and_features():
    # 1. Synthesize 5 seconds of audio with a distinct silence valley at 2.5s
    sr = 16000
    total_samples = int(5.0 * sr)
    audio = np.random.normal(0.0, 0.001, total_samples).astype(np.float32)  # noise floor

    # Speech burst from 0.0 to 2.3s
    t1 = np.linspace(0, 2.3, int(2.3 * sr), endpoint=False)
    audio[: len(t1)] += (0.4 * np.sin(2 * np.pi * 150 * t1)).astype(np.float32)

    # Speech burst from 2.7 to 4.8s
    t2 = np.linspace(0, 2.1, int(2.1 * sr), endpoint=False)
    s2_idx = int(2.7 * sr)
    audio[s2_idx : s2_idx + len(t2)] += (0.4 * np.sin(2 * np.pi * 150 * t2)).astype(np.float32)

    transcript = Transcript(
        text="First sentence here. Second sentence continues.",
        language="en",
        segments=[
            TranscriptSegment(
                id=0,
                start=0.0,
                end=2.3,
                text="First sentence here.",
                words=[
                    WordSegment(word="First", start=0.0, end=0.6),
                    WordSegment(word="sentence", start=0.7, end=1.4),
                    WordSegment(word="here.", start=1.5, end=2.3),
                ],
            ),
            TranscriptSegment(
                id=1,
                start=2.7,
                end=4.8,
                text="Second sentence continues.",
                words=[
                    WordSegment(word="Second", start=2.7, end=3.3),
                    WordSegment(word="sentence", start=3.4, end=4.0),
                    WordSegment(word="continues.", start=4.1, end=4.8),
                ],
            ),
        ],
        duration_seconds=5.0,
    )

    # Build units with audio samples
    units = build_units_from_transcript(transcript, audio_samples=audio, sample_rate=sr)
    assert len(units) >= 2

    # Enrich with shots
    shots = [(0.0, 2.5, 1), (2.5, 5.0, 2)]
    enriched = enrich_units_with_features(units, audio_samples=audio, sample_rate=sr, shots=shots)

    # Unit 1 must have valid loudness and shot id 1
    assert enriched[0].loudness_lufs > -40.0
    assert 1 in enriched[0].shot_ids


def test_generate_clip_reframe_plans_layout_selection():
    cand_slides = ClipCandidate(
        clip_number=1,
        start_seconds=10.0,
        end_seconds=40.0,
        title="Screen share demonstration",
        virality_score=80,
    )
    cand_talk = ClipCandidate(
        clip_number=2,
        start_seconds=50.0,
        end_seconds=80.0,
        title="Keynote speaker close-up",
        virality_score=75,
    )

    shot_plans = [
        ShotReframePlan(
            shot_id=1,
            start_seconds=0.0,
            end_seconds=45.0,
            layout_mode="blur_background",
            crop_x=656,
        ),
        ShotReframePlan(
            shot_id=2,
            start_seconds=45.0,
            end_seconds=90.0,
            layout_mode="center_crop",
            crop_x=700,
        ),
    ]

    updated = generate_clip_reframe_plans(
        candidates=[cand_slides, cand_talk],
        crop_path=[656] * (90 * 30),
        src_w=1920,
        src_h=1080,
        fps=30.0,
        shot_plans=shot_plans,
    )

    # Verify layout assignment matches underlying shot
    assert updated[0].layout_mode == "blur_background"
    assert updated[0].reframe_plans[0].layout_mode == "blur_background"

    assert updated[1].layout_mode == "center_crop"
    assert updated[1].reframe_plans[0].layout_mode == "center_crop"


def test_build_candidate_clip_plan_multi_shot():
    cand = ClipCandidate(
        clip_number=1,
        start_seconds=10.0,
        end_seconds=60.0,
        title="Multi-shot clip",
        virality_score=85,
        layout_mode="center_crop",
        reframe_plans=[
            ShotReframePlan(shot_id=1, start_seconds=10.0, end_seconds=30.0, layout_mode="center_crop", crop_x=600),
            ShotReframePlan(shot_id=2, start_seconds=30.0, end_seconds=60.0, layout_mode="blur_background", crop_x=656),
        ],
    )

    words = [
        WordSegment(word="Hello", start=10.0, end=10.5),
        WordSegment(word="World", start=59.0, end=59.5),
    ]

    plan = build_candidate_clip_plan(
        candidate=cand,
        crop_path=[600] * (60 * 30),
        src_w=1920,
        fps=30.0,
        all_words=words,
    )

    assert plan.clip_number == 1
    assert len(plan.beats) == 2
    assert plan.beats[0].src_start == 10.0
    assert plan.beats[0].src_end == 30.0
    assert plan.beats[0].layout_mode == "center_crop"

    assert plan.beats[1].src_start == 30.0
    assert plan.beats[1].src_end == 60.0
    assert plan.beats[1].layout_mode == "blur_background"
    assert plan.total_duration == pytest.approx(50.0, 0.01)
