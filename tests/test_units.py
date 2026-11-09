"""
Tests for Phase 1 Semantic Units, RMS Valley Snapping & Feature Extraction.
"""
import numpy as np
import pytest
from core.models import Transcript, TranscriptSegment, WordSegment, Unit
from core.units import (
    compute_rms_envelope,
    find_rms_valley,
    build_units_from_transcript,
    extract_all_words,
)
from core.features import (
    compute_audio_loudness_lufs,
    extract_silence_map,
    enrich_units_with_features,
)
from core.cache import save_units_cache, load_units_cache


def test_rms_valley_snapping():
    """Verify RMS valley detection accurately pinpoints local audio dips within ±150ms."""
    sr = 16000
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration))

    # Signal: speech energy (sine wave) with an acoustic silence dip at t = 0.50s
    signal = 0.5 * np.sin(2 * np.pi * 200 * t)
    # Create silence valley from 0.45 to 0.55s
    dip_mask = (t >= 0.45) & (t <= 0.55)
    signal[dip_mask] = 0.001

    rms, timestamps = compute_rms_envelope(signal, sample_rate=sr)
    assert len(rms) > 0

    # Test target timestamp slightly offset at 0.52s
    snapped = find_rms_valley(0.52, rms, timestamps, search_radius_sec=0.15)
    # Must snap within the silence valley [0.45, 0.55]
    assert 0.45 <= snapped <= 0.55


def test_unit_splitting_on_gap_and_punctuation():
    """Verify units split on word gaps >= 0.35s and sentence-final punctuation."""
    segments = [
        TranscriptSegment(
            text="First sentence.",
            start=1.0,
            end=2.5,
            words=[
                WordSegment(word="First", start=1.0, end=1.5, score=0.99),
                WordSegment(word="sentence.", start=1.6, end=2.5, score=0.99),
            ],
        ),
        TranscriptSegment(
            text="Second sentence with a gap",
            start=3.2,  # gap = 3.2 - 2.5 = 0.70s (>= 0.35s)
            end=5.0,
            words=[
                WordSegment(word="Second", start=3.2, end=3.8, score=0.99),
                WordSegment(word="sentence", start=3.9, end=4.4, score=0.99),
                WordSegment(word="with", start=4.45, end=4.7, score=0.99),
                WordSegment(word="gap.", start=4.75, end=5.0, score=0.99),
            ],
        ),
    ]
    transcript = Transcript(language="en", duration_seconds=10.0, segments=segments)
    units = build_units_from_transcript(transcript)

    assert len(units) >= 2
    assert units[0].unit_id == 1
    assert units[1].unit_id == 2
    assert "First sentence." in units[0].text
    assert units[0].pause_after_sec >= 0.30


def test_audio_loudness_and_features():
    """Verify loudness and multi-modal feature calculations."""
    sr = 16000
    silent_audio = np.zeros(sr * 2, dtype=np.float32)
    loud_audio = 0.5 * np.ones(sr * 2, dtype=np.float32)

    l_silent = compute_audio_loudness_lufs(silent_audio, sr)
    l_loud = compute_audio_loudness_lufs(loud_audio, sr)

    assert l_silent <= -60.0
    assert l_loud > -20.0

    unit = Unit(
        unit_id=1,
        start_seconds=0.1,
        end_seconds=1.9,
        raw_start_seconds=0.1,
        raw_end_seconds=1.9,
        text="Testing unit features",
    )
    enriched = enrich_units_with_features([unit], audio_samples=loud_audio, sample_rate=sr)
    assert enriched[0].loudness_lufs > -20.0


def test_units_cache_roundtrip(tmp_path):
    """Verify Unit structures save and reload without precision loss."""
    units = [
        Unit(
            unit_id=1,
            start_seconds=10.25,
            end_seconds=25.80,
            raw_start_seconds=10.20,
            raw_end_seconds=25.85,
            text="Cached unit content.",
            loudness_lufs=-18.5,
            speech_rate_wpm=145.0,
        )
    ]
    saved_path = save_units_cache("test_vid_123", units, cache_dir=tmp_path)
    assert saved_path.exists()

    loaded = load_units_cache("test_vid_123", cache_dir=tmp_path)
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0].unit_id == 1
    assert loaded[0].start_seconds == 10.25
    assert loaded[0].loudness_lufs == -18.5

