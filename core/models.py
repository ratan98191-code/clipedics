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


# ── Semantic Units & Features (Phase 1) ──────────────────────────────────────

class Unit(BaseModel):
    """
    Atomic narrative building block.
    Split on word gap >= 0.35s or sentence punctuation, snapped to RMS audio valleys.
    """
    unit_id: int                          # Sequential 1-based integer for LLM indexing
    start_seconds: float                  # Final snapped start timestamp
    end_seconds: float                    # Final snapped end timestamp
    raw_start_seconds: float = 0.0        # Word boundary start before RMS snap
    raw_end_seconds: float = 0.0          # Word boundary end before RMS snap
    text: str                             # Plain text content of unit
    words: list[WordSegment] = []         # Individual aligned words
    speaker: Optional[str] = "SPEAKER_00" # Speaker turn label

    # Extracted multi-modal features
    loudness_lufs: float = -24.0          # Integrated loudness (ebur128 / RMS dBFS)
    speech_rate_wpm: float = 0.0          # Words per minute
    pause_before_sec: float = 0.0         # Silence gap before unit
    pause_after_sec: float = 0.0          # Silence gap after unit
    shot_ids: list[int] = []              # Overlapping PySceneDetect shot IDs
    face_detected: bool = False           # Visual face presence
    dominant_face_x: Optional[float] = None # Face center x normalized [0.0, 1.0]

    # Phase 6 Narrative Arc & Storytelling Features
    role_hint: str = "build"              # "hook" | "build" | "peak" | "cliffhanger" | "resolution"
    opens_loop: Optional[str] = None      # Curiosity loop opened by this unit
    answers_loop_of: Optional[str] = None # Loop topic resolved/answered by this unit
    narrative_energy: float = 50.0        # 0.0 - 100.0 dynamic tension / energy level

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


# ── Vision & Reframing (Phase 3) ──────────────────────────────────────────────

class FaceBoundingBox(BaseModel):
    """Normalized 2D face bounding box (0.0 to 1.0) with confidence."""
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    confidence: float = 1.0

    @property
    def width(self) -> float:
        return max(0.0, self.xmax - self.xmin)

    @property
    def height(self) -> float:
        return max(0.0, self.ymax - self.ymin)

    @property
    def center_x(self) -> float:
        return (self.xmin + self.xmax) / 2.0

    @property
    def center_y(self) -> float:
        return (self.ymin + self.ymax) / 2.0

    @property
    def area(self) -> float:
        return self.width * self.height


class ShotReframePlan(BaseModel):
    """Shot-level reframe layout and crop coordinates."""
    shot_id: int
    start_seconds: float
    end_seconds: float
    layout_mode: str = "center_crop"  # "center_crop" | "split_screen" | "blur_background"
    crop_x: int = 0
    secondary_crop_x: Optional[int] = None  # for split-screen second speaker
    speaker_track_ids: list[int] = []


# ── Clips ─────────────────────────────────────────────────────────────────────

class ClipCandidate(BaseModel):
    """A clip candidate returned by the LLM clipping engine."""
    model_config = ConfigDict(extra="allow")  # allows dynamic attrs like _clip_segments
    clip_number: int = 1
    start_seconds: float
    end_seconds: float
    title: str = ""
    virality_score: int = 70          # 1–100
    virality_rationale: str = ""
    hook_sentence: str = ""           # The first sentence / opening hook
    suggested_caption: str = ""       # Ready-to-post social media caption
    hashtags: list[str] = []
    layout_mode: str = "center_crop"  # "center_crop" | "split_screen" | "blur_background"
    reframe_plans: list[ShotReframePlan] = []

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


class Beat(BaseModel):
    """
    Atomic narrative segment in a non-linear edit decision list (EDL).
    """
    beat_id: int                                # Sequential index (1, 2, 3...)
    role: str = "body"                          # "cold_open" | "hook" | "build" | "peak" | "cliffhanger" | "body"
    unit_ids: list[int] = []                    # Source unit IDs composing this beat
    src_start: float                            # Source video start timestamp (seconds)
    src_end: float                              # Source video end timestamp (seconds)
    target_start: float = 0.0                   # Output timeline start timestamp (seconds)
    target_end: float = 0.0                     # Output timeline end timestamp (seconds)
    text: str = ""                              # Text content of the beat
    layout_mode: str = "center_crop"            # "center_crop" | "split_screen" | "blur_background"
    crop_x: Optional[int] = None                # Left crop pixel coordinate for the beat

    @property
    def duration(self) -> float:
        return max(0.0, self.src_end - self.src_start)


class ClipPlan(BaseModel):
    """
    Non-linear Edit Decision List (EDL) plan for a clip.
    Represents reordered or multi-segment compositions (e.g. Cold Open).
    """
    model_config = ConfigDict(extra="allow")
    plan_id: str = ""
    clip_number: int = 1
    title: str = ""
    format_variant: str = "cold_open"           # "cold_open" | "contiguous" | "trailer"
    beats: list[Beat] = []
    virality_score: int = 70
    virality_rationale: str = ""
    hook_sentence: str = ""
    suggested_caption: str = ""
    hashtags: list[str] = []
    layout_mode: str = "center_crop"

    @property
    def cuts(self) -> list[tuple[float, float]]:
        """Ordered list of (src_start, src_end) tuples."""
        return [(b.src_start, b.src_end) for b in self.beats]

    @property
    def total_duration(self) -> float:
        """Total duration of all beats on the presentation timeline."""
        return sum(b.duration for b in self.beats)

    @property
    def duration_seconds(self) -> float:
        return self.total_duration

    @property
    def start_seconds(self) -> float:
        """Earliest source timestamp referenced in the plan."""
        return min((b.src_start for b in self.beats), default=0.0)

    @property
    def end_seconds(self) -> float:
        """Latest source timestamp referenced in the plan."""
        return max((b.src_end for b in self.beats), default=0.0)

    def to_candidate(self) -> ClipCandidate:
        """Downcast to ClipCandidate for backward compatibility."""
        return ClipCandidate(
            clip_number=self.clip_number,
            start_seconds=self.start_seconds,
            end_seconds=self.end_seconds,
            title=self.title,
            virality_score=self.virality_score,
            virality_rationale=self.virality_rationale,
            hook_sentence=self.hook_sentence,
            suggested_caption=self.suggested_caption,
            hashtags=self.hashtags,
            layout_mode=self.layout_mode,
        )


class ProcessedClip(BaseModel):
    """A clip after rendering — contains file path metadata."""
    candidate: ClipCandidate | ClipPlan
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
    clip_plans: list[ClipPlan] = []
    processed_clips: list[ProcessedClip] = []


# ── Pipeline Configuration ───────────────────────────────────────────────────

class PipelineConfig(BaseModel):
    """
    Explicit, strongly-typed pipeline configuration passed through execution steps.
    Eliminates module-level settings mutation.
    """
    num_clips: int = 5
    min_seconds: int = 30
    max_seconds: int = 90
    subtitle_style: str = "hormozi"
    reframe: bool = True
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    llm_provider: str = "groq"
    groq_model: str = "qwen/qwen3.8-27b"

    @classmethod
    def from_env(cls, **overrides) -> "PipelineConfig":
        """Instantiate config loaded from environment variables with optional overrides."""
        import os
        device = overrides.get("whisper_device", os.getenv("WHISPER_DEVICE", "cpu"))
        comp_type = overrides.get(
            "whisper_compute_type",
            "float16" if device == "cuda" else "int8"
        )
        data = {
            "num_clips": int(overrides.get("num_clips") or os.getenv("TARGET_CLIPS", 5)),
            "min_seconds": int(overrides.get("min_seconds") or os.getenv("CLIP_MIN_SECONDS", 30)),
            "max_seconds": int(overrides.get("max_seconds") or os.getenv("CLIP_MAX_SECONDS", 90)),
            "subtitle_style": str(overrides.get("subtitle_style") or os.getenv("SUBTITLE_STYLE", "hormozi")),
            "reframe": overrides.get("reframe") if overrides.get("reframe") is not None else True,
            "whisper_model": str(overrides.get("whisper_model") or os.getenv("WHISPER_MODEL", "base")),
            "whisper_device": device,
            "whisper_compute_type": comp_type,
            "llm_provider": str(overrides.get("llm_provider") or os.getenv("LLM_PROVIDER", "groq")).lower(),
            "groq_model": str(overrides.get("groq_model") or os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")),
        }
        return cls(**data)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS for human-readable transcript."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

