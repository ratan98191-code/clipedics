"""
Clipedics – Video Slicer
Cuts raw MP4 clips from the source video at LLM-specified timestamps using FFmpeg.
Fast stream-copy mode (no re-encode) for Phase 1 speed.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table

from config.settings import OUTPUT_DIR
from core.models import ClipCandidate, ProcessedClip

console = Console()


def slice_clips(
    video_path: Path,
    candidates: list[ClipCandidate],
    job_id: str,
    video_title: str = "clip",
) -> list[ProcessedClip]:
    """
    Cut each clip candidate from the source video using FFmpeg.
    Uses stream-copy (no re-encode) for maximum speed in Phase 1.

    Returns a list of ProcessedClip with output file paths.
    """
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[cyan]✂️  Slicing {len(candidates)} clips...[/cyan]")

    results: list[ProcessedClip] = []

    for candidate in candidates:
        safe_title = _sanitize_filename(candidate.title)
        rank = f"{candidate.virality_score:03d}"
        filename = f"{rank}_clip{candidate.clip_number:02d}_{safe_title}.mp4"
        out_path = out_dir / filename

        console.print(
            f"  [dim]Clip {candidate.clip_number:02d}[/dim] "
            f"[bold]{candidate.title[:45]}[/bold] "
            f"[{candidate.start_seconds:.1f}s → {candidate.end_seconds:.1f}s] "
            f"score=[bold {'green' if candidate.virality_score >= 70 else 'yellow' if candidate.virality_score >= 50 else 'red'}]"
            f"{candidate.virality_score}[/]"
        )

        success, error = _ffmpeg_cut(
            video_path=video_path,
            start=candidate.start_seconds,
            end=candidate.end_seconds,
            out_path=out_path,
        )

        results.append(
            ProcessedClip(
                candidate=candidate,
                raw_mp4_path=str(out_path) if success else "",
                output_mp4_path=str(out_path) if success else "",
                success=success,
                error=error,
            )
        )

    # Print summary table
    _print_summary(results, out_dir)

    return results


def _ffmpeg_cut(
    video_path: Path,
    start: float,
    end: float,
    out_path: Path,
    re_encode: bool = False,
) -> tuple[bool, str]:
    """
    Cut a clip using FFmpeg.
    re_encode=False → stream copy (fast, no quality loss, slight keyframe imprecision)
    re_encode=True  → full re-encode (slow, frame-accurate, needed for subtitles later)
    """
    duration = end - start

    if re_encode:
        # Accurate seek: input at start, re-encode
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(video_path),
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            "-loglevel", "error",
            str(out_path),
        ]
    else:
        # Stream copy: fast but may have slight keyframe offset at start
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-to", str(end),
            "-i", str(video_path),
            "-c", "copy",
            "-avoid_negative_ts", "1",
            "-loglevel", "error",
            str(out_path),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        console.print(f"    [red]✗ FFmpeg error:[/red] {result.stderr[:200]}")
        return False, result.stderr

    return True, ""


def _print_summary(results: list[ProcessedClip], out_dir: Path) -> None:
    """Print a rich table summary of all processed clips."""
    table = Table(
        title=f"\n✅ Clips saved to: {out_dir}",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("#", width=3, justify="right")
    table.add_column("Title", max_width=40)
    table.add_column("Duration", justify="right")
    table.add_column("Score", justify="center")
    table.add_column("Status")

    for r in results:
        c = r.candidate
        duration = f"{c.duration_seconds:.0f}s"
        score_color = "green" if c.virality_score >= 70 else "yellow" if c.virality_score >= 50 else "red"
        status = "[green]✓[/green]" if r.success else f"[red]✗ {r.error[:30]}[/red]"
        table.add_row(
            str(c.clip_number),
            c.title[:40],
            duration,
            f"[{score_color}]{c.virality_score}[/{score_color}]",
            status,
        )

    console.print(table)


def _sanitize_filename(name: str, max_len: int = 40) -> str:
    """Remove filesystem-unsafe characters from a string."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:max_len]

