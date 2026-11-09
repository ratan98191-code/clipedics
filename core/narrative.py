"""
Clipedics – Narrative Arc Planner & Beam Search Engine (Phase 6: Narrative Architecture)
Implements:
1. Narrative unit enrichment: role labeling (hook, build, peak, cliffhanger) and curiosity loops.
2. Multi-beat beam search optimizer assembling high-retention 4-part narrative arcs:
   [Hook (0-5s) → Build (10-25s) → Peak (8-20s) → Cliffhanger (3-8s)]
3. Loop closure bonus & dynamic duration constraint satisfaction.
4. Safe genre fallback and integration with Phase 6 Faithfulness Gate.
"""
from __future__ import annotations
import math
import re
import uuid
from typing import Optional, Sequence

import numpy as np

from core.models import Beat, ClipCandidate, ClipPlan, Unit
from core.ranking import score_hook_salience, score_semantic_hook, VIRAL_HOOK_TRIGGERS
from core.cold_open import create_cold_open_plan
from core.faithfulness import is_genre_safe_for_narrative_reorder, verify_faithfulness

# Narrative role markers
PEAK_TRIGGERS = [
    "discovered", "realized", "the single biggest", "the truth is", "exploded",
    "destroyed", "transformed", "shocking", "breakthrough", "genius", "insane",
    "the exact moment", "everything changed", "game changer", "vital", "catastrophic"
]

CLIFFHANGER_TRIGGERS = [
    "and then", "what happened next", "you won't believe", "to this day",
    "and that was just the beginning", "little did we know", "or so we thought",
    "the question remains", "nobody knows", "and that is why", "think about that",
    "let that sink in"
]


# ── Task 6.1: Narrative Unit Enrichment ────────────────────────────────────────

def label_narrative_units(units: list[Unit]) -> list[Unit]:
    """
    Enrich atomic Units with narrative roles (hook, build, peak, cliffhanger),
    curiosity loop opening/answering labels, and dynamic narrative energy.
    """
    if not units:
        return []

    for idx, u in enumerate(units):
        text_lower = u.text.lower()
        dur = u.duration_seconds

        # 1. Calculate dynamic narrative energy (0.0 to 100.0)
        # Based on loudness (-30 to -14 LUFS), WPM (100 to 180), and punctuation
        energy = 50.0
        if u.loudness_lufs > -22.0:
            energy += min(25.0, (u.loudness_lufs - (-22.0)) * 3.0)
        if u.speech_rate_wpm > 140.0:
            energy += min(15.0, (u.speech_rate_wpm - 140.0) * 0.5)
        if "!" in u.text:
            energy += 10.0
        u.narrative_energy = float(np.clip(energy, 20.0, 100.0))

        # 2. Curiosity Loop Opening & Role Hint Identification
        hook_score = score_hook_salience(u)

        # Check Cliffhanger / Open Question
        is_cliff = any(t in text_lower for t in CLIFFHANGER_TRIGGERS) or (
            idx == len(units) - 1 and "?" in u.text
        )

        # Check Peak Revelation
        is_peak = any(t in text_lower for t in PEAK_TRIGGERS) or (
            u.narrative_energy >= 75.0 and dur >= 3.0
        )

        # Check Hook / Opener
        is_hook = (hook_score >= 75.0 and dur <= 5.8) or (
            any(t in text_lower for t in VIRAL_HOOK_TRIGGERS[:10]) and dur <= 6.0
        )

        if is_cliff and (idx >= len(units) // 2 or any(t in text_lower for t in CLIFFHANGER_TRIGGERS)):
            u.role_hint = "cliffhanger"
        elif is_peak and dur >= 3.0:
            u.role_hint = "peak"
            # High energy peaks often resolve open loops
            u.answers_loop_of = "revelation_peak"
        elif is_hook and idx < len(units) - 1:
            u.role_hint = "hook"
            # Extract loop topic from question or trigger
            words = [w for w in text_lower.split() if len(w) > 3]
            u.opens_loop = " ".join(words[:4]) if words else "curiosity_hook"
        elif is_cliff:
            u.role_hint = "cliffhanger"
        elif is_hook:
            u.role_hint = "hook"
            words = [w for w in text_lower.split() if len(w) > 3]
            u.opens_loop = " ".join(words[:4]) if words else "curiosity_hook"
        else:
            u.role_hint = "build"

    return units


# ── Task 6.2: Multi-Beat Beam Search / Narrative Arc Planner ───────────────────

def extract_role_candidates(
    units: list[Unit],
    role: str,
    min_dur: float,
    max_dur: float,
) -> list[tuple[list[Unit], float]]:
    """
    Find contiguous spans of 1 to 3 units matching the specified narrative role and duration constraints.
    Returns list of (unit_span, score).
    """
    candidates: list[tuple[list[Unit], float]] = []
    n = len(units)

    for i in range(n):
        span: list[Unit] = []
        dur = 0.0
        for j in range(i, min(n, i + 3)):
            span.append(units[j])
            dur = span[-1].end_seconds - span[0].start_seconds
            if min_dur <= dur <= max_dur:
                # Score this span for the role
                score = 0.0
                if role == "hook":
                    score = score_hook_salience(span[0])
                    if len(span) == 1 and span[0].role_hint == "hook":
                        score += 20.0
                elif role == "build":
                    score = 60.0 + (dur / max_dur) * 20.0
                    if any(u.role_hint == "build" for u in span):
                        score += 15.0
                elif role == "peak":
                    score = max(u.narrative_energy for u in span)
                    if any(u.role_hint == "peak" for u in span):
                        score += 20.0
                elif role == "cliffhanger":
                    score = 65.0
                    if any(u.role_hint == "cliffhanger" for u in span):
                        score += 25.0
                    if "?" in span[-1].text or any(t in span[-1].text.lower() for t in CLIFFHANGER_TRIGGERS):
                        score += 15.0

                candidates.append((list(span), score))
            elif dur > max_dur:
                break

    # Sort descending by score
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def plan_narrative_arc(
    units: list[Unit],
    genre: str = "podcast",
    target_duration: float = 45.0,
    min_duration: float = 30.0,
    max_duration: float = 75.0,
    beam_width: int = 5,
) -> ClipPlan:
    """
    Assemble an optimized 4-part Narrative Arc ClipPlan:
    [Hook (2.5-5.5s) → Build (8-22s) → Peak (6-18s) → Cliffhanger (2.5-8s)]
    Satisfies narrative progression, curiosity loop resolution, and duration constraints.
    Falls back to safe Cold Open if genre is tutorial or if hard faithfulness gate fails.
    """
    # 1. Safe Genre Guard: Technical tutorials must stay contiguous or cold open
    if not is_genre_safe_for_narrative_reorder(genre):
        # Create standard candidate from first span and wrap in Cold Open
        cand = ClipCandidate(
            clip_number=1,
            start_seconds=units[0].start_seconds,
            end_seconds=units[-1].end_seconds,
            title="Overview",
            virality_score=75,
        )
        return create_cold_open_plan(cand, units)

    # 2. Enrich units with narrative roles
    labeled_units = label_narrative_units(units)

    # 3. Extract candidate unit pools per role
    hooks = extract_role_candidates(labeled_units, "hook", min_dur=2.0, max_dur=5.5)[:beam_width]
    builds = extract_role_candidates(labeled_units, "build", min_dur=8.0, max_dur=22.0)[:beam_width]
    peaks = extract_role_candidates(labeled_units, "peak", min_dur=6.0, max_dur=18.0)[:beam_width]
    cliffhangers = extract_role_candidates(labeled_units, "cliffhanger", min_dur=2.5, max_dur=8.0)[:beam_width]

    # Fallback if pools are sparse: use fallback spans
    if not hooks:
        hooks = [([labeled_units[0]], 70.0)]
    if not builds:
        mid_idx = len(labeled_units) // 3
        builds = [([labeled_units[mid_idx]], 65.0)]
    if not peaks:
        peak_idx = 2 * len(labeled_units) // 3
        peaks = [([labeled_units[peak_idx]], 75.0)]
    if not cliffhangers:
        cliffhangers = [([labeled_units[-1]], 65.0)]

    best_plan: Optional[ClipPlan] = None
    best_objective = -1e9

    # Beam Search across candidates
    for h_units, h_score in hooks:
        for b_units, b_score in builds:
            for p_units, p_score in peaks:
                for c_units, c_score in cliffhangers:
                    # Avoid duplicate overlapping units across beats
                    used_uids = set()
                    overlap = False
                    for group in (h_units, b_units, p_units, c_units):
                        for u in group:
                            if u.unit_id in used_uids:
                                overlap = True
                                break
                            used_uids.add(u.unit_id)
                        if overlap:
                            break
                    if overlap:
                        continue

                    # Total duration
                    d1 = h_units[-1].end_seconds - h_units[0].start_seconds
                    d2 = b_units[-1].end_seconds - b_units[0].start_seconds
                    d3 = p_units[-1].end_seconds - p_units[0].start_seconds
                    d4 = c_units[-1].end_seconds - c_units[0].start_seconds
                    total_dur = d1 + d2 + d3 + d4

                    if not (min_duration <= total_dur <= max_duration):
                        continue

                    # Curiosity loop resolution bonus
                    loop_bonus = 0.0
                    if h_units[0].opens_loop and (p_units[0].answers_loop_of or c_units[-1].answers_loop_of):
                        loop_bonus = 25.0

                    # Temporal penalty from target duration
                    dur_penalty = abs(total_dur - target_duration) * 1.5

                    # Objective function
                    objective = (
                        h_score * 1.2 +
                        b_score * 0.8 +
                        p_score * 1.4 +
                        c_score * 1.1 +
                        loop_bonus -
                        dur_penalty
                    )

                    if objective > best_objective:
                        # Construct beats with presentation timestamps
                        t = 0.0
                        b1 = Beat(
                            beat_id=1,
                            role="hook",
                            unit_ids=[u.unit_id for u in h_units],
                            src_start=h_units[0].start_seconds,
                            src_end=h_units[-1].end_seconds,
                            target_start=t,
                            target_end=round(t + d1, 3),
                            text=" ".join(u.text for u in h_units),
                        )
                        t += d1
                        b2 = Beat(
                            beat_id=2,
                            role="build",
                            unit_ids=[u.unit_id for u in b_units],
                            src_start=b_units[0].start_seconds,
                            src_end=b_units[-1].end_seconds,
                            target_start=round(t, 3),
                            target_end=round(t + d2, 3),
                            text=" ".join(u.text for u in b_units),
                        )
                        t += d2
                        b3 = Beat(
                            beat_id=3,
                            role="peak",
                            unit_ids=[u.unit_id for u in p_units],
                            src_start=p_units[0].start_seconds,
                            src_end=p_units[-1].end_seconds,
                            target_start=round(t, 3),
                            target_end=round(t + d3, 3),
                            text=" ".join(u.text for u in p_units),
                        )
                        t += d3
                        b4 = Beat(
                            beat_id=4,
                            role="cliffhanger",
                            unit_ids=[u.unit_id for u in c_units],
                            src_start=c_units[0].start_seconds,
                            src_end=c_units[-1].end_seconds,
                            target_start=round(t, 3),
                            target_end=round(t + d4, 3),
                            text=" ".join(u.text for u in c_units),
                        )

                        candidate_plan = ClipPlan(
                            plan_id=str(uuid.uuid4())[:8],
                            clip_number=1,
                            title=h_units[0].text[:40],
                            format_variant="narrative_arc",
                            beats=[b1, b2, b3, b4],
                            virality_score=int(min(98, 70 + objective * 0.1)),
                            virality_rationale="4-part narrative arc: hook -> build -> peak -> cliffhanger",
                            hook_sentence=b1.text,
                            suggested_caption=f"{b1.text} Watch till the end!",
                            hashtags=["story", "insight", "viral"],
                        )

                        # Hard Faithfulness Gate Check
                        is_faithful, reason = verify_faithfulness(candidate_plan, labeled_units, genre)
                        if is_faithful:
                            best_objective = objective
                            best_plan = candidate_plan

    # Fallback if no 4-beat plan satisfies constraints: assemble sequential plan
    if not best_plan:
        cand = ClipCandidate(
            clip_number=1,
            start_seconds=units[0].start_seconds,
            end_seconds=units[-1].end_seconds,
            title="Narrative Highlights",
            virality_score=75,
        )
        best_plan = create_cold_open_plan(cand, units)

    return best_plan


def plan_narrative_arcs_for_candidates(
    candidates: list[ClipCandidate],
    all_units: list[Unit],
    genre: str = "podcast",
) -> list[ClipPlan]:
    """Generate narrative ClipPlans for all candidates in a video."""
    plans = []
    for cand in candidates:
        # Find candidate units
        cand_units = [
            u for u in all_units
            if u.start_seconds >= cand.start_seconds - 0.20
            and u.end_seconds <= cand.end_seconds + 0.20
        ]
        if len(cand_units) >= 4 and is_genre_safe_for_narrative_reorder(genre):
            plan = plan_narrative_arc(cand_units, genre=genre)
            plan.clip_number = cand.clip_number
            plans.append(plan)
        else:
            plans.append(create_cold_open_plan(cand, all_units))
    return plans
