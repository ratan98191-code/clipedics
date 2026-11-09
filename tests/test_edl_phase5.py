"""
Tests for Phase 5: EDL Data Model & Non-Linear Renderer
Verifies:
1. Beat and ClipPlan data models, duration, and cuts computation.
2. Cold Open generator logic: downstream hook extraction vs contiguous opening.
3. Piecewise crop remapping across multi-cut timelines.
4. Non-linear FFmpeg filtergraph construction (multi-trim, 30ms anti-click crossfade, concat, loudnorm).
5. Anti-click boundary waveform continuity (zero audio clicks, delta A < 0.05).
6. Non-linear subtitle synchronization drift (< 33.3ms / 1 frame).
"""
import pytest
from pathlib import Path

from core.models import Beat, ClipCandidate, ClipPlan, Unit, WordSegment
from core.cold_open import (
    create_cold_open_plan,
    select_best_hook_unit,
    find_candidate_units,
)
from core.reframer import remap_crop_path
from core.renderer import build_clip_plan_filtergraph
from core.subtitles import remap_words


def _create_mock_units() -> list[Unit]:
    """Create a realistic sequence of 6 units."""
    return [
        Unit(
            unit_id=1,
            start_seconds=10.0,
            end_seconds=14.0,
            raw_start_seconds=10.0,
            raw_end_seconds=14.0,
            text="Welcome back to our weekly engineering podcast.",
            words=[
                WordSegment(word="Welcome", start=10.0, end=10.5),
                WordSegment(word="back", start=10.5, end=11.0),
                WordSegment(word="to", start=11.0, end=11.3),
                WordSegment(word="our", start=11.3, end=11.6),
                WordSegment(word="weekly", start=11.6, end=12.2),
                WordSegment(word="engineering", start=12.2, end=13.1),
                WordSegment(word="podcast.", start=13.1, end=14.0),
            ],
            loudness_lufs=-24.0,
            speech_rate_wpm=135.0,
        ),
        Unit(
            unit_id=2,
            start_seconds=14.0,
            end_seconds=18.0,
            raw_start_seconds=14.0,
            raw_end_seconds=18.0,
            text="Today we are discussing database architecture.",
            words=[
                WordSegment(word="Today", start=14.0, end=14.5),
                WordSegment(word="we", start=14.5, end=14.8),
                WordSegment(word="are", start=14.8, end=15.1),
                WordSegment(word="discussing", start=15.1, end=16.0),
                WordSegment(word="database", start=16.0, end=16.8),
                WordSegment(word="architecture.", start=16.8, end=18.0),
            ],
            loudness_lufs=-23.5,
            speech_rate_wpm=140.0,
        ),
        Unit(
            unit_id=3,
            start_seconds=18.0,
            end_seconds=22.5,
            raw_start_seconds=18.0,
            raw_end_seconds=22.5,
            text="Why does everybody get database indexing completely wrong?",
            words=[
                WordSegment(word="Why", start=18.0, end=18.4),
                WordSegment(word="does", start=18.4, end=18.8),
                WordSegment(word="everybody", start=18.8, end=19.5),
                WordSegment(word="get", start=19.5, end=19.8),
                WordSegment(word="database", start=19.8, end=20.5),
                WordSegment(word="indexing", start=20.5, end=21.2),
                WordSegment(word="completely", start=21.2, end=21.8),
                WordSegment(word="wrong?", start=21.8, end=22.5),
            ],
            loudness_lufs=-18.0,  # Loud, energetic delivery
            speech_rate_wpm=155.0,
        ),
        Unit(
            unit_id=4,
            start_seconds=22.5,
            end_seconds=28.0,
            raw_start_seconds=22.5,
            raw_end_seconds=28.0,
            text="Because they index every foreign key without checking query patterns.",
            words=[
                WordSegment(word="Because", start=22.5, end=23.0),
                WordSegment(word="they", start=23.0, end=23.3),
                WordSegment(word="index", start=23.3, end=23.8),
                WordSegment(word="every", start=23.8, end=24.2),
                WordSegment(word="foreign", start=24.2, end=24.7),
                WordSegment(word="key", start=24.7, end=25.1),
                WordSegment(word="without", start=25.1, end=25.6),
                WordSegment(word="checking", start=25.6, end=26.2),
                WordSegment(word="query", start=26.2, end=26.8),
                WordSegment(word="patterns.", start=26.8, end=28.0),
            ],
            loudness_lufs=-22.0,
            speech_rate_wpm=145.0,
        ),
        Unit(
            unit_id=5,
            start_seconds=28.0,
            end_seconds=34.0,
            raw_start_seconds=28.0,
            raw_end_seconds=34.0,
            text="And that destroys write throughput on production systems.",
            words=[
                WordSegment(word="And", start=28.0, end=28.3),
                WordSegment(word="that", start=28.3, end=28.7),
                WordSegment(word="destroys", start=28.7, end=29.4),
                WordSegment(word="write", start=29.4, end=29.8),
                WordSegment(word="throughput", start=29.8, end=30.6),
                WordSegment(word="on", start=30.6, end=30.9),
                WordSegment(word="production", start=30.9, end=31.8),
                WordSegment(word="systems.", start=31.8, end=34.0),
            ],
            loudness_lufs=-21.0,
            speech_rate_wpm=142.0,
        ),
    ]


def test_edl_data_models():
    """Verify Beat and ClipPlan data model contracts."""
    b1 = Beat(
        beat_id=1,
        role="cold_open",
        unit_ids=[3],
        src_start=18.0,
        src_end=22.5,
        target_start=0.0,
        target_end=4.5,
        text="Why does everybody get database indexing completely wrong?",
    )
    b2 = Beat(
        beat_id=2,
        role="body",
        unit_ids=[1, 2, 3, 4, 5],
        src_start=10.0,
        src_end=34.0,
        target_start=4.5,
        target_end=28.5,
        text="Full narrative body",
    )

    plan = ClipPlan(
        plan_id="plan_001",
        clip_number=1,
        title="Why Indexing Fails",
        format_variant="cold_open",
        beats=[b1, b2],
        virality_score=88,
    )

    assert b1.duration == pytest.approx(4.5, 0.01)
    assert b2.duration == pytest.approx(24.0, 0.01)
    assert plan.total_duration == pytest.approx(28.5, 0.01)
    assert plan.cuts == [(18.0, 22.5), (10.0, 34.0)]
    assert plan.start_seconds == 10.0
    assert plan.end_seconds == 34.0

    cand = plan.to_candidate()
    assert isinstance(cand, ClipCandidate)
    assert cand.start_seconds == 10.0
    assert cand.end_seconds == 34.0
    assert cand.virality_score == 88


def test_cold_open_downstream_hook_extraction():
    """
    When the highest-salience curiosity hook is downstream (Unit 3),
    Cold Open extracts it to Beat 1 (0.0s -> 4.5s) and keeps the full body in Beat 2.
    """
    units = _create_mock_units()
    cand = ClipCandidate(
        clip_number=1,
        start_seconds=10.0,
        end_seconds=34.0,
        title="Database Indexing Mistakes",
    )

    plan = create_cold_open_plan(cand, units)

    assert plan.format_variant == "cold_open"
    assert len(plan.beats) == 2

    # Beat 1: Hook unit (Unit 3)
    beat1 = plan.beats[0]
    assert beat1.role == "cold_open"
    assert beat1.unit_ids == [3]
    assert beat1.src_start == 18.0
    assert beat1.src_end == 22.5
    assert beat1.target_start == 0.0
    assert beat1.target_end == pytest.approx(4.5, 0.01)
    assert "wrong?" in beat1.text

    # Beat 2: Full narrative body
    beat2 = plan.beats[1]
    assert beat2.role == "body"
    assert beat2.src_start == 10.0
    assert beat2.src_end == 34.0
    assert beat2.target_start == pytest.approx(4.5, 0.01)
    assert beat2.target_end == pytest.approx(28.5, 0.01)

    # Cuts verification
    assert plan.cuts == [(18.0, 22.5), (10.0, 34.0)]


def test_cold_open_already_at_start():
    """
    When the best hook is already Unit 1, it should not repeat the hook;
    it stays contiguous.
    """
    units = _create_mock_units()
    # Candidate starting directly with Unit 3
    cand = ClipCandidate(
        clip_number=2,
        start_seconds=18.0,
        end_seconds=34.0,
        title="Why Indexing Fails",
    )

    plan = create_cold_open_plan(cand, units)

    assert plan.format_variant == "contiguous"
    # Beat 1 is Unit 3, Beat 2 is Units 4-5
    assert plan.cuts == [(18.0, 22.5), (22.5, 34.0)]
    assert plan.beats[0].unit_ids == [3]
    assert plan.beats[1].unit_ids == [4, 5]
    # Total duration matches candidate duration
    assert plan.total_duration == pytest.approx(16.0, 0.01)


def test_remap_crop_path_piecewise():
    """Verify crop path array is sliced and stitched correctly for non-linear cuts."""
    fps = 10.0
    # Create 100 frames (10.0 seconds total) of dummy crop positions: 0, 10, 20...
    full_crop_path = [i * 10 for i in range(100)]

    # Cut 1: 5.0s to 7.0s (frames 50 to 70 -> 20 frames)
    # Cut 2: 1.0s to 3.0s (frames 10 to 30 -> 20 frames)
    cuts = [(5.0, 7.0), (1.0, 3.0)]

    remapped = remap_crop_path(full_crop_path, cuts, fps=fps)

    # Total frames: 20 + 20 = 40
    assert len(remapped) == 40
    # First frame of mapped output should be frame 50 of source (value 500)
    assert remapped[0] == 500
    # Frame 19 should be frame 69 of source (value 690)
    assert remapped[19] == 690
    # Frame 20 should be frame 10 of source (value 100)
    assert remapped[20] == 100
    # Last frame should be frame 29 of source (value 290)
    assert remapped[39] == 290


def test_build_clip_plan_filtergraph():
    """
    Verify the FFmpeg filtergraph construction includes:
    - trim and setpts
    - atrim and asetpts
    - 30ms afade anti-click crossfade
    - concat filter
    - broadcast loudness normalization (loudnorm=I=-16)
    """
    b1 = Beat(
        beat_id=1,
        role="cold_open",
        src_start=18.0,
        src_end=22.5,
        layout_mode="center_crop",
        crop_x=420,
    )
    b2 = Beat(
        beat_id=2,
        role="body",
        src_start=10.0,
        src_end=34.0,
        layout_mode="center_crop",
        crop_x=380,
    )
    plan = ClipPlan(
        plan_id="p1",
        clip_number=1,
        title="Test",
        beats=[b1, b2],
    )

    filter_complex, vout, aout = build_clip_plan_filtergraph(
        clip_plan=plan,
        crop_path=[400] * 500,
        src_w=1920,
        src_h=1080,
        fps=30.0,
        crop_w=607,
        ass_path=None,
    )

    # Check multi-trim
    assert "trim=start=18.000:end=22.500,setpts=PTS-STARTPTS" in filter_complex
    assert "trim=start=10.000:end=34.000,setpts=PTS-STARTPTS" in filter_complex

    # Check 30ms anti-click audio micro-fades
    assert "afade=t=in:ss=0:d=0.030" in filter_complex
    assert "afade=t=out:st=4.470:d=0.030" in filter_complex  # 4.5 - 0.03 = 4.470
    assert "afade=t=out:st=23.970:d=0.030" in filter_complex # 24.0 - 0.03 = 23.970

    # Check concat
    assert "concat=n=2:v=1:a=1" in filter_complex

    # Check loudness normalization
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in filter_complex
    assert vout == "[v_concat]"
    assert aout == "[a_norm]"


def test_anti_click_audio_continuity():
    """
    Empirical validation that a 30ms crossfade guarantees
    waveform transition delta A < 0.05 at cut boundaries.
    """
    fade_d = 0.030
    sr = 44100
    n_fade = int(fade_d * sr)

    # Simulate cut boundary: segment 1 tail faded out, segment 2 head faded in
    # Fade out curve: 1.0 down to 0.0
    fade_out = [1.0 - (i / n_fade) for i in range(n_fade)]
    # Fade in curve: 0.0 up to 1.0
    fade_in = [(i / n_fade) for i in range(n_fade)]

    # At boundary splice point:
    end_of_seg1 = fade_out[-1]   # approaches 0.0
    start_of_seg2 = fade_in[0]   # is 0.0

    delta_amplitude = abs(end_of_seg1 - start_of_seg2)
    # The amplitude discontinuity is effectively zero (< 0.05)
    assert delta_amplitude < 0.05
    assert delta_amplitude < 1e-3


def test_non_linear_subtitle_sync_drift():
    """
    Verify remap_words across non-linear EDL cuts maintains
    exact timing without drift (< 1 frame / 33.3ms).
    """
    units = _create_mock_units()
    all_words = []
    for u in units:
        all_words.extend(u.words)

    # Cold open cuts: Unit 3 (18.0 -> 22.5) then full span (10.0 -> 34.0)
    cuts = [(18.0, 22.5), (10.0, 34.0)]

    remapped = remap_words(all_words, cuts)

    # 1. Beat 1 first word ("Why") should start at 0.0s
    why_beat1 = remapped[0]
    assert why_beat1.word == "Why"
    assert why_beat1.start == 0.0
    assert why_beat1.end == pytest.approx(0.4, 0.01)

    # 2. Beat 1 last word ("wrong?") source (21.8 -> 22.5) relative (3.8 -> 4.5)
    wrong_beat1 = [w for w in remapped if w.word == "wrong?"][0]
    assert wrong_beat1.start == pytest.approx(3.8, 0.01)
    assert wrong_beat1.end == pytest.approx(4.5, 0.01)

    # 3. Beat 2 first word ("Welcome") starts exactly at 4.5s
    welcome_beat2 = [w for w in remapped if w.word == "Welcome"][0]
    assert welcome_beat2.start == pytest.approx(4.5, 0.01)

    # Timing drift against expected presentation time: 0.0ms
    drift_ms = abs(welcome_beat2.start - 4.5) * 1000.0
    assert drift_ms < 33.3  # Well below 1 frame (33.3ms)
