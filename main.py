"""
Clipedics – Main CLI Entry Point
Full pipeline: Ingest → Transcribe → AI Clip Selection → Slice →
              Face Track → 9:16 Reframe → Kinetic Subtitles → Final MP4

Usage:
  python main.py --input "https://youtube.com/watch?v=..."
  python main.py --input video.mp4
  python main.py --input video.mp4 --clips 7 --min 20 --max 60
  python main.py --input video.mp4 --no-reframe          # skip face tracking
  python main.py --input video.mp4 --style minimal       # subtitle style
"""
from __future__ import annotations
import os
import sys
import uuid
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

app = typer.Typer(
    name="clipedics",
    help="🎬 AI-powered video clip generator — transforms long videos into viral shorts.",
    add_completion=False,
)
console = Console()


@app.command()
def run(
    input: str = typer.Option(..., "--input", "-i", help="YouTube URL or local video file path"),
    clips: int = typer.Option(None, "--clips", "-n", help="Number of clips to generate"),
    min_seconds: int = typer.Option(None, "--min", help="Minimum clip duration in seconds"),
    max_seconds: int = typer.Option(None, "--max", help="Maximum clip duration in seconds"),
    output_dir: str = typer.Option(None, "--output", "-o", help="Output directory for clips"),
    save_transcript: bool = typer.Option(False, "--transcript", "-t", help="Save transcript JSON"),
    save_metadata: bool = typer.Option(True, "--metadata", "-m", help="Save clip metadata JSON"),
    model: str = typer.Option(None, "--whisper-model", help="Whisper model: tiny/base/small/medium/large-v2"),
    reframe: bool = typer.Option(True, "--reframe/--no-reframe", help="Enable 9:16 face-tracked reframing"),
    style: str = typer.Option("hormozi", "--style", "-s", help="Subtitle style: hormozi | minimal | neon"),
) -> None:
    """Run the full Clipedics pipeline: ingest → transcribe → AI clip → 9:16 reframe → subtitles."""

    # ── Banner ─────────────────────────────────────────────────────────────
    console.print(Panel(
        Text("🎬 Clipedics", style="bold magenta", justify="center"),
        subtitle="AI Video Clip Generator — Vizard.ai Clone",
        border_style="magenta",
    ))

    # ── Pipeline Configuration ────────────────────────────────────────────
    from core.models import PipelineConfig
    pipeline_config = PipelineConfig.from_env(
        num_clips=clips,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
        subtitle_style=style,
        reframe=reframe,
        whisper_model=model,
    )
    if output_dir:
        import config.settings as settings
        settings.OUTPUT_DIR = Path(output_dir)
        settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Job ID ─────────────────────────────────────────────────────────────
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]
    console.print(f"[dim]Job ID: {job_id}[/dim]\n")

    # ── Import pipeline modules ────────────────────────────────────────────
    from core.models import ProcessingJob, TranscriptSegment, WordSegment
    from core.pipeline import run_pipeline_core, get_clip_words_and_segments

    job = ProcessingJob(input_source=input)

    try:
        def _cli_cb(status: str, pct: int, msg: str):
            console.print(f"[dim][{pct:02d}%][/dim] {msg}")

        result = run_pipeline_core(
            input_source=input,
            job_id=job_id,
            config=pipeline_config,
            progress_cb=_cli_cb,
            output_dir=settings.OUTPUT_DIR / job_id,
        )

        job.video_title = result["video_title"]
        job.video_path = str(result["video_path"])
        job.audio_path = str(result["audio_path"])
        job.transcript = result["transcript"]
        job.clip_candidates = result["candidates"]
        processed = result["processed_clips"]
        job.processed_clips = processed

        if save_transcript:
            _save_json(
                result["transcript"].model_dump(),
                settings.OUTPUT_DIR / job_id / "transcript.json",
                "Transcript"
            )

        # ── Step 5: Save metadata ──────────────────────────────────────────
        console.print("\n[bold]Final Step:[/bold] 💾 Saving metadata...")
        if save_metadata:
            metadata = _build_metadata(job, job_id)
            _save_json(
                metadata,
                settings.OUTPUT_DIR / job_id / "clips_metadata.json",
                "Metadata"
            )

        # ── Done ───────────────────────────────────────────────────────────
        successful = [c for c in processed if c.success]
        output_path = settings.OUTPUT_DIR / job_id
        console.print(Panel(
            f"[bold green]✅ Done![/bold green]\n"
            f"Generated [bold]{len(successful)}[/bold] clips in:\n"
            f"[cyan]{output_path}[/cyan]",
            border_style="green",
        ))

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Cancelled.[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"\n[red]✗ Pipeline failed:[/red] {e}")
        if os.getenv("DEBUG"):
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_clip_segments(all_segments, start: float, end: float):
    """
    Extract and re-zero transcript segments within a clip time window.
    Words and segment times are offset to be relative to clip start.
    """
    from core.models import TranscriptSegment, WordSegment

    result = []
    for seg in all_segments:
        if seg.end <= start or seg.start >= end:
            continue

        # Clip and re-zero segment bounds
        seg_start = max(0.0, seg.start - start)
        seg_end = min(end - start, seg.end - start)

        # Re-zero words that fall within this clip
        words = []
        for w in seg.words:
            if w.end <= start or w.start >= end:
                continue
            words.append(WordSegment(
                word=w.word,
                start=max(0.0, w.start - start),
                end=min(end - start, w.end - start),
                score=w.score,
            ))

        result.append(TranscriptSegment(
            text=seg.text,
            start=seg_start,
            end=seg_end,
            words=words,
        ))
    return result


def _print_candidates(candidates) -> None:
    from rich.table import Table
    table = Table(title="🤖 AI Selected Clips", header_style="bold cyan")
    table.add_column("#", width=3, justify="right")
    table.add_column("Title", max_width=40)
    table.add_column("Start", justify="right")
    table.add_column("End", justify="right")
    table.add_column("Dur", justify="right")
    table.add_column("Score", justify="center")
    for c in candidates:
        sc = "green" if c.virality_score >= 70 else "yellow" if c.virality_score >= 50 else "red"
        table.add_row(
            str(c.clip_number), c.title[:40],
            f"{c.start_seconds:.1f}s", f"{c.end_seconds:.1f}s",
            f"{c.duration_seconds:.0f}s",
            f"[{sc}]{c.virality_score}[/{sc}]",
        )
    console.print(table)


def _build_metadata(job, job_id: str) -> dict:
    return {
        "job_id": job_id,
        "input_source": job.input_source,
        "video_title": job.video_title,
        "generated_at": datetime.now().isoformat(),
        "clips": [
            {
                "clip_number": c.candidate.clip_number,
                "title": c.candidate.title,
                "start_seconds": c.candidate.start_seconds,
                "end_seconds": c.candidate.end_seconds,
                "duration_seconds": c.candidate.duration_seconds,
                "virality_score": c.candidate.virality_score,
                "virality_rationale": c.candidate.virality_rationale,
                "hook_sentence": c.candidate.hook_sentence,
                "suggested_caption": c.candidate.suggested_caption,
                "hashtags": c.candidate.hashtags,
                "file": c.output_mp4_path,
                "success": c.success,
            }
            for c in job.processed_clips
        ],
    }


def _save_json(data: dict, path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    console.print(f"[dim]  💾 {label} saved → {path.name}[/dim]")


def _get_clip_segments(segments, start_s, end_s):
    """Compatibility helper: extracts segments overlapping with time range."""
    from core.pipeline import get_clip_words_and_segments
    from core.models import Transcript
    dummy = Transcript(text="", segments=segments, duration_seconds=end_s)
    _, segs = get_clip_words_and_segments(dummy, start_s, end_s)
    return segs


if __name__ == "__main__":
    app()
