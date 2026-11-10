"""
Clipedics Empirical Evaluation Runner v3

Evaluates the REAL pipeline output against REAL hand-annotated ground truth.

Usage
-----
  # Run all dev-split videos that have cached data
  python evals/run.py

  # Run a single video by id
  python evals/run.py --video pod_lex_altman_openai

  # Write results to a markdown report
  python evals/run.py --report evals/BASELINE_V3.md

Prerequisites
-------------
  Each video in evals/bench_v2/cache/<video_id>/ must have:
    - transcript.json   Real ASR output from faster-whisper (or hand-corrected)
    - audio.wav         16kHz mono audio extracted from the real video
    - crop_path.json    Per-frame crop-x values from compute_crop_path()

  Each video in evals/bench_v2/ground_truth/ must have:
    - clips/<video_id>.json       Hand-labeled ground-truth clip intervals
    - word_timing/<video_id>.json Hand-corrected word timestamps (>=100 words)
    - reframe/<video_id>.json     Manually annotated face bounding boxes (>=40 frames)
    - turns/<video_id>.json       Speaker diarization turns

  See evals/bench_v2/README.md for how to generate these files.

No data is fabricated here.  If a cache file is missing, that metric is skipped
and recorded as "N/A" in the report.  Every number in the output traces directly
to a file on disk.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rich.console import Console
from rich.table import Table

from core.models import (
    Transcript,
    TranscriptSegment,
    WordSegment,
    PipelineConfig,
)
from core.clipper import select_clips
from evals.metrics import (
    compute_cut_in_silence_rate,
    compute_sentence_boundary_rate,
    measure_word_timing_error,
    compute_recall_and_iou,
    measure_subject_in_crop,
    measure_crop_jitter,
    NotMeasuredError,
)

console = Console()
BENCH_DIR = ROOT_DIR / "evals" / "bench_v2"
MANIFEST_PATH = BENCH_DIR / "manifest.json"
CACHE_DIR = BENCH_DIR / "cache"
GT_DIR = BENCH_DIR / "ground_truth"


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_manifest(split: str = "dev") -> list[dict]:
    if not MANIFEST_PATH.exists():
        console.print(f"[red]manifest.json not found at {MANIFEST_PATH}[/red]")
        return []
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return [v for v in data["videos"] if v.get("split") == split]


def load_transcript(video_id: str, cache_dir: Optional[Path] = None) -> Optional[Transcript]:
    base = cache_dir or CACHE_DIR
    path = base / video_id / "transcript.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    segs = []
    for s in raw.get("segments", []):
        words = [
            WordSegment(word=w["word"], start=w["start"], end=w["end"])
            for w in s.get("words", [])
        ]
        segs.append(TranscriptSegment(
            start=s["start"],
            end=s["end"],
            text=s["text"],
            words=words,
        ))
    return Transcript(
        segments=segs,
        language=raw.get("language", "en"),
        duration_seconds=raw.get("duration_seconds", segs[-1].end if segs else 0.0),
    )


def load_audio(video_id: str, cache_dir: Optional[Path] = None):
    """Returns (sample_rate, samples_float32) or (None, None)."""
    base = cache_dir or CACHE_DIR
    path = base / video_id / "audio.wav"
    if not path.exists():
        return None, None
    try:
        from scipy.io import wavfile
        import numpy as np
        sr, pcm = wavfile.read(str(path))
        if pcm.dtype.kind == "i":
            samples = pcm.astype("float32") / float(2 ** (pcm.dtype.itemsize * 8 - 1))
        else:
            samples = pcm.astype("float32")
        return sr, samples
    except Exception as exc:
        console.print(f"[yellow]  audio load failed for {video_id}: {exc}[/yellow]")
        return None, None


def load_crop_path(video_id: str, cache_dir: Optional[Path] = None) -> Optional[list[int]]:
    base = cache_dir or CACHE_DIR
    path = base / video_id / "crop_path.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_gt_clips(video_id: str, gt_dir: Optional[Path] = None) -> Optional[list[dict]]:
    base = gt_dir or GT_DIR
    path = base / "clips" / f"{video_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_gt_word_timing(video_id: str, gt_dir: Optional[Path] = None) -> Optional[list[dict]]:
    base = gt_dir or GT_DIR
    path = base / "word_timing" / f"{video_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_gt_reframe(video_id: str, gt_dir: Optional[Path] = None) -> Optional[list[dict]]:
    base = gt_dir or GT_DIR
    path = base / "reframe" / f"{video_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# ── Per-video evaluation ───────────────────────────────────────────────────────

NA = "N/A"


def evaluate_video(
    video_meta: dict,
    cache_dir: Optional[Path] = None,
    gt_dir: Optional[Path] = None,
) -> dict:
    vid = video_meta["id"]
    result = {
        "id": vid,
        "genre": video_meta.get("genre", ""),
        "silence_rate": NA,
        "sentence_boundary_rate": NA,
        "word_timing_mae_ms": NA,
        "clip_recall": NA,
        "clip_iou": NA,
        "in_crop_rate": NA,
        "crop_jitter_px_per_s": NA,
        "n_clips_selected": NA,
        "errors": [],
    }

    # ── Load transcript (required for all metrics) ─────────────────────────
    transcript = load_transcript(vid, cache_dir=cache_dir)
    if transcript is None:
        result["errors"].append("transcript.json missing — skipping video")
        return result

    sr, audio = load_audio(vid, cache_dir=cache_dir)
    crop_path = load_crop_path(vid, cache_dir=cache_dir)

    # ── Run the real clipper ───────────────────────────────────────────────
    try:
        cfg = PipelineConfig()
        candidates = select_clips(transcript, config=cfg)
        result["n_clips_selected"] = len(candidates)
    except Exception as exc:
        result["errors"].append(f"select_clips failed: {exc}")
        candidates = []

    if not candidates:
        return result

    # ── Metric 1: silence rate at cut points ───────────────────────────────
    if audio is not None and sr is not None:
        try:
            result["silence_rate"] = round(
                compute_cut_in_silence_rate(
                    candidates=candidates,
                    audio_samples=audio,
                    sample_rate=sr,
                ),
                3,
            )
        except (NotMeasuredError, Exception) as exc:
            result["errors"].append(f"silence_rate: {exc}")

    # ── Metric 2: sentence boundary rate ──────────────────────────────────
    try:
        result["sentence_boundary_rate"] = round(
            compute_sentence_boundary_rate(
                candidates=candidates,
                transcript=transcript,
            ),
            3,
        )
    except (NotMeasuredError, Exception) as exc:
        result["errors"].append(f"sentence_boundary_rate: {exc}")

    # ── Metric 3: word timing error ───────────────────────────────────────
    gt_words = load_gt_word_timing(vid, gt_dir=gt_dir)
    if gt_words:
        try:
            pred_words = [
                {"word": w.word, "start": w.start, "end": w.end}
                for seg in transcript.segments
                for w in (seg.words or [])
            ]
            gold_words = [
                {"word": w["word"], "start": float(w["start"]), "end": float(w["end"])}
                for w in gt_words
            ]
            timing_stats = measure_word_timing_error(pred_words, gold_words)
            result["word_timing_mae_ms"] = timing_stats.get("median_error_ms", NA)
        except (NotMeasuredError, Exception) as exc:
            result["errors"].append(f"word_timing_mae: {exc}")

    # ── Metric 4: clip recall and IoU vs ground truth ─────────────────────
    gt_clips = load_gt_clips(vid, gt_dir=gt_dir)
    if gt_clips:
        try:
            norm_gt = []
            for g in gt_clips:
                s = float(g.get("start_seconds", g.get("start", 0.0)))
                e = float(g.get("end_seconds", g.get("end", 0.0)))
                src = g.get("source", "default")
                norm_gt.append({"start_seconds": s, "end_seconds": e, "source": src})
            recall_iou_stats = compute_recall_and_iou(
                candidates=candidates,
                ground_truth_clips=norm_gt,
            )
            result["clip_recall"] = round(recall_iou_stats.get("recall_at_k", 0.0), 3)
            result["clip_iou"] = round(recall_iou_stats.get("mean_best_iou", 0.0), 3)
        except (NotMeasuredError, Exception) as exc:
            result["errors"].append(f"clip_recall_iou: {exc}")

    # ── Metrics 5–6: reframe / in-crop rate and jitter ────────────────────
    gt_reframe = load_gt_reframe(vid, gt_dir=gt_dir)
    if gt_reframe and crop_path:
        try:
            crop_x_by_frame = {i: x for i, x in enumerate(crop_path)}
            norm_frames = []
            for item in gt_reframe:
                f_idx = item.get("frame_idx", item.get("frame", 0))
                box = item.get("active_speaker_box")
                if box is None and "face_x1" in item:
                    box = [item["face_x1"], item["face_y1"], item["face_x2"], item["face_y2"]]
                norm_frames.append({
                    "frame_idx": int(f_idx),
                    "active_speaker_box": box,
                    "layout_mode": item.get("layout_mode", "center_crop"),
                })
            in_crop = measure_subject_in_crop(
                crop_x_by_frame=crop_x_by_frame,
                labeled_frames=norm_frames,
                crop_w=608,
                crop_h=1080,
            )
            result["in_crop_rate"] = round(in_crop, 3)
        except (NotMeasuredError, Exception) as exc:
            result["errors"].append(f"in_crop_rate: {exc}")
        try:
            jitter = measure_crop_jitter(crop_path, fps=30.0)
            result["crop_jitter_px_per_s"] = round(jitter, 1)
        except (NotMeasuredError, Exception) as exc:
            result["errors"].append(f"crop_jitter: {exc}")

    return result


# ── Report generation ──────────────────────────────────────────────────────────

def build_rich_table(results: list[dict]) -> Table:
    t = Table(title="Clipedics Evaluation — Real Pipeline on Real Data", show_lines=True)
    t.add_column("Video ID", style="cyan", no_wrap=True)
    t.add_column("Genre", style="dim")
    t.add_column("Clips", justify="right")
    t.add_column("Silence@Cut", justify="right")
    t.add_column("SentBound", justify="right")
    t.add_column("Word MAE ms", justify="right")
    t.add_column("Recall", justify="right")
    t.add_column("IoU", justify="right")
    t.add_column("InCrop", justify="right")
    t.add_column("Jitter px/s", justify="right")

    for r in results:
        errs = "; ".join(r["errors"]) if r["errors"] else ""
        vid_col = f"[red]{r['id']}[/red] [dim]{errs}[/dim]" if errs else r["id"]
        t.add_row(
            vid_col,
            r["genre"],
            str(r["n_clips_selected"]),
            str(r["silence_rate"]),
            str(r["sentence_boundary_rate"]),
            str(r["word_timing_mae_ms"]),
            str(r["clip_recall"]),
            str(r["clip_iou"]),
            str(r["in_crop_rate"]),
            str(r["crop_jitter_px_per_s"]),
        )
    return t


def write_markdown_report(results: list[dict], path: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Clipedics Pipeline Evaluation — {now}",
        "",
        "> **All numbers below are computed from real cached pipeline output and hand-annotated ground truth.**",
        "> N/A = cache file missing; run the pipeline on the real video first.",
        "",
        "| Video ID | Genre | Clips | Silence@Cut | SentBound | Word MAE ms | Recall | IoU | InCrop | Jitter px/s | Errors |",
        "|----------|-------|-------|-------------|-----------|-------------|--------|-----|--------|-------------|--------|",
    ]
    for r in results:
        errs = "; ".join(r["errors"]) if r["errors"] else ""
        lines.append(
            f"| {r['id']} | {r['genre']} | {r['n_clips_selected']} "
            f"| {r['silence_rate']} | {r['sentence_boundary_rate']} "
            f"| {r['word_timing_mae_ms']} | {r['clip_recall']} | {r['clip_iou']} "
            f"| {r['in_crop_rate']} | {r['crop_jitter_px_per_s']} | {errs} |"
        )
    lines += [
        "",
        "---",
        "",
        "## Notes",
        "",
        "- `Silence@Cut`: fraction of clip start-points that land in an acoustic valley (lower RMS than neighbourhood).",
        "- `SentBound`: fraction of clip boundaries that align with sentence-final punctuation.",
        "- `Word MAE ms`: mean absolute timing error vs hand-corrected timestamps.",
        "- `Recall`: fraction of ground-truth clips matched by pipeline output (IoU >= 0.5).",
        "- `IoU`: mean intersection-over-union for matched pairs.",
        "- `InCrop`: fraction of labelled face frames where the bounding box is inside the crop window.",
        "- `Jitter px/s`: mean absolute frame-to-frame crop displacement (lower = smoother).",
        "",
        "_No interpretation or finding text is generated automatically._",
        "_Read the raw numbers above and form your own conclusions._",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Report written to {path}[/green]")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Clipedics Evaluation Runner v3")
    parser.add_argument("--split", default="dev", choices=["dev", "test"], help="Dataset split")
    parser.add_argument("--video", default=None, help="Evaluate a single video by id")
    parser.add_argument("--report", default=None, help="Write markdown report to this path")
    args = parser.parse_args()

    videos = load_manifest(split=args.split)
    if not videos:
        console.print("[red]No videos in manifest. Exiting.[/red]")
        sys.exit(1)

    if args.video:
        videos = [v for v in videos if v["id"] == args.video]
        if not videos:
            console.print(f"[red]Video '{args.video}' not found in {args.split} split[/red]")
            sys.exit(1)

    cached = [v for v in videos if (CACHE_DIR / v["id"] / "transcript.json").exists()]
    skipped = len(videos) - len(cached)
    if skipped:
        console.print(
            f"[yellow]Skipping {skipped}/{len(videos)} video(s) — no transcript.json in cache.[/yellow]"
            f"\nRun the pipeline on those videos first, then copy transcript.json to evals/bench_v2/cache/<id>/."
        )
    if not cached:
        console.print("[red]No cached data found. Nothing to evaluate.[/red]")
        sys.exit(0)

    results = []
    for meta in cached:
        console.print(f"\nEvaluating [cyan]{meta['id']}[/cyan] ...")
        t0 = time.perf_counter()
        r = evaluate_video(meta)
        elapsed = time.perf_counter() - t0
        status = "[green]OK[/green]" if not r["errors"] else f"[yellow]{len(r['errors'])} warning(s)[/yellow]"
        console.print(f"  {status}  {elapsed:.1f}s")
        results.append(r)

    console.print()
    console.print(build_rich_table(results))

    if args.report:
        write_markdown_report(results, Path(args.report))


if __name__ == "__main__":
    main()
