"""
Unit tests for Clipedics Phase 2: Unit-ID Prompting, Constrained Search, Composite Scoring & Temporal NMS.
"""
from __future__ import annotations
import pytest
from core.models import Transcript, TranscriptSegment, WordSegment, Unit, ClipCandidate, PipelineConfig
from core.units import (
    build_units_from_transcript,
    format_units_for_llm,
    constrained_boundary_search,
    build_clip_from_units,
)
from core.ranking import (
    score_audio_salience,
    score_visual_salience,
    score_hook_salience,
    compute_composite_score,
    temporal_nms,
    select_best_clips_from_units,
)
from core.clipper import _parse_clips, _extract_int, _find_closest_unit_id


@pytest.fixture
def sample_units():
    words1 = [WordSegment(word="Why", start=0.0, end=0.4), WordSegment(word="dopamine", start=0.45, end=0.9), WordSegment(word="matters.", start=0.95, end=1.5)]
    words2 = [WordSegment(word="When", start=2.0, end=2.4), WordSegment(word="you", start=2.45, end=2.7), WordSegment(word="reach", start=2.75, end=3.1), WordSegment(word="a", start=3.15, end=3.3), WordSegment(word="peak,", start=3.35, end=3.8)]
    words3 = [WordSegment(word="your", start=4.2, end=4.5), WordSegment(word="baseline", start=4.55, end=5.1), WordSegment(word="drops", start=5.15, end=5.6), WordSegment(word="below", start=5.65, end=6.0), WordSegment(word="normal.", start=6.05, end=6.6)]
    words4 = [WordSegment(word="This", start=7.2, end=7.5), WordSegment(word="is", start=7.55, end=7.8), WordSegment(word="why", start=7.85, end=8.1), WordSegment(word="motivation", start=8.15, end=8.8), WordSegment(word="crashes.", start=8.85, end=9.5)]
    words5 = [WordSegment(word="To", start=10.0, end=10.3), WordSegment(word="fix", start=10.35, end=10.6), WordSegment(word="it,", start=10.65, end=11.0), WordSegment(word="control", start=11.05, end=11.5), WordSegment(word="the", start=11.55, end=11.7), WordSegment(word="spikes.", start=11.75, end=12.5)]

    units = [
        Unit(unit_id=1, start_seconds=0.0, end_seconds=1.6, raw_start_seconds=0.0, raw_end_seconds=1.5, text="Why dopamine matters.", words=words1, speech_rate_wpm=150.0, loudness_lufs=-18.0, shot_ids=[0], face_detected=True, pause_before_sec=0.0, pause_after_sec=0.4),
        Unit(unit_id=2, start_seconds=2.0, end_seconds=3.9, raw_start_seconds=2.0, raw_end_seconds=3.8, text="When you reach a peak,", words=words2, speech_rate_wpm=145.0, loudness_lufs=-19.0, shot_ids=[0], face_detected=True, pause_before_sec=0.4, pause_after_sec=0.3),
        Unit(unit_id=3, start_seconds=4.2, end_seconds=6.7, raw_start_seconds=4.2, raw_end_seconds=6.6, text="your baseline drops below normal.", words=words3, speech_rate_wpm=140.0, loudness_lufs=-17.5, shot_ids=[1], face_detected=True, pause_before_sec=0.3, pause_after_sec=0.5),
        Unit(unit_id=4, start_seconds=7.2, end_seconds=9.6, raw_start_seconds=7.2, raw_end_seconds=9.5, text="This is why motivation crashes.", words=words4, speech_rate_wpm=155.0, loudness_lufs=-18.2, shot_ids=[1], face_detected=True, pause_before_sec=0.5, pause_after_sec=0.4),
        Unit(unit_id=5, start_seconds=10.0, end_seconds=12.6, raw_start_seconds=10.0, raw_end_seconds=12.5, text="To fix it, control the spikes.", words=words5, speech_rate_wpm=142.0, loudness_lufs=-18.8, shot_ids=[2], face_detected=True, pause_before_sec=0.4, pause_after_sec=1.0),
    ]
    return units


def test_format_units_for_llm(sample_units):
    text = format_units_for_llm(sample_units)
    assert "[Unit 1]" in text
    assert "Why dopamine matters." in text
    assert "[Unit 5]" in text
    assert "To fix it, control the spikes." in text


def test_constrained_boundary_search(sample_units):
    # Minimum 6s constraint: Unit 1 (1.6s) is too short -> should expand forward
    s_id, e_id = constrained_boundary_search(1, 1, sample_units, min_seconds=6.0, max_seconds=15.0)
    assert s_id == 1
    assert e_id >= 3  # Units 1..3 span 0.0 to 6.7s (> 6.0s)

    # Inverted IDs: start > end -> should swap and normalize
    s_id2, e_id2 = constrained_boundary_search(4, 2, sample_units, min_seconds=2.0, max_seconds=15.0)
    assert s_id2 <= e_id2

    # Maximum constraint: if span is too long, trims backward
    s_id3, e_id3 = constrained_boundary_search(1, 5, sample_units, min_seconds=2.0, max_seconds=5.0)
    assert e_id3 < 5


def test_build_clip_from_units(sample_units):
    clip = build_clip_from_units(
        start_unit_id=1,
        end_unit_id=3,
        units=sample_units,
        clip_number=1,
        title="Dopamine Secret",
        virality_score=85,
        min_seconds=5.0,
        max_seconds=15.0,
    )
    assert clip.clip_number == 1
    assert clip.title == "Dopamine Secret"
    assert clip.start_seconds == 0.0
    assert clip.end_seconds == 6.7
    assert "Why dopamine matters." in clip.hook_sentence


def test_parse_clips_unit_ids(sample_units):
    fake_transcript = Transcript(
        text="Why dopamine matters...",
        segments=[],
        language="en",
        duration_seconds=15.0,
    )
    json_response = """{
      "clips": [
        {
          "clip_number": 1,
          "start_unit_id": 1,
          "end_unit_id": 3,
          "title": "Dopamine Crash",
          "virality_score": 90,
          "virality_rationale": "High curiosity opening",
          "hook_sentence": "Why dopamine matters.",
          "suggested_caption": "Mind blowing dopamine truth",
          "hashtags": ["mindset", "focus"]
        }
      ]
    }"""
    cfg = PipelineConfig(num_clips=1, min_seconds=4.0, max_seconds=10.0)
    clips = _parse_clips(json_response, fake_transcript, cfg, units=sample_units)
    assert len(clips) == 1
    assert clips[0].start_seconds == 0.0
    assert clips[0].end_seconds == 6.7
    assert clips[0].title == "Dopamine Crash"


def test_parse_clips_fallback_timestamps(sample_units):
    fake_transcript = Transcript(
        text="Why dopamine matters...",
        segments=[],
        language="en",
        duration_seconds=15.0,
    )
    # LLM hallucinated timestamps instead of unit IDs
    json_response = """{
      "clips": [
        {
          "clip_number": 1,
          "start_seconds": 2.1,
          "end_seconds": 9.4,
          "title": "Fallback Mapping",
          "virality_score": 88
        }
      ]
    }"""
    cfg = PipelineConfig(num_clips=1, min_seconds=4.0, max_seconds=15.0)
    clips = _parse_clips(json_response, fake_transcript, cfg, units=sample_units)
    assert len(clips) == 1
    # 2.1s maps to Unit 2 (starts at 2.0s), 9.4s maps to Unit 4 (ends at 9.6s)
    assert clips[0].start_seconds == 2.0
    assert clips[0].end_seconds == 9.6


def test_temporal_nms():
    # Two heavily overlapping clips (IoU > 0.40)
    c1 = ClipCandidate(
        clip_number=1, start_seconds=10.0, end_seconds=40.0,
        title="High Score", virality_score=95
    )
    c2 = ClipCandidate(
        clip_number=2, start_seconds=12.0, end_seconds=42.0,
        title="Overlapping Lower Score", virality_score=80
    )
    # Disjoint clip
    c3 = ClipCandidate(
        clip_number=3, start_seconds=100.0, end_seconds=130.0,
        title="Separate Viral Moment", virality_score=85
    )

    pruned = temporal_nms([c1, c2, c3], iou_threshold=0.40, top_k=5)
    # c2 should be suppressed by c1
    assert len(pruned) == 2
    assert pruned[0].title == "High Score"
    assert pruned[1].title == "Separate Viral Moment"
    assert pruned[0].clip_number == 1
    assert pruned[1].clip_number == 2


def test_composite_scoring(sample_units):
    c = ClipCandidate(
        clip_number=1, start_seconds=0.0, end_seconds=6.7,
        title="Test Clip", virality_score=85
    )
    score = compute_composite_score(c, sample_units)
    assert 1 <= score <= 100
    # Opening unit has question opener "Why dopamine matters." -> scores high hook
    assert score >= 70
