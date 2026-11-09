"""
Tests for Phase 6: Narrative Planner & Faithfulness Gate
Verifies:
1. Narrative unit enrichment (hook, build, peak, cliffhanger roles & loop detection).
2. Beam search narrative arc optimization (strict role progression).
3. Hook placement in the first 3 seconds (dur <= 5.5s, target_start == 0.0s).
4. Faithfulness hard gate: negation polarity preservation, non-contradiction, and safe genre restrictions.
5. End-to-end integration with non-linear EDL filtergraph renderer.
"""
import pytest

from core.models import Beat, ClipCandidate, ClipPlan, Unit, WordSegment
from core.narrative import (
    label_narrative_units,
    extract_role_candidates,
    plan_narrative_arc,
    plan_narrative_arcs_for_candidates,
)
from core.faithfulness import (
    detect_polarity_inversion,
    is_genre_safe_for_narrative_reorder,
    verify_faithfulness,
)
from core.renderer import build_clip_plan_filtergraph


def _create_story_units() -> list[Unit]:
    """Create a realistic sequence of 8 units forming a complete story arc."""
    return [
        Unit(
            unit_id=1,
            start_seconds=10.0,
            end_seconds=14.0,
            raw_start_seconds=10.0,
            raw_end_seconds=14.0,
            text="In 2021, our startup was 24 hours away from complete bankruptcy.",
            loudness_lufs=-22.0,
            speech_rate_wpm=140.0,
        ),
        Unit(
            unit_id=2,
            start_seconds=14.0,
            end_seconds=18.5,
            raw_start_seconds=14.0,
            raw_end_seconds=18.5,
            text="We had three payrolls due on Friday and zero money in the bank account.",
            loudness_lufs=-21.5,
            speech_rate_wpm=145.0,
        ),
        Unit(
            unit_id=3,
            start_seconds=18.5,
            end_seconds=22.5,
            raw_start_seconds=18.5,
            raw_end_seconds=22.5,
            text="Why do 90% of technical founders make the exact same cash flow mistake?",
            loudness_lufs=-18.0,
            speech_rate_wpm=155.0,
        ),
        Unit(
            unit_id=4,
            start_seconds=22.5,
            end_seconds=32.0,
            raw_start_seconds=22.5,
            raw_end_seconds=32.0,
            text="Because they assume enterprise contract signatures mean cash received today.",
            loudness_lufs=-22.0,
            speech_rate_wpm=135.0,
        ),
        Unit(
            unit_id=5,
            start_seconds=32.0,
            end_seconds=42.0,
            raw_start_seconds=32.0,
            raw_end_seconds=42.0,
            text="So I sat down on Thursday night, opened up my personal phone, and called 25 clients.",
            loudness_lufs=-23.0,
            speech_rate_wpm=138.0,
        ),
        Unit(
            unit_id=6,
            start_seconds=42.0,
            end_seconds=52.0,
            raw_start_seconds=42.0,
            raw_end_seconds=52.0,
            text="And that was the exact moment everything changed: one client wired two million dollars in twenty minutes!",
            loudness_lufs=-17.0,  # Peak revelation
            speech_rate_wpm=160.0,
        ),
        Unit(
            unit_id=7,
            start_seconds=52.0,
            end_seconds=58.0,
            raw_start_seconds=52.0,
            raw_end_seconds=58.0,
            text="We saved every job on Friday morning.",
            loudness_lufs=-20.0,
            speech_rate_wpm=140.0,
        ),
        Unit(
            unit_id=8,
            start_seconds=58.0,
            end_seconds=63.0,
            raw_start_seconds=58.0,
            raw_end_seconds=63.0,
            text="And you won't believe what that same investor offered us the following Monday morning.",
            loudness_lufs=-19.0,
            speech_rate_wpm=148.0,
        ),
    ]


def test_narrative_unit_labeling():
    """Verify narrative role labeling and loop opening/answering detection."""
    units = _create_story_units()
    labeled = label_narrative_units(units)

    # Unit 3 has strong question trigger ("Why do...")
    assert labeled[2].role_hint == "hook"
    assert labeled[2].opens_loop is not None

    # Unit 6 has peak revelation triggers ("exact moment everything changed") and high loudness
    assert labeled[5].role_hint == "peak"
    assert labeled[5].narrative_energy > 70.0

    # Unit 8 has cliffhanger marker ("you won't believe")
    assert labeled[7].role_hint == "cliffhanger"


def test_multi_beat_narrative_arc_progression():
    """
    Verify beam search narrative planner builds a 4-beat arc with strictly:
    [hook -> build -> peak -> cliffhanger]
    """
    units = _create_story_units()
    plan = plan_narrative_arc(units, genre="podcast", target_duration=35.0, min_duration=20.0, max_duration=60.0)

    assert plan.format_variant == "narrative_arc"
    assert len(plan.beats) == 4

    roles = [b.role for b in plan.beats]
    assert roles == ["hook", "build", "peak", "cliffhanger"]

    # Hook must be in the first 3-5 seconds
    hook_beat = plan.beats[0]
    assert hook_beat.target_start == 0.0
    assert hook_beat.duration <= 5.5

    # Target timestamps must form a seamless presentation timeline
    prev_end = 0.0
    for b in plan.beats:
        assert b.target_start == pytest.approx(prev_end, 0.01)
        assert b.target_end > b.target_start
        prev_end = b.target_end

    assert plan.total_duration == pytest.approx(prev_end, 0.01)
    assert 20.0 <= plan.total_duration <= 60.0


def test_faithfulness_negation_polarity_integrity():
    """
    Verify the Faithfulness Gate detects and rejects negation polarity inversions.
    """
    src_text = "I never believed we would fail without putting up a fight."
    # Distortion: "we would fail without putting up a fight" (severed "never")
    distorted_text = "we would fail without putting up a fight"

    assert detect_polarity_inversion(src_text, distorted_text) is True

    # Faithful preservation: retains "never"
    faithful_text = "I never believed we would fail"
    assert detect_polarity_inversion(src_text, faithful_text) is False


def test_faithfulness_safe_genre_fallback():
    """
    Verify safe genre restrictions:
    - Podcast / Talk permits narrative reordering
    - Tutorial / Code restricts non-linear reordering and falls back to safe formats
    """
    assert is_genre_safe_for_narrative_reorder("podcast") is True
    assert is_genre_safe_for_narrative_reorder("interview_talk") is True
    assert is_genre_safe_for_narrative_reorder("debate") is True

    assert is_genre_safe_for_narrative_reorder("tutorial_vlog") is False
    assert is_genre_safe_for_narrative_reorder("code_walkthrough") is False

    units = _create_story_units()
    # Planning for a tutorial genre should safely fall back to cold_open or contiguous
    tut_plan = plan_narrative_arc(units, genre="tutorial_vlog")
    assert tut_plan.format_variant in ("cold_open", "contiguous")


def test_faithfulness_hard_gate_validation():
    """Verify verify_faithfulness accepts valid plans and rejects contradictory ones."""
    units = _create_story_units()
    plan = plan_narrative_arc(units, genre="podcast")

    passed, reason = verify_faithfulness(plan, units, genre="podcast")
    assert passed is True

    # Corrupt a beat with a nonexistent unit ID
    corrupted_beats = list(plan.beats)
    corrupted_beats[0] = Beat(
        beat_id=1,
        role="hook",
        unit_ids=[999],  # Nonexistent
        src_start=0.0,
        src_end=4.0,
        target_start=0.0,
        target_end=4.0,
        text="Hallucinated text",
    )
    corrupted_plan = ClipPlan(
        plan_id="corrupt",
        format_variant="narrative_arc",
        beats=corrupted_beats,
    )

    passed, reason = verify_faithfulness(corrupted_plan, units, genre="podcast")
    assert passed is False
    assert "nonexistent unit" in reason


def test_narrative_filtergraph_rendering_compatibility():
    """
    Verify that 4-beat narrative ClipPlans generate valid FFmpeg filtergraphs
    with multi-trim, 30ms anti-click crossfading, concat, and loudnorm.
    """
    units = _create_story_units()
    plan = plan_narrative_arc(units, genre="podcast")

    filter_complex, vout, aout = build_clip_plan_filtergraph(
        clip_plan=plan,
        crop_path=[400] * 500,
        src_w=1920,
        src_h=1080,
        fps=30.0,
        crop_w=607,
        ass_path=None,
    )

    # 4 beats mean 4 trims and concat=n=4
    assert "concat=n=4:v=1:a=1" in filter_complex
    assert "afade=t=in:ss=0:d=0.030" in filter_complex
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in filter_complex
    assert vout == "[v_concat]"
    assert aout == "[a_norm]"
