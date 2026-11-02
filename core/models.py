"""
Clipedics – Pydantic Data Models
Shared schemas across the entire pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from pydantic import BaseModel, ConfigDict


# ── Transcription ──────────────────────────────────────────────────────────────

class WordSegment(BaseModel):
    """A single word with its precise timestamps from WhisperX alignment."""
    word: str
    start: float   # seconds
    end: float     # seconds
    score: float = 1.0  # confidence


class TranscriptSegment(BaseModel):
    """A sentence/phrase segment containing aligned words."""
    text: str
    start: float
    end: float
    speaker: Optional[str] = None  # e.g. "SPEAKER_00" (future: diarization)
    words: list[WordSegment] = []


class Transcript(BaseModel):
    """Full transcript of a video."""
    language: str
    duration_seconds: float
    segments: list[TranscriptSegment]

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)

    def to_timestamped_text(self) -> str:
        """Returns a formatted string with timestamps for LLM context."""
        lines = []
        for seg in self.segments:
            start = _fmt_time(seg.start)
            end = _fmt_time(seg.end)
            lines.append(f"[{start} → {end}] {seg.text.strip()}")
        return "\n".join(lines)


# ── Clips ─────────────────────────────────────────────────────────────────────

class ClipCandidate(BaseModel):
    """A clip candidate returned by the LLM clipping engine."""
    model_config = ConfigDict(extra="allow")  # allows dynamic attrs like _clip_segments
    clip_number: int
    start_seconds: float
    end_seconds: float
    title: str
    virality_score: int          # 1–100
    virality_rationale: str
    hook_sentence: str           # The first sentence / opening hook
    suggested_caption: str       # Ready-to-post social media caption
    hashtags: list[str] = []

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


class ProcessedClip(BaseModel):
    """A clip after rendering — contains file path metadata."""
    candidate: ClipCandidate
    raw_mp4_path: str            # Raw cut, no subtitles
    output_mp4_path: str = ""   # Final output (Phase 2+: with subtitles)
    thumbnail_path: str = ""
    success: bool = True
    error: str = ""


# ── Job ───────────────────────────────────────────────────────────────────────

class ProcessingJob(BaseModel):
    """Tracks the state of an end-to-end processing run."""
    input_source: str           # URL or file path
    video_title: str = ""
    video_path: str = ""
    audio_path: str = ""
    transcript: Optional[Transcript] = None
    clip_candidates: list[ClipCandidate] = []
    processed_clips: list[ProcessedClip] = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS for human-readable transcript."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

