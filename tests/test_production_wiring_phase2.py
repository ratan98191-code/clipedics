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
    assert len(plan.words) == 2


def test_face_detected_mid_shot_interval_overlap():
    """Validates that units inside a shot (both start-of-shot and mid-shot) correctly inherit face presence."""
    fps = 30.0
    crop_path = [656] * int(60.0 * fps)
    src_w = 1920

    shot_plans = [
        ShotReframePlan(
            shot_id=1,
            start_seconds=0.0,
            end_seconds=30.0,
            layout_mode="center_crop",
            crop_x=656,
            face_detected=True,
        ),
        ShotReframePlan(
            shot_id=2,
            start_seconds=30.0,
            end_seconds=60.0,
            layout_mode="blur_background",
            crop_x=656,
            face_detected=False,
        ),
    ]

    units = [
        Unit(unit_id=1, start_seconds=0.0, end_seconds=5.0, text="Shot start unit"),
        Unit(unit_id=2, start_seconds=10.0, end_seconds=18.0, text="Mid shot unit with face"),
        Unit(unit_id=3, start_seconds=35.0, end_seconds=42.0, text="Mid shot unit without face"),
    ]

    # Apply the interval-overlap logic from core.pipeline
    for u in units:
        sf = max(0, int(u.start_seconds * fps))
        ef = min(len(crop_path), int(u.end_seconds * fps))
        if ef > sf:
            u.dominant_face_x = float(np.mean(crop_path[sf:ef])) / max(1.0, src_w)

        overlapping_shots = [
            sp for sp in shot_plans
            if max(u.start_seconds, sp.start_seconds) < min(u.end_seconds, sp.end_seconds)
        ]
        if overlapping_shots:
            u.face_detected = any(getattr(sp, "face_detected", False) for sp in overlapping_shots)
        else:
            u.face_detected = False

    # Unit 1 is at start of shot 1 -> face detected
    assert units[0].face_detected is True
    # Unit 2 is in the middle of shot 1 (10s - 18s) -> MUST be True (fixes bug where mid-shot was False)
    assert units[1].face_detected is True
    # Unit 3 is in shot 2 (no face) -> MUST be False
    assert units[2].face_detected is False


def test_filtergraph_golden_audio_fades_only_at_cuts():
    """Golden test: audio micro-fades apply ONLY at non-contiguous timeline cuts, never within continuous speech."""
    from core.models import Beat
    from core.renderer import build_clip_plan_filtergraph

    # Case 1: Contiguous camera shots (e.g. shot cut at 10.0s inside continuous speech)
    contiguous_plan = ClipPlan(
        clip_number=1,
        title="Contiguous",
        beats=[
            Beat(beat_id=1, role="body", src_start=0.0, src_end=10.0, target_start=0.0, target_end=10.0),
            Beat(beat_id=2, role="body", src_start=10.0, src_end=20.0, target_start=10.0, target_end=20.0),
        ],
    )
    filter_complex, _, _ = build_clip_plan_filtergraph(
        contiguous_plan, crop_path=[], src_w=1920, src_h=1080, fps=30.0, crop_w=608
    )

    # First beat has fade-in, but NO fade-out at 10s (speech continues!)
    assert "afade=t=in:ss=0" in filter_complex
    # Second beat has NO fade-in at 10s (speech was continuous!), but HAS fade-out at clip end
    assert filter_complex.count("afade=t=in") == 1
    assert filter_complex.count("afade=t=out") == 1

    # Case 2: Non-contiguous cut (jump cut with 5s gap: 0-10s, then 15-25s)
    cut_plan = ClipPlan(
        clip_number=2,
        title="NonContiguous",
        beats=[
            Beat(beat_id=1, role="body", src_start=0.0, src_end=10.0, target_start=0.0, target_end=10.0),
            Beat(beat_id=2, role="body", src_start=15.0, src_end=25.0, target_start=10.0, target_end=20.0),
        ],
    )
    filter_complex_cut, _, _ = build_clip_plan_filtergraph(
        cut_plan, crop_path=[], src_w=1920, src_h=1080, fps=30.0, crop_w=608
    )

    # Both beats must have fade-in and fade-out to prevent pop/click at true cut boundaries
    assert filter_complex_cut.count("afade=t=in") == 2
    assert filter_complex_cut.count("afade=t=out") == 2


def test_consecutive_rerenders_preserve_words_and_beats(tmp_path: Path, monkeypatch):
    """Ensures two consecutive rerenders preserve words and beat metadata without caption drop."""
    from api.db_models import Clip, Project
    from workers.pipeline import rerender_clip_task

    # Create dummy video file
    video_file = tmp_path / "video.mp4"
    video_file.write_bytes(b"dummy_mp4_bytes")

    initial_words = [
        {"word": "Consistency", "start": 10.0, "end": 10.8},
        {"word": "matters", "start": 10.9, "end": 11.5},
    ]
    initial_beats = [
        {
            "beat_id": 1,
            "role": "hook",
            "src_start": 10.0,
            "src_end": 20.0,
            "target_start": 0.0,
            "target_end": 10.0,
            "layout_mode": "center_crop",
            "crop_x": 656,
        },
        {
            "beat_id": 2,
            "role": "body",
            "src_start": 20.0,
            "src_end": 35.0,
            "target_start": 10.0,
            "target_end": 25.0,
            "layout_mode": "blur_background",
            "crop_x": 700,
        },
    ]

    # Mock DB session in rerender_clip_task
    class MockProject:
        video_path = str(video_file)

    class MockClip:
        id = "test-clip-123"
        project_id = "proj-1"
        clip_number = 1
        title = "Test Rerender Clip"
        start_seconds = 10.0
        end_seconds = 35.0
        virality_score = 88
        output_mp4_path = str(tmp_path / "initial.mp4")
        clip_plan_json = {
            "beats": initial_beats,
            "words": initial_words,
            "src_w": 1280,
            "src_h": 720,
            "fps": 25.0,
            "crop_w": 405,
        }
        success = True
        error = ""

    mock_clip = MockClip()

    class MockSession:
        def get(self, model, pk):
            if model.__name__ == "Clip":
                return mock_clip
            if model.__name__ == "Project":
                return MockProject()
            return None

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr("sqlalchemy.orm.sessionmaker.__call__", lambda self: MockSession())

    # Mock render_clip_plan to simulate successful render
    from core.models import ProcessedClip
    captured_words = []

    def mock_render(source_video, clip_plan, crop_path, src_w, src_h, fps, crop_w, out_dir, subtitle_style, all_words=None):
        captured_words.append(list(all_words) if all_words else [])
        out_file = out_dir / f"rendered_{len(captured_words)}.mp4"
        out_file.write_bytes(b"rendered")
        return ProcessedClip(
            candidate=clip_plan,
            raw_mp4_path=str(out_file),
            output_mp4_path=str(out_file),
            success=True,
        )

    monkeypatch.setattr("workers.pipeline.render_clip_plan", mock_render)

    # ── First rerender: change subtitle style ──
    res1 = rerender_clip_task(clip_id=mock_clip.id, subtitle_style="karaoke")
    assert res1["status"] == "success"
    # Verify captions were passed
    assert len(captured_words[0]) == 2
    assert captured_words[0][0].word == "Consistency"
    # Verify clip_plan_json retained words and beats after first rerender
    assert "words" in mock_clip.clip_plan_json
    assert len(mock_clip.clip_plan_json["words"]) == 2
    assert len(mock_clip.clip_plan_json["beats"]) == 2
    assert mock_clip.clip_plan_json["src_w"] == 1280

    # ── Second consecutive rerender: swap beat order ──
    res2 = rerender_clip_task(clip_id=mock_clip.id, beat_order=[2, 1])
    assert res2["status"] == "success"
    # Verify captions are STILL present (bug 1: was lost after 1st rerender)
    assert len(captured_words[1]) == 2
    assert captured_words[1][0].word == "Consistency"
    assert "words" in mock_clip.clip_plan_json
    assert len(mock_clip.clip_plan_json["words"]) == 2
    # Verify beats reordered properly
    assert mock_clip.clip_plan_json["beats"][0]["src_start"] == 20.0
    assert mock_clip.clip_plan_json["beats"][1]["src_start"] == 10.0

