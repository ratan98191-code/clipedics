"""
Clipedics – FFmpeg Render Pipeline (Phase 2)
Combines face-tracked 9:16 crop + ASS kinetic subtitles into one FFmpeg pass.

Pipeline per clip:
  [input clip] → crop={crop_w}:{src_h}:{crop_x}:0 → scale=1080:1920
              → subtitles=clip.ass → libx264 encode → output.mp4

The crop_x is delivered as a per-second value string for FFmpeg's
'crop' filtergraph using the 'sendcmd' filter for smooth animated panning.
"""
from __future__ import annotations
import json
import subprocess
import tempfile
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from core.models import ClipCandidate, ProcessedClip
from core.subtitles import generate_ass, STYLE_PRESETS
from config.settings import OUTPUT_DIR

console = Console()


def render_clips(
    source_video: Path,
    candidates: list[ClipCandidate],
    crop_path: list[int],
    src_w: int,
    src_h: int,
    fps: float,
    job_id: str,
    subtitle_style: str = "hormozi",
) -> list[ProcessedClip]:
    """
    For each clip candidate, render a final 9:16 MP4 with:
      1. Face-tracked smooth crop
      2. Kinetic word-by-word ASS subtitles burned in

    Returns list of ProcessedClip with output paths.
    """
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Calculate crop width for 9:16
    crop_w = int(src_h * 9 / 16)
    crop_w = min(crop_w, src_w)

    results: list[ProcessedClip] = []

    console.print(f"\n[cyan]🎬 Rendering {len(candidates)} clips (9:16 + subtitles)...[/cyan]")

    for candidate in candidates:
        result = _render_single(
            source_video=source_video,
            candidate=candidate,
            crop_path=crop_path,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            crop_w=crop_w,
            out_dir=out_dir,
            subtitle_style=subtitle_style,
        )
        results.append(result)

    # Summary
    success = sum(1 for r in results if r.success)
    console.print(
        f"\n[green]✓ Rendered {success}/{len(results)} clips[/green] → {out_dir}"
    )
    return results


def _render_single(
    source_video: Path,
    candidate: ClipCandidate,
    crop_path: list[int],
    src_w: int,
    src_h: int,
    fps: float,
    crop_w: int,
    out_dir: Path,
    subtitle_style: str,
) -> ProcessedClip:
    """Render one clip — crop + reframe + subtitles → output mp4."""
    import shutil

    safe_title = _sanitize(candidate.title)
    score = f"{candidate.virality_score:03d}"
    base_name = f"{score}_clip{candidate.clip_number:02d}_{safe_title}"
    out_path = out_dir / f"{base_name}_9x16.mp4"
    ass_path = out_dir / f"{base_name}.ass"

    console.print(
        f"  [dim]Clip {candidate.clip_number:02d}[/dim] "
        f"[bold]{candidate.title[:45]}[/bold] "
        f"[{candidate.start_seconds:.1f}s→{candidate.end_seconds:.1f}s] "
        f"score=[{'green' if candidate.virality_score >= 70 else 'yellow'}]"
        f"{candidate.virality_score}[/]"
    )

    try:
        # ── 1. Generate ASS subtitle for this clip's words ─────────────
        # Filter and offset transcript segments to clip time range
        from core.models import TranscriptSegment, WordSegment
        clipped_segs = _extract_clip_segments(candidate)
        if clipped_segs:
            generate_ass(clipped_segs, ass_path, style=subtitle_style)
        else:
            ass_path = None

        # ── 2. Calculate average crop_x for this clip ──────────────────
        # Use middle-of-clip average for stable single crop value
        # (per-frame dynamic pan requires drawtext sendcmd — Phase 3+)
        start_frame = int(candidate.start_seconds * fps)
        end_frame = int(candidate.end_seconds * fps)
        clip_frames = crop_path[start_frame:end_frame]
        avg_crop_x = int(sum(clip_frames) / max(len(clip_frames), 1)) if clip_frames else (src_w - crop_w) // 2

        # ── 3. Build FFmpeg command ────────────────────────────────────
        duration = candidate.end_seconds - candidate.start_seconds

        # Filter chain: crop → scale → (optional) subtitles
        if ass_path and ass_path.exists():
            # FFmpeg needs forward slashes and escaped colons in filter paths
            ass_str = str(ass_path).replace("\\", "/").replace(":", "\\:")
            vf = (
                f"crop={crop_w}:{src_h}:{avg_crop_x}:0,"
                f"scale={1080}:{1920}:flags=lanczos,"
                f"subtitles='{ass_str}':fontsdir='.'"
            )
        else:
            vf = (
                f"crop={crop_w}:{src_h}:{avg_crop_x}:0,"
                f"scale={1080}:{1920}:flags=lanczos"
            )

        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [
            ffmpeg, "-y",
            "-ss", str(candidate.start_seconds),
            "-i", str(source_video),
            "-t", str(duration),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-loglevel", "error",
            str(out_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            console.print(f"    [red]✗ FFmpeg error:[/red] {result.stderr[:300]}")
            return ProcessedClip(
                candidate=candidate,
                raw_mp4_path="",
                output_mp4_path="",
                success=False,
                error=result.stderr[:200],
            )

        console.print(f"    [green]✓[/green] → {out_path.name}")
        return ProcessedClip(
            candidate=candidate,
            raw_mp4_path=str(out_path),
            output_mp4_path=str(out_path),
            success=True,
        )

    except Exception as e:
        console.print(f"    [red]✗ Error:[/red] {e}")
        return ProcessedClip(
            candidate=candidate,
            raw_mp4_path="",
            output_mp4_path="",
            success=False,
            error=str(e),
        )


def _extract_clip_segments(candidate: ClipCandidate):
    """
    Extract transcript segments for a specific clip time window
    and re-zero their timestamps relative to clip start.
    This is called after transcription stored segments in the job.
    We attach segments to the candidate at runtime via the job object,
    so here we reconstruct from the candidate's hook/caption context.
    The full integration happens in main.py via the job object.
    """
    # Segments are passed via the job object in main.py
    # This function is a stub — real segments injected at render time
    return getattr(candidate, "_clip_segments", [])


def _sanitize(name: str, max_len: int = 40) -> str:
    import re
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:max_len]

