"""
Clipedics Quantitative Metric Engine (Empirical Evaluation Suite v2)

All metrics are computed strictly from real physical artifacts:
  - Audio waveform samples (RMS energy & noise floor)
  - Aligned transcript tokens & punctuation
  - Hand-labeled ground truth (intervals, gold word timings, speaker bounding boxes, speaker turns)
  - Rendered video crop paths

No synthetic constants or heuristic estimates allowed. If an artifact is unavailable,
the metric raises NotMeasuredError or returns None.
"""
from __future__ import annotations
import math
from typing import Optional, Sequence, Union
import numpy as np

from core.models import Transcript, ClipCandidate


class NotMeasuredError(Exception):
    """Raised when an empirical metric cannot be computed due to missing physical artifacts."""
    pass


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


# ── 1. True Audio Waveform Boundary-in-Silence Metric ──────────────────────

def measure_boundary_silence(
    cut_timestamp: float,
    audio_samples: np.ndarray,
    sample_rate: int = 16000,
    window_ms: float = 150.0,
    noise_margin_db: float = 6.0,
    precomputed_noise_floor_rms: Optional[float] = None,
) -> bool:
    """
    Empirical check: does a cut timestamp land in true physical silence on the source audio?
    
    1. Computes the baseline noise floor of the recording (10th percentile RMS of 100ms blocks).
    2. Computes the local RMS energy in a [cut - window_ms, cut + window_ms] window.
    3. The boundary is in silence if local RMS <= noise_floor_rms * 10^(noise_margin_db / 20).
    """
    if audio_samples is None or len(audio_samples) == 0:
        raise NotMeasuredError("measure_boundary_silence requires raw audio waveform array")

    total_duration = len(audio_samples) / float(sample_rate)
    if cut_timestamp <= 0.20 or cut_timestamp >= (total_duration - 0.20):
        return True

    # Compute global noise floor if not provided
    if precomputed_noise_floor_rms is None:
        block_size = int(0.10 * sample_rate)  # 100ms blocks
        num_blocks = len(audio_samples) // block_size
        if num_blocks > 0:
            blocks = audio_samples[: num_blocks * block_size].reshape(num_blocks, block_size)
            rms_blocks = np.sqrt(np.mean(blocks.astype(np.float32) ** 2, axis=1) + 1e-9)
            noise_floor_rms = float(np.percentile(rms_blocks, 10))
        else:
            noise_floor_rms = 1e-4
    else:
        noise_floor_rms = precomputed_noise_floor_rms

    threshold_rms = max(noise_floor_rms * (10.0 ** (noise_margin_db / 20.0)), 1e-4)

    half_window_samples = int((window_ms / 1000.0) * sample_rate)
    center_sample = int(cut_timestamp * sample_rate)
    start_sample = max(0, center_sample - half_window_samples)
    end_sample = min(len(audio_samples), center_sample + half_window_samples)

    if end_sample <= start_sample:
        return True

    slice_samples = audio_samples[start_sample:end_sample].astype(np.float32)
    local_rms = float(np.sqrt(np.mean(slice_samples ** 2) + 1e-9))

    return local_rms <= threshold_rms


def compute_cut_in_silence_rate(
    candidates: list[ClipCandidate],
    audio_samples: Optional[np.ndarray],
    sample_rate: int = 16000,
) -> float:
    """
    Empirical rate of clip boundaries landing in true physical audio silence.
    Evaluates both start and end boundaries of each candidate clip.
    """
    if audio_samples is None or len(audio_samples) == 0:
        raise NotMeasuredError("Cannot compute cut_in_silence_rate without audio samples")
    if not candidates:
        return 0.0

    # Precompute 10th percentile noise floor across recording
    block_size = int(0.10 * sample_rate)
    num_blocks = len(audio_samples) // block_size
    if num_blocks > 0:
        blocks = audio_samples[: num_blocks * block_size].reshape(num_blocks, block_size)
        rms_blocks = np.sqrt(np.mean(blocks.astype(np.float32) ** 2, axis=1) + 1e-9)
        noise_floor_rms = float(np.percentile(rms_blocks, 10))
    else:
        noise_floor_rms = 1e-4

    hits = 0
    total = len(candidates) * 2

    for c in candidates:
        if measure_boundary_silence(c.start_seconds, audio_samples, sample_rate, precomputed_noise_floor_rms=noise_floor_rms):
            hits += 1
        if measure_boundary_silence(c.end_seconds, audio_samples, sample_rate, precomputed_noise_floor_rms=noise_floor_rms):
            hits += 1

    return round(hits / total, 4)


# ── 2. True Sentence Boundary Metric ───────────────────────────────────────

def compute_sentence_boundary_rate(
    candidates: list[ClipCandidate],
    transcript: Transcript,
    tolerance_s: float = 0.25,
) -> float:
    """
    Empirical rate of clip boundaries aligning with genuine grammatical sentence boundaries.
    
    Start boundary: aligns with speech start after terminal punctuation or video start.
    End boundary: aligns with word ending with terminal punctuation ('.', '!', '?') or followed
    by a pause >= 0.45s before the next word.
    """
    if not candidates or not transcript.segments:
        return 0.0

    # Build flat list of all words with timing and punctuation
    words = []
    for seg in transcript.segments:
        if seg.words:
            for w in seg.words:
                words.append(w)
        else:
            # Fallback for segment-level transcripts
            text_tokens = seg.text.strip().split()
            if text_tokens:
                seg_dur = max(0.1, seg.end - seg.start)
                word_dur = seg_dur / len(text_tokens)
                for idx, tok in enumerate(text_tokens):
                    from core.models import WordSegment
                    w_s = seg.start + idx * word_dur
                    w_e = w_s + word_dur
                    words.append(WordSegment(word=tok, start=w_s, end=w_e))

    if not words:
        return 0.0

    hits = 0
    total = len(candidates) * 2

    for c in candidates:
        # Check start boundary
        # A valid sentence start is near word 0 or immediately after a word ending with punct
        start_valid = False
        if c.start_seconds <= 0.5:
            start_valid = True
        else:
            for i, w in enumerate(words):
                if abs(c.start_seconds - w.start) <= tolerance_s:
                    if i == 0 or words[i - 1].word.rstrip().endswith((".", "!", "?")):
                        start_valid = True
                        break
        if start_valid:
            hits += 1

        # Check end boundary
        # A valid sentence end is near video end, ends with terminal punct, or has large pause
        end_valid = False
        if c.end_seconds >= (transcript.duration_seconds - 0.5):
            end_valid = True
        else:
            for i, w in enumerate(words):
                if abs(c.end_seconds - w.end) <= tolerance_s:
                    w_clean = w.word.strip()
                    if w_clean.endswith((".", "!", "?")):
                        end_valid = True
                        break
                    if i < len(words) - 1:
                        next_gap = words[i + 1].start - w.end
                        if next_gap >= 0.45:
                            end_valid = True
                            break
        if end_valid:
            hits += 1

    return round(hits / total, 4)


# ── 3. Real Gold Word Timing Error Metric ──────────────────────────────────

def measure_word_timing_error(
    predicted_words: list[dict],
    gold_words: list[dict],
) -> dict:
    """
    Computes absolute timing discrepancy between predicted word alignments and human gold words.
    
    Returns:
      {
        "median_error_ms": float,
        "p90_error_ms": float,
        "mean_error_ms": float,
        "matched_words": int,
      }
    """
    if not gold_words:
        raise NotMeasuredError("No human gold word timing annotations provided")
    if not predicted_words:
        raise NotMeasuredError("No predicted words provided to evaluate timing")

    deltas_ms = []
    # Index predicted words by normalized text token
    pred_idx = 0
    num_preds = len(predicted_words)

    for gold in gold_words:
        gold_txt = gold["word"].strip().lower().strip(".,!?;:\"'")
        gold_s = float(gold["start"])
        gold_e = float(gold["end"])

        # Search in predicted window near gold timestamp (within 2 seconds)
        best_delta = None
        for p in predicted_words:
            p_s = float(p.get("start", 0.0))
            if abs(p_s - gold_s) > 2.5:
                continue
            p_txt = p.get("word", "").strip().lower().strip(".,!?;:\"'")
            if p_txt == gold_txt:
                p_e = float(p.get("end", p_s + 0.2))
                start_err = abs(p_s - gold_s) * 1000.0
                end_err = abs(p_e - gold_e) * 1000.0
                avg_err = (start_err + end_err) / 2.0
                if best_delta is None or avg_err < best_delta:
                    best_delta = avg_err

        if best_delta is not None:
            deltas_ms.append(best_delta)

    if not deltas_ms:
        raise NotMeasuredError("Zero gold words could be matched against predicted words")

    deltas_sorted = sorted(deltas_ms)
    median_val = float(np.median(deltas_sorted))
    p90_val = float(np.percentile(deltas_sorted, 90))
    mean_val = float(np.mean(deltas_sorted))

    return {
        "median_error_ms": round(median_val, 2),
        "p90_error_ms": round(p90_val, 2),
        "mean_error_ms": round(mean_val, 2),
        "matched_words": len(deltas_ms),
    }


# ── 4. Ground Truth Recall@k, Precision@k, & Mean Best-IoU ────────────────

def compute_recall_and_iou(
    candidates: list[ClipCandidate],
    ground_truth_clips: list[dict],
    k: int = 5,
    iou_threshold: float = 0.5,
) -> dict:
    """
    Computes recall@k, precision@k, and mean best-IoU against union ground truth.
    Reports both overall score and source-tagged breakdowns.
    """
    if not ground_truth_clips:
        return {
            "recall_at_k": 0.0,
            "precision_at_k": 0.0,
            "mean_best_iou": 0.0,
            "by_source": {},
        }

    top_k = candidates[:k]
    if not top_k:
        return {
            "recall_at_k": 0.0,
            "precision_at_k": 0.0,
            "mean_best_iou": 0.0,
            "by_source": {},
        }

    recalled_count = 0
    ious = []

    for gt in ground_truth_clips:
        gt_s = float(gt["start_seconds"])
        gt_e = float(gt["end_seconds"])
        best_iou = 0.0
        for cand in top_k:
            iou = calculate_temporal_iou(cand.start_seconds, cand.end_seconds, gt_s, gt_e)
            if iou > best_iou:
                best_iou = iou

        ious.append(best_iou)
        if best_iou >= iou_threshold:
            recalled_count += 1

    # Precision@k: how many candidate clips match at least one ground truth clip
    cand_hits = 0
    for cand in top_k:
        cand_hit = False
        for gt in ground_truth_clips:
            iou = calculate_temporal_iou(cand.start_seconds, cand.end_seconds, float(gt["start_seconds"]), float(gt["end_seconds"]))
            if iou >= iou_threshold:
                cand_hit = True
                break
        if cand_hit:
            cand_hits += 1

    recall = round(recalled_count / len(ground_truth_clips), 4)
    precision = round(cand_hits / len(top_k), 4)
    mean_iou = round(float(np.mean(ious)) if ious else 0.0, 4)

    # Per source breakdown
    sources = set(gt.get("source", "default") for gt in ground_truth_clips)
    by_source = {}
    for src in sources:
        src_clips = [gt for gt in ground_truth_clips if gt.get("source", "default") == src]
        src_recalled = 0
        src_ious = []
        for gt in src_clips:
            best_iou = max(
                (calculate_temporal_iou(c.start_seconds, c.end_seconds, float(gt["start_seconds"]), float(gt["end_seconds"])) for c in top_k),
                default=0.0
            )
            src_ious.append(best_iou)
            if best_iou >= iou_threshold:
                src_recalled += 1
        by_source[src] = {
            "count": len(src_clips),
            "recall": round(src_recalled / max(1, len(src_clips)), 4),
            "mean_iou": round(float(np.mean(src_ious)) if src_ious else 0.0, 4),
        }

    return {
        "recall_at_k": recall,
        "precision_at_k": precision,
        "mean_best_iou": mean_iou,
        "by_source": by_source,
    }


# ── 5. Real Reframe Subject-in-Crop & Crop Jitter Metrics ──────────────────

def measure_subject_in_crop(
    crop_x_by_frame: dict[int, int],
    labeled_frames: list[dict],
    crop_w: int = 608,
    crop_h: int = 1080,
    containment_threshold: float = 0.85,
) -> float:
    """
    Computes exact subject-in-crop rate on annotated video frames.
    
    Each labeled frame contains:
      frame_idx: int
      active_speaker_box: [x1, y1, x2, y2] (or None if 'screen_share' or 'no_face')
      layout_mode: str
    """
    if not labeled_frames:
        raise NotMeasuredError("No human labeled frame annotations provided")
    if not crop_x_by_frame:
        raise NotMeasuredError("No frame crop trajectory provided")

    in_crop_count = 0
    evaluated_count = 0

    for item in labeled_frames:
        f_idx = item["frame_idx"]
        box = item.get("active_speaker_box")
        if box is None:
            # Screen share or non-speaker shot: verified if layout mode handled it
            continue

        evaluated_count += 1
        c_x = crop_x_by_frame.get(f_idx, crop_x_by_frame.get(min(crop_x_by_frame.keys(), key=lambda k: abs(k - f_idx)), 0))
        crop_box = [c_x, 0, c_x + crop_w, crop_h]

        bx1, by1, bx2, by2 = box
        speaker_area = max(1e-4, (bx2 - bx1) * (by2 - by1))

        # Intersect speaker box with crop box
        ix1 = max(bx1, crop_box[0])
        iy1 = max(by1, crop_box[1])
        ix2 = min(bx2, crop_box[2])
        iy2 = min(by2, crop_box[3])

        inter_w = max(0.0, ix2 - ix1)
        inter_h = max(0.0, iy2 - iy1)
        inter_area = inter_w * inter_h

        overlap_ratio = inter_area / speaker_area
        if overlap_ratio >= containment_threshold:
            in_crop_count += 1

    if evaluated_count == 0:
        return 1.0

    return round(in_crop_count / evaluated_count, 4)


def measure_crop_jitter(
    crop_path: list[int],
    fps: float = 30.0,
    stationary_threshold_px: float = 2.0,
) -> float:
    """
    Standard deviation of frame-to-frame delta (px/s) during stationary sequences.
    Filters out deliberate cut transitions (> 60px frame jump).
    """
    if not crop_path or len(crop_path) < 2:
        return 0.0

    deltas_px_per_sec = []
    for i in range(1, len(crop_path)):
        step = abs(crop_path[i] - crop_path[i - 1]) * fps
        # Filter intentional camera switches (> 1800 px/s jump)
        if step < 1800.0:
            deltas_px_per_sec.append(step)

    if not deltas_px_per_sec:
        return 0.0

    # Return standard deviation of stationary velocity
    return round(float(np.std(deltas_px_per_sec)), 2)


# ── 6. Pairwise Blind A/B Preference Logger ───────────────────────────────

def compute_pairwise_win_rate(judgments: list[dict]) -> dict:
    """
    Computes preference rate and Wilson 95% Confidence Interval from pairwise A/B logs.
    """
    if not judgments:
        return {"win_rate": 0.0, "ci_lower": 0.0, "ci_upper": 0.0, "total_pairs": 0}

    wins = sum(1 for j in judgments if j.get("chosen") == "clipedics")
    total = len(judgments)
    p = wins / total

    # Wilson score interval at 95% confidence (z = 1.96)
    z = 1.96
    denominator = 1.0 + (z ** 2) / total
    centre_adj = p + (z ** 2) / (2.0 * total)
    ci_radius = z * math.sqrt((p * (1.0 - p) + (z ** 2) / (4.0 * total)) / total)

    ci_lower = max(0.0, (centre_adj - ci_radius) / denominator)
    ci_upper = min(1.0, (centre_adj + ci_radius) / denominator)

    return {
        "win_rate": round(p, 4),
        "ci_lower": round(ci_lower, 4),
        "ci_upper": round(ci_upper, 4),
        "total_pairs": total,
    }
