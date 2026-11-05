"""
Clipedics Semantic Unit Segmentation & RMS Valley Snapping (Phase 1)

Splits aligned word streams into atomic narrative units:
1. Split rule: word gap >= 0.35s OR sentence-final punctuation (. ! ?)
2. Snapping: snaps boundaries to local audio RMS energy valleys within ±150ms
3. Generates sequential numbered units (1, 2, 3...) for LLM indexing
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import Optional, Sequence
import numpy as np

from core.models import Transcript, WordSegment, Unit


def extract_all_words(transcript: Transcript) -> list[WordSegment]:
    """Flatten all aligned words chronologically from transcript segments."""
    words: list[WordSegment] = []
    for seg in transcript.segments:
        if seg.words:
            words.extend(seg.words)
        else:
            # Fallback for segments without word alignment: synthesize word tokens
            tokens = seg.text.strip().split()
            if not tokens:
                continue
            duration = max(0.01, seg.end - seg.start)
            token_dur = duration / len(tokens)
            for idx, tok in enumerate(tokens):
                w_start = round(seg.start + idx * token_dur, 2)
                w_end = round(seg.start + (idx + 1) * token_dur, 2)
                words.append(WordSegment(word=tok, start=w_start, end=w_end, score=0.95))

    words.sort(key=lambda w: w.start)
    return words


def compute_rms_envelope(
    audio_samples: np.ndarray,
    sample_rate: int = 16000,
    window_sec: float = 0.02,
    hop_sec: float = 0.005,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute RMS energy envelope over sliding frames.
    Returns: (rms_values, time_timestamps)
    """
    if len(audio_samples) == 0:
        return np.array([]), np.array([])

    win_len = max(1, int(window_sec * sample_rate))
    hop_len = max(1, int(hop_sec * sample_rate))

    # Pad audio to align frames
    pad_len = win_len // 2
    padded = np.pad(audio_samples, (pad_len, pad_len), mode="reflect")

    # Vectorized frame slicing
    num_frames = max(1, (len(padded) - win_len) // hop_len + 1)
    shape = (num_frames, win_len)
    strides = (padded.strides[0] * hop_len, padded.strides[0])
    frames = np.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)

    # RMS per frame
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    timestamps = np.arange(num_frames) * hop_sec
    return rms, timestamps


def find_rms_valley(
    target_time: float,
    rms: np.ndarray,
    timestamps: np.ndarray,
    search_radius_sec: float = 0.15,
) -> float:
    """
    Find local minimum RMS energy valley within ±search_radius_sec of target_time.
    """
    if len(rms) == 0 or len(timestamps) == 0:
        return target_time

    min_t = max(0.0, target_time - search_radius_sec)
    max_t = target_time + search_radius_sec

    mask = (timestamps >= min_t) & (timestamps <= max_t)
    if not np.any(mask):
        return target_time

    sub_rms = rms[mask]
    sub_times = timestamps[mask]

    min_idx = np.argmin(sub_rms)
    return float(sub_times[min_idx])


def build_units_from_transcript(
    transcript: Transcript,
    audio_samples: Optional[np.ndarray] = None,
    sample_rate: int = 16000,
    min_gap_sec: float = 0.35,
    max_unit_duration_sec: float = 15.0,
) -> list[Unit]:
    """
    Segment transcript words into atomic narrative Units and snap boundaries to RMS valleys.
    """
    words = extract_all_words(transcript)
    if not words:
        return []

    # Pre-calculate RMS envelope if audio waveform is provided
    rms_vals, rms_times = (
        compute_rms_envelope(audio_samples, sample_rate)
        if audio_samples is not None
        else (np.array([]), np.array([]))
    )

    # ── Step 1: Word clustering by gap & punctuation ───────────────────────
    unit_word_groups: list[list[WordSegment]] = []
    current_group: list[WordSegment] = [words[0]]

    for i in range(len(words) - 1):
        w_curr = words[i]
        w_next = words[i + 1]

        gap = max(0.0, w_next.start - w_curr.end)
        has_final_punct = w_curr.word.strip().endswith((".", "!", "?"))
        curr_duration = w_curr.end - current_group[0].start

        should_split = (
            gap >= min_gap_sec
            or has_final_punct
            or (curr_duration >= max_unit_duration_sec and gap >= 0.15)
        )

        if should_split:
            unit_word_groups.append(current_group)
            current_group = [w_next]
        else:
            current_group.append(w_next)

    if current_group:
        unit_word_groups.append(current_group)

    # ── Step 2: Build & snap Unit objects ─────────────────────────────────
    units: list[Unit] = []
    for idx, grp in enumerate(unit_word_groups, 1):
        raw_start = grp[0].start
        raw_end = grp[-1].end

        if len(rms_vals) > 0:
            snapped_start = round(find_rms_valley(raw_start, rms_vals, rms_times, search_radius_sec=0.15), 3)
            snapped_end = round(find_rms_valley(raw_end, rms_vals, rms_times, search_radius_sec=0.15), 3)
        else:
            # Acoustic silence padding fallback when audio waveform is not in memory
            # Half-gap padding into inter-word silence ensures pause boundary
            snapped_start = round(max(0.0, raw_start - 0.08), 3)
            snapped_end = round(raw_end + 0.08, 3)

        if snapped_end <= snapped_start:
            snapped_end = snapped_start + max(0.1, raw_end - raw_start)

        unit_text = " ".join(w.word for w in grp).strip()
        duration_min = max(0.01, (snapped_end - snapped_start) / 60.0)
        wpm = round(len(grp) / duration_min, 1)

        unit = Unit(
            unit_id=idx,
            start_seconds=snapped_start,
            end_seconds=snapped_end,
            raw_start_seconds=round(raw_start, 3),
            raw_end_seconds=round(raw_end, 3),
            text=unit_text,
            words=grp,
            speech_rate_wpm=wpm,
        )
        units.append(unit)

    # ── Step 3: Compute pause-before and pause-after features ─────────────
    for i, u in enumerate(units):
        if i > 0:
            u.pause_before_sec = round(max(0.0, u.start_seconds - units[i - 1].end_seconds), 3)
        else:
            u.pause_before_sec = round(u.start_seconds, 3)

        if i < len(units) - 1:
            u.pause_after_sec = round(max(0.0, units[i + 1].start_seconds - u.end_seconds), 3)
        else:
            u.pause_after_sec = round(max(0.0, transcript.duration_seconds - u.end_seconds), 3)

    return units


def assemble_contiguous_clips_from_units(
    units: list[Unit],
    target_clips: int = 3,
    min_seconds: float = 30.0,
    max_seconds: float = 90.0,
) -> list[ClipCandidate]:
    """
    Assemble contiguous spans of Units ensuring every clip boundary aligns
    with an atomic snapped Unit boundary (pause >= 0.35s / punctuation).
    """
    from core.models import ClipCandidate

    if not units:
        return []

    spans: list[tuple[int, int, float]] = []
    for i in range(len(units)):
        for j in range(i, len(units)):
            dur = units[j].end_seconds - units[i].start_seconds
            if min_seconds <= dur <= max_seconds:
                spans.append((i, j, dur))

    if not spans:
        # Fallback to single span
        spans = [(0, min(len(units) - 1, 3), units[min(len(units) - 1, 3)].end_seconds - units[0].start_seconds)]

    # Select evenly distributed candidate spans
    step = max(1, len(spans) // target_clips)
    selected_spans = spans[::step][:target_clips]

    candidates: list[ClipCandidate] = []
    for idx, (u_start_idx, u_end_idx, dur) in enumerate(selected_spans, 1):
        u_s = units[u_start_idx]
        u_e = units[u_end_idx]
        text_preview = " ".join(u.text for u in units[u_start_idx : u_end_idx + 1])
        candidates.append(ClipCandidate(
            clip_number=idx,
            start_seconds=round(u_s.start_seconds, 2),
            end_seconds=round(u_e.end_seconds, 2),
            title=f"Unit Clip {idx}: {u_s.text[:40]}...",
            virality_score=80,
            virality_rationale="Unit-aligned semantic span with RMS pause boundaries",
            hook_sentence=u_s.text,
            suggested_caption=text_preview[:120],
            hashtags=["clip", "viral"],
        ))

    return candidates
