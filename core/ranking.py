"""
Clipedics Multi-Modal Candidate Ranker & Temporal NMS Engine (Phase 2)

Performs:
1. Multi-modal scoring: blends LLM salience with audio dynamics, visual pacing, and opening hook strength.
2. Temporal Non-Maximum Suppression (1D NMS): eliminates overlapping redundant clips using temporal IoU.
3. Global candidate pool selection: picks top non-redundant viral clips.
"""
from __future__ import annotations
import math
from typing import Sequence
import numpy as np

from core.models import ClipCandidate, Unit


def calculate_temporal_iou(
    cand_start: float, cand_end: float, gt_start: float, gt_end: float
) -> float:
    """Calculate temporal Intersection over Union (IoU) between two 1D time intervals."""
    intersection_start = max(cand_start, gt_start)
    intersection_end = min(cand_end, gt_end)
    intersection = max(0.0, intersection_end - intersection_start)

    union_start = min(cand_start, gt_start)
    union_end = max(cand_end, gt_end)
    union = max(1e-6, union_end - union_start)

    return intersection / union


def score_audio_salience(units: list[Unit]) -> float:
    """
    Score acoustic vitality based on loudness consistency, speech rate pacing, and pause cleaniness.
    Returns: score 0.0 – 100.0
    """
    if not units:
        return 50.0

    # 1. Speech rate score (ideal viral speech rate: 130 - 170 WPM)
    wpms = [u.speech_rate_wpm for u in units if u.speech_rate_wpm > 0]
    avg_wpm = float(np.mean(wpms)) if wpms else 140.0
    if 130 <= avg_wpm <= 170:
        wpm_score = 100.0
    elif 100 <= avg_wpm < 130:
        wpm_score = 70.0 + (avg_wpm - 100)
    elif 170 < avg_wpm <= 210:
        wpm_score = 100.0 - (avg_wpm - 170) * 0.75
    else:
        wpm_score = 50.0

    # 2. Loudness score (ideal broadcast loudness: -24 to -14 LUFS)
    loudness_vals = [u.loudness_lufs for u in units if u.loudness_lufs > -60]
    avg_lufs = float(np.mean(loudness_vals)) if loudness_vals else -20.0
    if -26.0 <= avg_lufs <= -14.0:
        loud_score = 100.0
    else:
        loud_score = max(40.0, 100.0 - abs(avg_lufs - (-20.0)) * 4.0)

    # 3. Clean boundary pause reward
    start_pause = units[0].pause_before_sec
    end_pause = units[-1].pause_after_sec
    pause_bonus = min(20.0, (start_pause + end_pause) * 15.0)

    audio_score = 0.50 * wpm_score + 0.35 * loud_score + 0.15 * (50.0 + pause_bonus)
    return float(np.clip(audio_score, 0.0, 100.0))


def score_visual_salience(units: list[Unit]) -> float:
    """
    Score visual engagement based on face presence and camera cut rhythm.
    Returns: score 0.0 – 100.0
    """
    if not units:
        return 50.0

    duration = max(1.0, units[-1].end_seconds - units[0].start_seconds)

    # Count unique shot transitions across units
    all_shots = set()
    for u in units:
        all_shots.update(u.shot_ids)
    num_cuts = max(0, len(all_shots) - 1)
    cuts_per_minute = (num_cuts / duration) * 60.0

    # Optimal short-form pacing: 4 to 18 cuts per minute
    if 4.0 <= cuts_per_minute <= 18.0:
        shot_score = 100.0
    elif cuts_per_minute < 4.0:
        shot_score = 65.0 + cuts_per_minute * 8.0
    else:
        shot_score = max(50.0, 100.0 - (cuts_per_minute - 18.0) * 2.5)

    # Face presence score
    faces = [u.face_detected for u in units]
    face_ratio = sum(faces) / len(faces) if faces else 0.5
    face_score = 80.0 if face_ratio > 0.4 else 60.0

    visual_score = 0.60 * shot_score + 0.40 * face_score
    return float(np.clip(visual_score, 0.0, 100.0))


VIRAL_HOOK_TRIGGERS = [
    # Question / curiosity openers
    "why", "how", "what if", "have you ever", "the reason", "did you know",
    "the biggest mistake", "the secret", "the truth about", "most people think",
    # Contrarian / surprise markers
    "actually", "never", "counter-intuitive", "fallacy", "paradox", "myth",
    "dangerous", "crisis", "lie", "wrong", "problem with", "warning",
    # Authority / storytelling
    "i discovered", "we realized", "years ago", "the single most", "rule number",
    "here is why", "listen carefully", "stop doing", "everybody gets this wrong"
]


def score_semantic_hook(opening_unit: Unit) -> float:
    """
    Score the linguistic opening hook strength based on curiosity triggers,
    questions, and contrarian markers.
    Returns: score 50.0 – 100.0
    """
    text_lower = opening_unit.text.lower()
    score = 60.0

    # 1. Question opener bonus
    if "?" in opening_unit.text or any(text_lower.startswith(q) for q in ["why", "how", "what", "is ", "are ", "can "]):
        score += 20.0

    # 2. Viral trigger keywords
    matches = sum(1 for trigger in VIRAL_HOOK_TRIGGERS if trigger in text_lower)
    score += min(25.0, matches * 10.0)

    # 3. Conciseness bonus (short punchy opening sentence)
    num_words = len(opening_unit.words)
    if 4 <= num_words <= 16:
        score += 10.0
    elif num_words > 25:
        score -= 10.0

    return float(np.clip(score, 50.0, 100.0))


def score_hook_salience(opening_unit: Unit) -> float:
    """
    Score the opening unit's punchiness (ideal hook is concise, 2-5 seconds, with strong linguistic curiosity).
    Returns: score 0.0 – 100.0
    """
    dur = opening_unit.duration_seconds
    if 2.0 <= dur <= 5.5:
        dur_score = 100.0
    elif dur < 2.0:
        dur_score = 70.0
    else:
        dur_score = max(40.0, 100.0 - (dur - 5.5) * 8.0)

    # Bonus for clean pause before the hook
    pause_bonus = min(20.0, opening_unit.pause_before_sec * 25.0)

    # Linguistic curiosity score
    semantic_score = score_semantic_hook(opening_unit)

    hook_score = 0.50 * dur_score + 0.35 * semantic_score + 0.15 * (50.0 + pause_bonus)
    return float(np.clip(hook_score, 0.0, 100.0))


def compute_composite_score(
    candidate: ClipCandidate,
    all_units: list[Unit],
    w_llm: float = 0.50,
    w_audio: float = 0.20,
    w_visual: float = 0.15,
    w_hook: float = 0.15,
) -> int:
    """
    Calculate composite multi-modal virality score combining LLM judgment with physical features.
    """
    # Find matching units in candidate span
    span_units = [
        u for u in all_units
        if u.start_seconds >= (candidate.start_seconds - 0.20)
        and u.end_seconds <= (candidate.end_seconds + 0.20)
    ]
    if not span_units:
        span_units = all_units[:3]

    s_llm = float(candidate.virality_score)
    s_audio = score_audio_salience(span_units)
    s_visual = score_visual_salience(span_units)
    s_hook = score_hook_salience(span_units[0])

    composite = (
        w_llm * s_llm +
        w_audio * s_audio +
        w_visual * s_visual +
        w_hook * s_hook
    )
    return int(np.clip(round(composite), 1, 100))


def temporal_nms(
    candidates: list[ClipCandidate],
    iou_threshold: float = 0.40,
    top_k: int = 5,
) -> list[ClipCandidate]:
    """
    Apply 1D Temporal Non-Maximum Suppression (NMS) over candidate time intervals.
    Eliminates redundant overlapping candidates and selects the top-K diverse clips.
    """
    if not candidates:
        return []

    # Sort descending by virality score
    sorted_cands = sorted(candidates, key=lambda c: c.virality_score, reverse=True)
    keep: list[ClipCandidate] = []

    for cand in sorted_cands:
        overlap = False
        for selected in keep:
            iou = calculate_temporal_iou(
                cand.start_seconds, cand.end_seconds,
                selected.start_seconds, selected.end_seconds
            )
            if iou >= iou_threshold:
                overlap = True
                break

        if not overlap:
            keep.append(cand)
            if len(keep) >= top_k:
                break

    # Renumber sequentially
    for idx, c in enumerate(keep, 1):
        c.clip_number = idx

    return keep


def generate_candidate_spans(
    units: list[Unit],
    min_seconds: float = 30.0,
    max_seconds: float = 80.0,
    max_candidates: int = 200,
) -> list[ClipCandidate]:
    """
    Generate valid candidate spans from units adhering to duration bounds and compute composite virality scores.
    """
    from core.units import build_clip_from_units

    if not units:
        return []

    spans: list[ClipCandidate] = []
    n = len(units)

    for i in range(n):
        for j in range(i, n):
            dur = units[j].end_seconds - units[i].start_seconds
            if dur > max_seconds:
                break
            if dur >= min_seconds:
                cand = build_clip_from_units(
                    start_unit_id=units[i].unit_id,
                    end_unit_id=units[j].unit_id,
                    units=units,
                    min_seconds=min_seconds,
                    max_seconds=max_seconds,
                )
                cand.virality_score = compute_composite_score(cand, units)
                spans.append(cand)
                if len(spans) >= max_candidates:
                    break
        if len(spans) >= max_candidates:
            break

    return spans


def select_best_clips_from_units(
    units: list[Unit],
    target_clips: int = 3,
    min_seconds: float = 30.0,
    max_seconds: float = 80.0,
    iou_threshold: float = 0.40,
) -> list[ClipCandidate]:
    """
    End-to-end multi-modal candidate selection:
    1. Generates bounded unit candidate spans.
    2. Scores each with multi-modal composite ranker (LLM/semantic + audio + visual + hook).
    3. Prunes overlapping clips using 1D temporal NMS on IoU.
    """
    candidates = generate_candidate_spans(
        units=units,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
    )
    return temporal_nms(candidates, iou_threshold=iou_threshold, top_k=target_clips)

