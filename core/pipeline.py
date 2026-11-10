"""
Clipedics Unified Production Pipeline (Phase 2 Master Engine)

Unifies CLI (main.py) and Celery Worker (workers/pipeline.py) into a single,
deterministic pipeline with physical artifact caching:
  ingest -> audio -> asr -> units(+audio) -> features -> select -> plan -> reframe -> render

Guarantees:
  1. Real 16kHz mono audio waveform is loaded and passed to unit builder for true RMS valley snapping.
  2. Multi-modal features (loudness LUFS, PySceneDetect shots, face tracking) enrich Units.
  3. Reframe produces per-shot ShotReframePlan with layout modes (blur_background, split_screen, center_crop).
  4. Non-linear ClipPlan EDL is always constructed and rendered with 30ms anti-click crossfades and -16 LUFS loudnorm.
  5. Provides real-time progress callbacks for SSE status streaming and CLI progress bars.
"""
from __future__ import annotations
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional
import numpy as np
from scipy.io import wavfile

from core.models import (
    Transcript,
    Unit,
    ClipCandidate,
    ClipPlan,
    Beat,
    ProcessedClip,
    PipelineConfig,
    ShotReframePlan,
    WordSegment,
    TranscriptSegment,
)
from core.ingestion import prepare_video, extract_audio
from core.transcriber import transcribe
from core.units import build_units_from_transcript, extract_all_words
from core.features import detect_shot_boundaries, enrich_units_with_features
from core.clipper import select_clips
from core.reframer import compute_crop_path, generate_clip_reframe_plans
from core.renderer import render_clip_plan, render_clips
from core.cache import save_units_cache, load_units_cache


def get_clip_words_and_segments(
    transcript: Transcript,
    start_sec: float,
    end_sec: float,
) -> tuple[list[WordSegment], list[TranscriptSegment]]:
    """Extract all words and transcript segments that overlap with [start_sec, end_sec]."""
    clip_words: list[WordSegment] = []
    clip_segs: list[TranscriptSegment] = []

    for seg in transcript.segments:
        if not (seg.end <= start_sec or seg.start >= end_sec):
            clip_segs.append(seg)
            if seg.words:
                for w in seg.words:
                    if w.end >= start_sec and w.start <= end_sec:
                        clip_words.append(w)
            else:
                tokens = seg.text.strip().split()
                if tokens:
                    dur = max(0.01, seg.end - seg.start) / len(tokens)
                    for i, t in enumerate(tokens):
                        ws = seg.start + i * dur
                        we = ws + dur
                        if we >= start_sec and ws <= end_sec:
                            clip_words.append(WordSegment(word=t, start=ws, end=we))

    return clip_words, clip_segs


def build_candidate_clip_plan(
    candidate: ClipCandidate,
    crop_path: list[int],
    src_w: int,
    fps: float,
    all_words: list[WordSegment],
    enable_cold_open: bool = False,
    enable_narrative: bool = False,
) -> ClipPlan:
    """
    Constructs an explicit Edit Decision List (ClipPlan) for a candidate clip.
    Handles per-shot layout modes and audio crossfades.
    """
    beats: list[Beat] = []
    reframe_plans = candidate.reframe_plans or []

    if enable_narrative and getattr(candidate, "_narrative_arc", None) is not None:
        # Phase 6 narrative arc beats — only used when NarrativeArc.to_clip_plan_beats() exists
        arc = candidate._narrative_arc
        if hasattr(arc, "to_clip_plan_beats"):
            beats = arc.to_clip_plan_beats()
        else:
            beats = []  # fallback to standard plan below
    elif enable_cold_open and getattr(candidate, "_cold_open_plan", None) is not None:
        # Phase 5 cold open variant
        beats = candidate._cold_open_plan.beats
    else:
        # Standard contiguous plan broken across camera shot boundaries if available
        if reframe_plans and len(reframe_plans) > 1:
            for idx, sp in enumerate(reframe_plans, 1):
                b_start = max(candidate.start_seconds, sp.start_seconds)
                b_end = min(candidate.end_seconds, sp.end_seconds)
                if b_end > b_start:
                    beats.append(Beat(
                        beat_id=idx,
                        role="body",
                        src_start=b_start,
                        src_end=b_end,
                        target_start=0.0,
                        target_end=b_end - b_start,
                        layout_mode=sp.layout_mode,
                        crop_x=sp.crop_x,
                    ))

        if not beats:
            # Single contiguous beat
            beats = [
                Beat(
                    beat_id=1,
                    role="body",
                    src_start=candidate.start_seconds,
                    src_end=candidate.end_seconds,
                    target_start=0.0,
                    target_end=candidate.duration_seconds,
                    layout_mode=candidate.layout_mode,
                )
            ]

    # Calculate target timeline offsets
    cur_t = 0.0
    for b in beats:
        b.target_start = cur_t
        b.target_end = cur_t + (b.src_end - b.src_start)
        cur_t = b.target_end

    plan = ClipPlan(
        clip_number=candidate.clip_number,
        title=candidate.title,
        beats=beats,
        virality_score=candidate.virality_score,
        format_variant="contiguous",
        layout_mode=candidate.layout_mode,
        words=all_words,
    )
    # Attach source words for non-linear subtitle remapping
    plan._source_words = all_words
    return plan


def run_pipeline_core(
    input_source: str,
    job_id: str,
    config: Optional[PipelineConfig] = None,
    progress_cb: Optional[Callable[[str, int, str], None]] = None,
    output_dir: Optional[Path] = None,
    enable_narrative: bool = False,
    enable_cold_open: bool = False,
) -> dict:
    """
    Executes the shared end-to-end Clipedics pipeline.
    Returns:
      {
        "video_path": Path,
        "video_title": str,
        "audio_path": Path,
        "audio_samples": np.ndarray,
        "sample_rate": int,
        "transcript": Transcript,
        "units": list[Unit],
        "crop_path": list[int],
        "shot_plans": list[ShotReframePlan],
        "candidates": list[ClipCandidate],
        "processed_clips": list[ProcessedClip],
        "plans": list[ClipPlan],
      }
    """
    cfg = config or PipelineConfig()
    from config.settings import OUTPUT_DIR
    out_base = output_dir or (OUTPUT_DIR / job_id)
    out_base.mkdir(parents=True, exist_ok=True)

    def _notify(status: str, pct: int, msg: str):
        if progress_cb:
            progress_cb(status, pct, msg)

    # ── Stage 1: Ingest Video ──────────────────────────────────────────────
    _notify("downloading", 5, "Ingesting video source...")
    video_path, video_title = prepare_video(input_source, job_id)
    _notify("downloading", 12, f"Ingested: {video_title[:50]}")

    # ── Stage 2: Extract Audio & Load Waveform ─────────────────────────────
    _notify("transcribing", 15, "Extracting 16kHz audio waveform...")
    audio_path = extract_audio(video_path, job_id)
    sr, audio_pcm = wavfile.read(str(audio_path))
    if audio_pcm.dtype == np.int16:
        audio_samples = audio_pcm.astype(np.float32) / 32768.0
    else:
        audio_samples = audio_pcm.astype(np.float32)

    # ── Stage 3: ASR Transcription ─────────────────────────────────────────
    _notify("transcribing", 22, "Transcribing with faster-whisper...")
    transcript = transcribe(audio_path, config=cfg)
    _notify("transcribing", 38, f"Transcribed {len(transcript.segments)} spoken segments")

    # ── Stage 4: Semantic Units with Real RMS Snapping ─────────────────────
    _notify("clipping", 42, "Segmenting semantic units & snapping to acoustic valleys...")
    units = build_units_from_transcript(transcript, audio_samples=audio_samples, sample_rate=sr)

    # ── Stage 5: Multi-Modal Feature Extraction ────────────────────────────
    _notify("clipping", 48, "Detecting camera shots and acoustic loudness...")
    shots = detect_shot_boundaries(video_path)
    units = enrich_units_with_features(units, audio_samples=audio_samples, sample_rate=sr, shots=shots)

    # ── Stage 6: Shot-Aware Face Tracking & Reframe ────────────────────────
    src_w, src_h, fps = 1920, 1080, 30.0
    crop_path: list[int] = []
    shot_plans: list[ShotReframePlan] = []

    if cfg.reframe:
        _notify("rendering", 55, "Tracking faces with One-Euro smoothing & layout detection...")
        try:
            crop_path, src_w, src_h, fps, shot_plans = compute_crop_path(
                video_path, shots=shots, return_shot_plans=True
            )
            # Update units with face presence from shot_plans (which carry real
            # MediaPipe face-detection results), NOT from crop_path existence alone.
            # crop_path is a smoothed x-offset; it always has values even when no
            # face was detected (fallback = center crop).  Use shot_plans.face_detected
            # when available, otherwise leave the field at its default (False).
            for u in units:
                sf = max(0, int(u.start_seconds * fps))
                ef = min(len(crop_path), int(u.end_seconds * fps))
                if ef > sf:
                    # Dominant crop x (normalized) is still useful for layout decisions
                    u.dominant_face_x = float(np.mean(crop_path[sf:ef])) / max(1.0, src_w)

                # Interval overlap: a unit has face_detected=True if any shot that overlaps
                # with [u.start_seconds, u.end_seconds] had a face detected. Mid-shot units
                # and multi-shot units are both correctly resolved.
                overlapping_shots = [
                    sp for sp in shot_plans
                    if max(u.start_seconds, sp.start_seconds) < min(u.end_seconds, sp.end_seconds)
                ]
                if overlapping_shots:
                    u.face_detected = any(getattr(sp, "face_detected", False) for sp in overlapping_shots)
                else:
                    u.face_detected = False
        except Exception as e:
            # Fallback to center crop if face tracking cannot initialize
            crop_w = int(src_h * 9 / 16)
            crop_path = [(src_w - crop_w) // 2] * int(transcript.duration_seconds * fps)

    # ── Stage 7: LLM Selection & Boundary Refinement ───────────────────────
    _notify("clipping", 68, "Groq AI selecting top viral moments...")
    candidates = select_clips(transcript, config=cfg, units=units)

    # Attach per-shot reframe plans and layout mode to candidates
    candidates = generate_clip_reframe_plans(
        candidates, crop_path, src_w, src_h, fps, shots=shots, shot_plans=shot_plans
    )

    # ── Stage 8: Build Non-Linear ClipPlans (EDL) ──────────────────────────
    _notify("rendering", 75, "Constructing non-linear Edit Decision Lists (EDL)...")
    clip_plans: list[ClipPlan] = []
    all_words = extract_all_words(transcript)

    for cand in candidates:
        cand_words, cand_segs = get_clip_words_and_segments(transcript, cand.start_seconds, cand.end_seconds)
        cand._clip_segments = cand_segs
        plan = build_candidate_clip_plan(
            candidate=cand,
            crop_path=crop_path,
            src_w=src_w,
            fps=fps,
            all_words=cand_words,
            enable_cold_open=enable_cold_open,
            enable_narrative=enable_narrative,
        )
        cand.clip_plan = plan
        clip_plans.append(plan)

    # ── Stage 9: Render Clips through Non-Linear Filtergraph ────────────────
    _notify("rendering", 80, "Rendering clips with loudnorm, crossfades & safe-zone captions...")
    crop_w = int(src_h * 9 / 16)
    processed_clips: list[ProcessedClip] = []

    for idx, (cand, plan) in enumerate(zip(candidates, clip_plans), 1):
        pct = 80 + int((idx / max(1, len(candidates))) * 18)
        _notify("rendering", pct, f"Rendering clip {idx}/{len(candidates)}: {cand.title[:35]}...")

        # Render through unified ClipPlan filtergraph
        processed = render_clip_plan(
            source_video=video_path,
            clip_plan=plan,
            crop_path=crop_path,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            crop_w=crop_w,
            out_dir=out_base,
            subtitle_style=cfg.subtitle_style,
            all_words=plan._source_words,
        )
        processed.candidate = cand
        processed_clips.append(processed)

    _notify("done", 100, f"Successfully rendered {len(processed_clips)} clips!")

    return {
        "video_path": video_path,
        "video_title": video_title,
        "audio_path": audio_path,
        "audio_samples": audio_samples,
        "sample_rate": sr,
        "transcript": transcript,
        "units": units,
        "crop_path": crop_path,
        "shot_plans": shot_plans,
        "candidates": candidates,
        "processed_clips": processed_clips,
        "plans": clip_plans,
        "src_w": src_w,
        "src_h": src_h,
        "fps": fps,
        "crop_w": crop_w,
    }

