"""
Clipedics – FFmpeg Render Pipeline (Phase 5: EDL Non-Linear Multi-Trim & Concat)
Combines:
  1. Multi-trim non-linear video/audio concatenation (ClipPlan EDL)
  2. 30ms anti-click audio crossfading at cut boundaries
  3. Broadcast loudness normalization (EBU R128: -16 LUFS)
  4. Shot-aware 9:16 reframe & dynamic layout modes
  5. Piecewise ASS kinetic subtitles burned in with sub-frame synchronization
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union

import numpy as np
from rich.console import Console

from core.models import Beat, ClipCandidate, ClipPlan, ProcessedClip, PipelineConfig, WordSegment, TranscriptSegment
from core.subtitles import generate_ass, remap_words, STYLE_PRESETS
from config.settings import OUTPUT_DIR

console = Console()


def build_clip_plan_filtergraph(
    clip_plan: ClipPlan,
    crop_path: list[int],
    src_w: int,
    src_h: int,
    fps: float,
    crop_w: int,
    ass_path: Optional[Path] = None,
) -> tuple[str, str, str]:
    """
    Build the full FFmpeg -filter_complex string for non-linear multi-trim editing:
      - per-beat video trimming & layout crop
      - per-beat audio trimming with 30ms anti-click crossfading
      - multi-stream video & audio concat
      - broadcast loudness normalization (-16 LUFS)
      - burned-in kinetic subtitles

    Returns: (filter_complex_str, vout_label, aout_label)
    """
    beats = clip_plan.beats
    if not beats:
        raise ValueError("Cannot build filtergraph for empty ClipPlan beats.")

    crop_w = min(int(crop_w), src_w)
    crop_w = crop_w - (crop_w % 2)

    n = len(beats)
    filter_parts: list[str] = []
    v_labels: list[str] = []
    a_labels: list[str] = []

    for i, beat in enumerate(beats):
        s = beat.src_start
        e = beat.src_end
        dur = max(0.01, e - s)

        # 30ms micro-fade to eliminate clicks/pops at cut points
        fade_d = min(0.030, dur / 3.0)
        fade_out_st = max(0.0, dur - fade_d)

        # Determine horizontal crop for this beat
        if beat.crop_x is not None:
            bx = beat.crop_x
        elif crop_path:
            s_f = max(0, int(round(s * fps)))
            e_f = min(len(crop_path), int(round(e * fps)))
            sub = crop_path[s_f:e_f]
            bx = int(np.mean(sub)) if sub else (src_w - crop_w) // 2
        else:
            bx = (src_w - crop_w) // 2
        bx = max(0, min(src_w - crop_w, bx))

        layout = beat.layout_mode or "center_crop"

        # ── Video stream for beat i ──
        if layout == "blur_background":
            filter_parts.append(
                f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,split=2[fg_{i}][bg_{i}]"
            )
            filter_parts.append(
                f"[bg_{i}]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.15[bg_blur_{i}]"
            )
            filter_parts.append(
                f"[fg_{i}]scale=1080:-1[fg_sc_{i}]"
            )
            filter_parts.append(
                f"[bg_blur_{i}][fg_sc_{i}]overlay=(W-w)/2:(H-h)/2[v_proc_{i}]"
            )
        elif layout == "split_screen":
            x1 = max(0, bx - crop_w // 2)
            x2 = min(src_w - crop_w, bx + crop_w // 2)
            filter_parts.append(
                f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,split=2[s1_{i}][s2_{i}]"
            )
            filter_parts.append(
                f"[s1_{i}]crop={crop_w}:{src_h}:{x1}:0,scale=1080:960[top_{i}]"
            )
            filter_parts.append(
                f"[s2_{i}]crop={crop_w}:{src_h}:{x2}:0,scale=1080:960[bot_{i}]"
            )
            filter_parts.append(
                f"[top_{i}][bot_{i}]vstack[v_proc_{i}]"
            )
        else:  # center_crop
            filter_parts.append(
                f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,crop={crop_w}:{src_h}:{bx}:0,scale=1080:1920:flags=lanczos[v_proc_{i}]"
            )
        v_labels.append(f"[v_proc_{i}]")

        # ── Audio stream for beat i ──
        # Apply 30ms micro-fades ONLY at true non-contiguous cuts (gaps in the
        # source timeline). Within continuous speech that has been segmented by
        # camera shot boundaries the samples are contiguous, so a fade-in here
        # would create an audible dip every few seconds.
        prev_beat = beats[i - 1] if i > 0 else None
        next_beat = beats[i + 1] if i < n - 1 else None
        is_cut_in  = (prev_beat is None) or (abs(beat.src_start - prev_beat.src_end) > 0.001)
        is_cut_out = (next_beat is None) or (abs(next_beat.src_start - beat.src_end) > 0.001)

        a_parts = [f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS"]
        if is_cut_in:
            a_parts.append(f"afade=t=in:ss=0:d={fade_d:.3f}")
        if is_cut_out:
            a_parts.append(f"afade=t=out:st={fade_out_st:.3f}:d={fade_d:.3f}")
        filter_parts.append(",".join(a_parts) + f"[a_proc_{i}]")
        a_labels.append(f"[a_proc_{i}]")

    # ── Concat multi-trim streams ──
    concat_in = "".join(f"{v}{a}" for v, a in zip(v_labels, a_labels))
    filter_parts.append(f"{concat_in}concat=n={n}:v=1:a=1[v_concat][a_concat]")

    # ── Broadcast loudness normalization ──
    filter_parts.append("[a_concat]loudnorm=I=-16:TP=-1.5:LRA=11[a_norm]")

    # ── Burn in kinetic subtitles ──
    if ass_path and ass_path.exists():
        ass_str = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        filter_parts.append(f"[v_concat]subtitles='{ass_str}':fontsdir='.'[v_out]")
        vout_label = "[v_out]"
    else:
        vout_label = "[v_concat]"

    aout_label = "[a_norm]"
    filter_complex = ";".join(filter_parts)
    return filter_complex, vout_label, aout_label


def render_clip_plan(
    source_video: Path,
    clip_plan: ClipPlan,
    crop_path: list[int],
    src_w: int,
    src_h: int,
    fps: float,
    crop_w: int,
    out_dir: Path,
    subtitle_style: str = "hormozi",
    all_words: Optional[list[WordSegment]] = None,
) -> ProcessedClip:
    """Render a non-linear ClipPlan (EDL) using FFmpeg multi-trim filtergraph."""
    safe_title = _sanitize(clip_plan.title)
    score = f"{clip_plan.virality_score:03d}"
    variant = clip_plan.format_variant
    base_name = f"{score}_clip{clip_plan.clip_number:02d}_{variant}_{safe_title}"
    out_path = out_dir / f"{base_name}_9x16.mp4"
    ass_path = out_dir / f"clip_{clip_plan.clip_number:02d}.ass"

    console.print(
        f"  [dim]ClipPlan {clip_plan.clip_number:02d}[/dim] "
        f"[bold]{clip_plan.title[:40]}[/bold] "
        f"[{clip_plan.total_duration:.1f}s, {len(clip_plan.beats)} beats, {variant}] "
        f"score=[{'green' if clip_plan.virality_score >= 70 else 'yellow'}]{clip_plan.virality_score}[/]"
    )

    crop_w = min(int(crop_w), src_w)
    crop_w = crop_w - (crop_w % 2)

    try:
        # 1. Non-linear Subtitle Generation via remap_words()
        words_to_map = all_words or getattr(clip_plan, "_source_words", [])
        if words_to_map:
            remapped_words = remap_words(words_to_map, clip_plan.cuts)
            generate_ass(remapped_words, ass_path, style=subtitle_style)
        else:
            ass_path = None

        # 2. Build non-linear filtergraph
        filter_complex, vout, aout = build_clip_plan_filtergraph(
            clip_plan=clip_plan,
            crop_path=crop_path,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            crop_w=crop_w,
            ass_path=ass_path,
        )

        # 3. Execute FFmpeg
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        encoder = os.getenv("CLIPEDICS_VIDEO_ENCODER", "libx264")
        cmd = [
            ffmpeg, "-y",
            "-i", str(source_video),
            "-filter_complex", filter_complex,
            "-map", vout,
            "-map", aout,
            "-c:v", encoder,
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-loglevel", "error",
            str(out_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        # Software fallback to libx264 if hardware encoder fails
        if result.returncode != 0 and encoder != "libx264":
            console.print(f"    [yellow][!] Encoder {encoder} failed, retrying with libx264 software encoder...[/yellow]")
            cmd_fallback = list(cmd)
            v_idx = cmd_fallback.index("-c:v")
            cmd_fallback[v_idx + 1] = "libx264"
            result = subprocess.run(cmd_fallback, capture_output=True, text=True)

        if result.returncode != 0:
            console.print(f"    [red]✗ FFmpeg error:[/red] {result.stderr[:300]}")
            return ProcessedClip(
                candidate=clip_plan,
                raw_mp4_path="",
                output_mp4_path="",
                success=False,
                error=result.stderr[:200],
            )

        console.print(f"    [green]✓[/green] → {out_path.name}")
        return ProcessedClip(
            candidate=clip_plan,
            raw_mp4_path=str(out_path),
            output_mp4_path=str(out_path),
            success=True,
        )

    except Exception as e:
        console.print(f"    [red]✗ Error:[/red] {e}")
        return ProcessedClip(
            candidate=clip_plan,
            raw_mp4_path="",
            output_mp4_path="",
            success=False,
            error=str(e),
        )


def _render_single(
    source_video: Path,
    candidate: Union[ClipCandidate, ClipPlan],
    crop_path: list[int],
    src_w: int,
    src_h: int,
    fps: float,
    crop_w: int,
    out_dir: Path,
    subtitle_style: str,
) -> ProcessedClip:
    """Render a single clip — dispatches to render_clip_plan if ClipPlan."""
    if isinstance(candidate, ClipPlan) or hasattr(candidate, "beats"):
        return render_clip_plan(
            source_video=source_video,
            clip_plan=candidate,
            crop_path=crop_path,
            src_w=src_w,
            src_h=src_h,
            fps=fps,
            crop_w=crop_w,
            out_dir=out_dir,
            subtitle_style=subtitle_style,
        )

    safe_title = _sanitize(candidate.title)
    score = f"{candidate.virality_score:03d}"
    base_name = f"{score}_clip{candidate.clip_number:02d}_{safe_title}"
    out_path = out_dir / f"{base_name}_9x16.mp4"
    ass_path = out_dir / f"clip_{candidate.clip_number:02d}.ass"

    console.print(
        f"  [dim]Clip {candidate.clip_number:02d}[/dim] "
        f"[bold]{candidate.title[:45]}[/bold] "
        f"[{candidate.start_seconds:.1f}s→{candidate.end_seconds:.1f}s] "
        f"score=[{'green' if candidate.virality_score >= 70 else 'yellow'}]{candidate.virality_score}[/]"
    )

    try:
        # 1. Generate ASS subtitle for this clip's words
        clipped_segs = _extract_clip_segments(candidate)
        if clipped_segs:
            generate_ass(clipped_segs, ass_path, style=subtitle_style)
        else:
            ass_path = None

        # 2. Determine Layout and Filtergraph
        start_frame = int(candidate.start_seconds * fps)
        end_frame = int(candidate.end_seconds * fps)
        clip_frames = crop_path[start_frame:end_frame]
        avg_crop_x = int(sum(clip_frames) / max(len(clip_frames), 1)) if clip_frames else (src_w - crop_w) // 2

        layout_mode = getattr(candidate, "layout_mode", "center_crop") or "center_crop"
        duration = candidate.end_seconds - candidate.start_seconds

        ass_str = None
        if ass_path and ass_path.exists():
            ass_str = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

        # 3. Build FFmpeg command based on layout mode
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [
            ffmpeg, "-y",
            "-ss", str(candidate.start_seconds),
            "-i", str(source_video),
            "-t", str(duration),
        ]

        if layout_mode == "blur_background":
            filter_chain = (
                "[0:v]split=2[fg][bg];"
                "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5,eq=brightness=-0.15[bg_blur];"
                "[fg]scale=1080:-1[fg_scaled];"
                "[bg_blur][fg_scaled]overlay=(W-w)/2:(H-h)/2"
            )
            if ass_str:
                filter_chain += f"[v_pre];[v_pre]subtitles='{ass_str}':fontsdir='.'[vout]"
            else:
                filter_chain += "[vout]"
            cmd.extend(["-filter_complex", filter_chain, "-map", "[vout]", "-map", "0:a?"])

        elif layout_mode == "split_screen":
            x1 = getattr(candidate, "split_x1", max(0, avg_crop_x - crop_w // 2))
            x2 = getattr(candidate, "split_x2", min(src_w - crop_w, avg_crop_x + crop_w // 2))
            filter_chain = (
                f"[0:v]split=2[s1][s2];"
                f"[s1]crop={crop_w}:{src_h}:{x1}:0,scale=1080:960[top];"
                f"[s2]crop={crop_w}:{src_h}:{x2}:0,scale=1080:960[bottom];"
                f"[top][bottom]vstack"
            )
            if ass_str:
                filter_chain += f"[v_pre];[v_pre]subtitles='{ass_str}':fontsdir='.'[vout]"
            else:
                filter_chain += "[vout]"
            cmd.extend(["-filter_complex", filter_chain, "-map", "[vout]", "-map", "0:a?"])

        else:
            # Standard center crop on active speaker with One-Euro smoothing
            vf = f"crop={crop_w}:{src_h}:{avg_crop_x}:0,scale=1080:1920:flags=lanczos"
            if ass_str:
                vf += f",subtitles='{ass_str}':fontsdir='.'"
            cmd.extend(["-vf", vf])

        encoder = os.getenv("CLIPEDICS_VIDEO_ENCODER", "libx264")
        cmd.extend([
            "-c:v", encoder,
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-loglevel", "error",
            str(out_path),
        ])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and encoder != "libx264":
            console.print(f"    [yellow][!] Encoder {encoder} failed, retrying with libx264 software encoder...[/yellow]")
            cmd_fallback = list(cmd)
            v_idx = cmd_fallback.index("-c:v")
            cmd_fallback[v_idx + 1] = "libx264"
            result = subprocess.run(cmd_fallback, capture_output=True, text=True)

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


def render_clips(
    source_video: Path,
    candidates: list[Union[ClipCandidate, ClipPlan]],
    crop_path: list[int],
    src_w: int,
    src_h: int,
    fps: float,
    job_id: str,
    subtitle_style: str = "hormozi",
    config: Optional[PipelineConfig] = None,
) -> list[ProcessedClip]:
    """
    For each clip candidate or clip plan, render a final 9:16 MP4 with:
      1. Non-linear multi-trim concat or face-tracked smooth crop
      2. 30ms anti-click audio crossfading
      3. Kinetic word-by-word ASS subtitles burned in

    Returns list of ProcessedClip with output paths.
    """
    cfg = config or PipelineConfig.from_env()
    effective_style = subtitle_style or cfg.subtitle_style or "hormozi"
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Calculate crop width for 9:16 (clamped & even)
    crop_w = min(int(src_h * 9 / 16), src_w)
    crop_w = crop_w - (crop_w % 2)

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
            subtitle_style=effective_style,
        )
        results.append(result)

    # Summary
    success = sum(1 for r in results if r.success)
    console.print(
        f"\n[green]✓ Rendered {success}/{len(results)} clips[/green] → {out_dir}"
    )
    return results


def _extract_clip_segments(candidate: ClipCandidate):
    """Extract transcript segments attached to candidate."""
    return getattr(candidate, "_clip_segments", [])


def _sanitize(name: str, max_len: int = 40) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:max_len]
