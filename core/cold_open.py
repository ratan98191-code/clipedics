"""
Clipedics – Cold Open Variant Generator (Phase 5: EDL Architecture)
Transforms contiguous clip candidates into high-retention "Cold Open" non-linear edits.
Pulls the highest-salience hook line to Beat 1 (0.0s - 4.5s) to hook the viewer,
followed immediately by the narrative body.
"""
from __future__ import annotations
import uuid
from typing import Optional
import numpy as np

from core.models import Beat, ClipCandidate, ClipPlan, Unit
from core.ranking import score_hook_salience


def find_candidate_units(
    candidate: ClipCandidate,
    units: list[Unit],
    tolerance_sec: float = 0.20,
) -> list[Unit]:
    """Return all units that overlap with the candidate's start/end window."""
    return [
        u for u in units
        if u.start_seconds >= (candidate.start_seconds - tolerance_sec)
        and u.end_seconds <= (candidate.end_seconds + tolerance_sec)
    ]


def select_best_hook_unit(candidate_units: list[Unit]) -> tuple[int, Unit, float]:
    """
    Find the unit with the highest hook salience score within the candidate span.
    Returns: (index_in_candidate_units, best_unit, best_score).
    """
    if not candidate_units:
        raise ValueError("Cannot select hook unit from empty candidate units list.")

    best_idx = 0
    best_unit = candidate_units[0]
    best_score = -1.0

    for idx, unit in enumerate(candidate_units):
        score = score_hook_salience(unit)
        # Boost for louder/more energetic delivery
        if unit.loudness_lufs > -22.0:
            score += 8.0
        # Optimal duration for a cold open teaser is 2.5 to 5.5 seconds
        if 2.5 <= unit.duration_seconds <= 5.5:
            score += 10.0
        elif unit.duration_seconds > 8.0:
            score -= 15.0

        if score > best_score:
            best_score = score
            best_idx = idx
            best_unit = unit

    return best_idx, best_unit, best_score


def create_cold_open_plan(
    candidate: ClipCandidate,
    all_units: list[Unit],
    repeat_body_contiguously: bool = True,
) -> ClipPlan:
    """
    Build a non-linear ClipPlan (EDL) using the Cold Open structure:
    - Beat 1: The highest-salience curiosity/hook statement (3–5s teaser).
    - Beat 2: The narrative body.

    If the best hook is already the first unit (or the clip has <= 2 units),
    the clip remains a contiguous sequence without redundant duplication.
    """
    candidate_units = find_candidate_units(candidate, all_units)

    # Fallback if no matching units found: single contiguous beat
    if not candidate_units or len(candidate_units) <= 2:
        beat = Beat(
            beat_id=1,
            role="body",
            unit_ids=[u.unit_id for u in candidate_units],
            src_start=candidate.start_seconds,
            src_end=candidate.end_seconds,
            target_start=0.0,
            target_end=candidate.duration_seconds,
            text=candidate.hook_sentence or candidate.title,
            layout_mode=candidate.layout_mode,
        )
        return ClipPlan(
            plan_id=str(uuid.uuid4())[:8],
            clip_number=candidate.clip_number,
            title=candidate.title,
            format_variant="contiguous",
            beats=[beat],
            virality_score=candidate.virality_score,
            virality_rationale=candidate.virality_rationale,
            hook_sentence=candidate.hook_sentence,
            suggested_caption=candidate.suggested_caption,
            hashtags=candidate.hashtags,
            layout_mode=candidate.layout_mode,
        )

    best_idx, hook_unit, hook_score = select_best_hook_unit(candidate_units)

    beats: list[Beat] = []
    current_target_time = 0.0

    # Case A: Best hook is already at the very beginning of the clip
    if best_idx == 0:
        # Beat 1: Hook opening
        b1_dur = hook_unit.duration_seconds
        beats.append(Beat(
            beat_id=1,
            role="cold_open",
            unit_ids=[hook_unit.unit_id],
            src_start=hook_unit.start_seconds,
            src_end=hook_unit.end_seconds,
            target_start=current_target_time,
            target_end=round(current_target_time + b1_dur, 3),
            text=hook_unit.text,
            layout_mode=candidate.layout_mode,
        ))
        current_target_time += b1_dur

        # Beat 2: Rest of narrative body
        remaining_units = candidate_units[1:]
        if remaining_units:
            b2_start = remaining_units[0].start_seconds
            b2_end = remaining_units[-1].end_seconds
            b2_dur = b2_end - b2_start
            beats.append(Beat(
                beat_id=2,
                role="body",
                unit_ids=[u.unit_id for u in remaining_units],
                src_start=b2_start,
                src_end=b2_end,
                target_start=round(current_target_time, 3),
                target_end=round(current_target_time + b2_dur, 3),
                text=" ".join(u.text for u in remaining_units),
                layout_mode=candidate.layout_mode,
            ))
        format_variant = "contiguous"

    # Case B: Best hook is later in the clip -> Non-linear Cold Open Reorder
    else:
        # Beat 1: Cold Open Teaser pulled from downstream
        b1_dur = hook_unit.duration_seconds
        beats.append(Beat(
            beat_id=1,
            role="cold_open",
            unit_ids=[hook_unit.unit_id],
            src_start=hook_unit.start_seconds,
            src_end=hook_unit.end_seconds,
            target_start=current_target_time,
            target_end=round(current_target_time + b1_dur, 3),
            text=hook_unit.text,
            layout_mode=candidate.layout_mode,
        ))
        current_target_time += b1_dur

        # Beat 2: Full contiguous narrative body
        b2_start = candidate.start_seconds
        b2_end = candidate.end_seconds
        b2_dur = b2_end - b2_start
        beats.append(Beat(
            beat_id=2,
            role="body",
            unit_ids=[u.unit_id for u in candidate_units],
            src_start=b2_start,
            src_end=b2_end,
            target_start=round(current_target_time, 3),
            target_end=round(current_target_time + b2_dur, 3),
            text=" ".join(u.text for u in candidate_units),
            layout_mode=candidate.layout_mode,
        ))
        format_variant = "cold_open"

    return ClipPlan(
        plan_id=str(uuid.uuid4())[:8],
        clip_number=candidate.clip_number,
        title=candidate.title,
        format_variant=format_variant,
        beats=beats,
        virality_score=candidate.virality_score,
        virality_rationale=candidate.virality_rationale,
        hook_sentence=hook_unit.text if format_variant == "cold_open" else candidate.hook_sentence,
        suggested_caption=candidate.suggested_caption,
        hashtags=candidate.hashtags,
        layout_mode=candidate.layout_mode,
    )


def create_cold_open_plans(
    candidates: list[ClipCandidate],
    all_units: list[Unit],
) -> list[ClipPlan]:
    """Generate Cold Open ClipPlans for a collection of candidates."""
    return [create_cold_open_plan(c, all_units) for c in candidates]
