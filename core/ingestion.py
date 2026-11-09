"""
Clipedics – Video Ingestion
Handles downloading from YouTube/URLs via yt-dlp and local file validation.
"""
from __future__ import annotations
import re
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from config.settings import TEMP_DIR

console = Console()


def is_url(source: str) -> bool:
    """Return True if the source looks like a URL."""
    return source.startswith(("http://", "https://", "www."))


def download_video(url: str, job_id: str) -> Path:
    """
    Download a video from any URL supported by yt-dlp (YouTube, Vimeo, etc.)
    Returns the path to the downloaded video file.
    """
    out_dir = TEMP_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "video.%(ext)s")

    # Reuse existing downloaded video if present
    existing = [f for f in out_dir.glob("video.*") if not f.name.endswith((".part", ".ytdl")) and f.stat().st_size > 0]
    if existing:
        console.print(f"[green]✓ Found existing downloaded video:[/green] {existing[0].name} ({_file_size(existing[0])})")
        return existing[0]

    console.print(f"[cyan]⬇ Downloading video from:[/cyan] {url}")

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=android,web;player_skip=webpage,configs",
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/18/best",
        "--merge-output-format", "mp4",
        "--output", out_template,
        "--no-playlist",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        if "unavailable" in err.lower():
            raise ValueError("This video is unavailable on YouTube (it may be private, deleted, or region-restricted).")
        raise RuntimeError(f"Video download failed: {err}")

    # Find the downloaded file (excluding in-progress .part files)
    mp4_files = [f for f in out_dir.glob("video.*") if not f.name.endswith((".part", ".ytdl"))]
    if not mp4_files:
        raise FileNotFoundError(f"No video file found after download in {out_dir}")

    video_path = mp4_files[0]
    console.print(f"[green]✓ Downloaded:[/green] {video_path.name} ({_file_size(video_path)})")
    return video_path


def prepare_video(source: str, job_id: str) -> tuple[Path, str]:
    """
    Given a source (URL or local file path), returns:
    - Path to the video file
    - Human-readable title/name
    """
    if is_url(source):
        # Get video title first
        title = _get_video_title(source)
        video_path = download_video(source, job_id)
        return video_path, title
    else:
        # Local file
        video_path = Path(source)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {source}")
        if not video_path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}:
            raise ValueError(f"Unsupported video format: {video_path.suffix}")

        # Copy to temp so we don't modify the original
        dest_dir = TEMP_DIR / job_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / video_path.name
        shutil.copy2(video_path, dest_path)

        console.print(f"[green]✓ Using local file:[/green] {video_path.name} ({_file_size(video_path)})")
        return dest_path, video_path.stem


def extract_audio(video_path: Path, job_id: str) -> Path:
    """
    Extract audio track from video as a 16kHz mono WAV file.
    (16kHz mono is optimal for Whisper models.)
    """
    out_dir = TEMP_DIR / job_id
    audio_path = out_dir / "audio.wav"

    if audio_path.exists() and audio_path.stat().st_size > 0:
        console.print(f"[green]✓ Found existing extracted audio:[/green] {audio_path.name} ({_file_size(audio_path)})")
        return audio_path

    console.print("[cyan]🎵 Extracting audio track...[/cyan]")

    cmd = [
        "ffmpeg",
        "-y",                        # overwrite
        "-i", str(video_path),
        "-vn",                        # no video
        "-acodec", "pcm_s16le",      # 16-bit PCM
        "-ar", "16000",              # 16kHz sample rate (Whisper optimum)
        "-ac", "1",                  # mono
        "-loglevel", "error",
        str(audio_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed:\n{result.stderr}")

    console.print(f"[green]✓ Audio extracted:[/green] {audio_path.name} ({_file_size(audio_path)})")
    return audio_path


def get_video_duration(video_path: Path) -> float:
    """Return video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_video_title(url: str) -> str:
    """Use yt-dlp to fetch the video title without downloading."""
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=android,web;player_skip=webpage,configs",
        "--get-title", "--no-playlist", url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        if "unavailable" in err.lower():
            raise ValueError("This video is unavailable on YouTube (it may be private, deleted, or region-restricted).")
        return "YouTube Video"
    title = result.stdout.strip()
    # Sanitize for use as filename
    title = re.sub(r'[<>:"/\\|?*]', "", title)
    return title or "Untitled Video"


def _file_size(path: Path) -> str:
    """Return human-readable file size."""
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

