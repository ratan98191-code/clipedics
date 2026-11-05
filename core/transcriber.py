"""
Clipedics – Transcription Engine (Faster-Whisper / WhisperX)
Transcribes audio with word-level timestamps using Faster-Whisper.
"""
from __future__ import annotations
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config.settings import (
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
)
from core.models import Transcript, TranscriptSegment, WordSegment, PipelineConfig

# ── Patch PyAV 14+ incompatibility with faster-whisper ────────────────────────
try:
    import av
    if not hasattr(av, "_patched_clipedics"):
        _orig_av_open = av.open
        def _safe_av_open(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return _orig_av_open(*args, **kwargs)
        av.open = _safe_av_open
        av._patched_clipedics = True
except Exception:
    pass

console = Console()


def transcribe(audio_path: Path, config: Optional[PipelineConfig] = None) -> Transcript:
    """
    Transcribe an audio file using faster-whisper with word-level timestamps.

    Returns a Transcript object with timestamped segments and words.
    """
    cfg = config or PipelineConfig.from_env()
    model_name = cfg.whisper_model or WHISPER_MODEL
    device = cfg.whisper_device or WHISPER_DEVICE
    compute_type = cfg.whisper_compute_type or WHISPER_COMPUTE_TYPE

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError(
            "faster-whisper is not installed.\n"
            "Run: .venv\\Scripts\\pip.exe install faster-whisper"
        )

    console.print(
        f"[cyan]🎤 Transcribing with Faster-Whisper[/cyan] "
        f"(model={model_name}, device={device})"
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:

        task = progress.add_task("Loading Whisper model...", total=None)
        
        # Load the model
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )
        progress.update(task, description="Model loaded ✓")

        # Transcribe with word timestamps enabled
        progress.update(task, description="Transcribing speech with word-level alignment...")
        segments_generator, info = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            vad_filter=True, # Voice activity detection to ignore silence
        )
        
        language = info.language
        progress.update(task, description=f"Transcription done ✓ (lang={language})")

        # Collect segments
        segments = []
        for seg in segments_generator:
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(
                        WordSegment(
                            word=w.word.strip(),
                            start=float(w.start),
                            end=float(w.end),
                            score=float(getattr(w, "probability", 1.0)),
                        )
                    )

            segments.append(
                TranscriptSegment(
                    text=seg.text.strip(),
                    start=float(seg.start),
                    end=float(seg.end),
                    words=words,
                )
            )

    duration = info.duration if info.duration else (segments[-1].end if segments else 0.0)

    transcript = Transcript(
        language=language,
        duration_seconds=float(duration),
        segments=segments,
    )

    console.print(
        f"[green]✓ Transcribed:[/green] "
        f"{len(segments)} segments, "
        f"{sum(len(s.words) for s in segments)} words, "
        f"duration={_fmt_duration(duration)}"
    )

    return transcript


def _fmt_duration(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
