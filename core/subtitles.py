"""
Clipedics – Kinetic ASS Subtitle Generator (Phase 4: Caption Rewrite)
Generates high-engagement, platform-safe 9:16 kinetic subtitles for TikTok, Instagram Reels, and YouTube Shorts.

Phase 4 Features:
1. 2–4 Word Micro-Chunking: tightly paced phrases with a strict maximum of 2 lines.
2. Zero-Gap Hold Protocol: captions stay on screen until the exact start of the next spoken word, eliminating blinking.
3. Platform Safe Zones: placed at vertical margin 420px to avoid obstruction by TikTok/Reels/Shorts UI overlays.
4. Non-Linear remap(): maps non-linear EDL cuts to contiguous presentation timestamps.
5. High-Impact Styling: scale-pop active word animation with universal font fallbacks.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from core.models import TranscriptSegment, WordSegment

# ── Platform Safe Zone Presets (1080×1920) ────────────────────────────────────
# Baseline at Y = 1500 (MarginV = 420px from bottom)
# Clears bottom description, sound title, like/share rails, and top notch.
DEFAULT_SAFE_MARGIN_V = 420
DEFAULT_MARGIN_L = 80
DEFAULT_MARGIN_R = 120

STYLE_PRESETS = {
    "hormozi": {
        "fontname": "Impact",
        "fontsize": 82,
        "primary": "&H00FFFFFF&",       # Crisp White
        "highlight": "&H0000FFFF&",     # Vibrant Electric Yellow/Cyan
        "outline": "&H00000000&",       # Solid Black outline
        "back": "&H80000000&",          # 50% Black drop shadow
        "bold": 1,
        "outline_size": 5,
        "shadow_size": 2,
        "alignment": 2,                 # Bottom-center (within safe zone)
        "margin_v": DEFAULT_SAFE_MARGIN_V,
        "margin_l": DEFAULT_MARGIN_L,
        "margin_r": DEFAULT_MARGIN_R,
    },
    "minimal": {
        "fontname": "Montserrat",
        "fontsize": 72,
        "primary": "&H00FFFFFF&",
        "highlight": "&H00FFE500&",     # Golden Yellow
        "outline": "&H00000000&",
        "back": "&H60000000&",
        "bold": 1,
        "outline_size": 3,
        "shadow_size": 1,
        "alignment": 2,
        "margin_v": DEFAULT_SAFE_MARGIN_V,
        "margin_l": DEFAULT_MARGIN_L,
        "margin_r": DEFAULT_MARGIN_R,
    },
    "neon": {
        "fontname": "Arial Black",
        "fontsize": 78,
        "primary": "&H00FFFFFF&",
        "highlight": "&H0000FF00&",     # High-contrast Neon Green
        "outline": "&H00000000&",
        "back": "&HA0000000&",
        "bold": 1,
        "outline_size": 5,
        "shadow_size": 3,
        "alignment": 2,
        "margin_v": DEFAULT_SAFE_MARGIN_V,
        "margin_l": DEFAULT_MARGIN_L,
        "margin_r": DEFAULT_MARGIN_R,
    },
}


# ── Chunk Data Model ──────────────────────────────────────────────────────────

@dataclass
class CaptionChunk:
    """A tightly bounded 2-4 word subtitle chunk with max 2 lines."""
    words: list[WordSegment]
    line1_words: list[WordSegment]
    line2_words: list[WordSegment]

    @property
    def start_time(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end_time(self) -> float:
        return self.words[-1].end if self.words else 0.0

    @property
    def word_count(self) -> int:
        return len(self.words)

    @property
    def line_count(self) -> int:
        return 2 if self.line2_words else 1

    def full_text(self) -> str:
        return " ".join(w.word.strip() for w in self.words)


# ── 2–4 Word Micro-Chunking with Max 2 Lines ──────────────────────────────────

def chunk_words(
    words: list[WordSegment],
    min_words: int = 2,
    max_words: int = 4,
    max_pause_sec: float = 0.50,
) -> list[CaptionChunk]:
    """
    Partition words into balanced 2–4 word micro-chunks with a maximum of 2 lines.
    Enforces natural breaks on sentence-ending punctuation or audible pauses.
    """
    valid_words = [w for w in words if w.start is not None and w.end is not None]
    if not valid_words:
        return []

    # First pass: split on sentence ends or long pauses
    segments: list[list[WordSegment]] = []
    curr: list[WordSegment] = []

    for i, w in enumerate(valid_words):
        curr.append(w)
        text_clean = w.word.strip()
        has_punct = any(text_clean.endswith(p) for p in (".", "!", "?"))
        gap = (valid_words[i + 1].start - w.end) if i < len(valid_words) - 1 else 0.0

        if has_punct or gap >= max_pause_sec:
            segments.append(curr)
            curr = []
    if curr:
        segments.append(curr)

    # Second pass: balanced chunking within each segment
    chunks: list[CaptionChunk] = []
    for seg in segments:
        n = len(seg)
        if n == 0:
            continue
        if n <= max_words:
            l1, l2 = _split_into_two_lines(seg)
            chunks.append(CaptionChunk(words=seg, line1_words=l1, line2_words=l2))
            continue

        idx = 0
        while idx < n:
            rem = n - idx
            if rem <= max_words:
                take = rem
            elif rem == 5:
                take = 3
            elif rem == 6:
                take = 3
            elif rem == 7:
                take = 4
            elif rem == 8:
                take = 4
            else:
                take = 3

            sub = seg[idx : idx + take]
            l1, l2 = _split_into_two_lines(sub)
            chunks.append(CaptionChunk(words=sub, line1_words=l1, line2_words=l2))
            idx += take

    return chunks


def _split_into_two_lines(
    words: list[WordSegment],
) -> tuple[list[WordSegment], list[WordSegment]]:
    """Split 2-4 words into at most two lines."""
    n = len(words)
    if n <= 2:
        return (words, [])
    elif n == 3:
        # 2 words top, 1 word bottom
        return (words[:2], words[2:])
    else:
        # 4 words: 2 top, 2 bottom
        mid = n // 2
        return (words[:mid], words[mid:])


# ── Non-Linear remap() Engine ──────────────────────────────────────────────────

def remap_words(
    words: list[WordSegment],
    cuts: list[tuple[float, float]],
) -> list[WordSegment]:
    """
    Remap words from non-linear source intervals [(src_start, src_end), ...]
    to a continuous presentation timeline starting at 0.0.
    Enables accurate word-sync captions for non-linear edits, cold opens, and trailer cuts.
    """
    remapped: list[WordSegment] = []
    current_out_time = 0.0

    for src_start, src_end in cuts:
        cut_duration = src_end - src_start
        # Select all words belonging to this cut interval
        interval_words = [
            w for w in words
            if w.start is not None and w.end is not None
            and w.start >= (src_start - 0.05)
            and w.end <= (src_end + 0.05)
        ]
        for w in interval_words:
            rel_start = max(0.0, w.start - src_start)
            rel_end = min(cut_duration, w.end - src_start)
            remapped.append(WordSegment(
                word=w.word,
                start=round(current_out_time + rel_start, 3),
                end=round(current_out_time + rel_end, 3),
                score=w.score,
            ))
        current_out_time += cut_duration

    return remapped


# ── Zero-Gap Hold Protocol & ASS Generator ─────────────────────────────────────

def generate_ass(
    segments: list[TranscriptSegment] | list[WordSegment],
    output_path: Path,
    style: str = "hormozi",
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    safe_zone_margin_v: int = DEFAULT_SAFE_MARGIN_V,
) -> Path:
    """
    Generate Advanced SubStation Alpha (.ass) subtitle file with:
    - 2–4 word micro-chunking
    - Max 2 lines
    - Zero-gap hold (no blank flicker between words)
    - Platform safe zone placement
    - Kinetic scale-pop karaoke active word animation
    """
    preset = dict(STYLE_PRESETS.get(style, STYLE_PRESETS["hormozi"]))
    preset["margin_v"] = safe_zone_margin_v

    # Flatten words from segments
    all_words: list[WordSegment] = []
    if segments and isinstance(segments[0], TranscriptSegment):
        for seg in segments:
            for w in seg.words:
                if w.start is not None and w.end is not None:
                    all_words.append(w)
    elif segments and isinstance(segments[0], WordSegment):
        all_words = [w for w in segments if w.start is not None and w.end is not None]

    if not all_words:
        # Fallback empty or minimal ASS
        return _write_empty_ass(output_path, preset, play_res_x, play_res_y)

    chunks = chunk_words(all_words, min_words=2, max_words=4)
    lines = [_make_header(preset, play_res_x, play_res_y)]

    # Generate dialogue events for each chunk with Zero-Gap Hold
    for c_idx, chunk in enumerate(chunks):
        next_chunk_start = chunks[c_idx + 1].start_time if c_idx < len(chunks) - 1 else None

        for w_idx, active_word in enumerate(chunk.words):
            event_start = active_word.start

            # ── Zero-Gap Hold Calculation ──────────────────────────────────────
            # Word display holds until next word start, or next chunk start if last word
            if w_idx < len(chunk.words) - 1:
                event_end = chunk.words[w_idx + 1].start
            else:
                if next_chunk_start is not None and (next_chunk_start - active_word.end) <= 1.5:
                    event_end = next_chunk_start
                else:
                    event_end = active_word.end + 0.35

            if event_end <= event_start:
                event_end = event_start + 0.10

            start_str = _fmt_ass_time(event_start)
            end_str = _fmt_ass_time(event_end)

            # Build formatted lines with active word highlighted
            formatted_dialogue = _format_chunk_text(chunk, w_idx, preset)
            lines.append(
                f"Dialogue: 0,{start_str},{end_str},ViralStyle,,0,0,0,,{formatted_dialogue}"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return output_path


def _format_chunk_text(chunk: CaptionChunk, active_idx: int, preset: dict) -> str:
    """Format chunk text with active word pop animation and max 2 lines with \\N."""
    rendered_words: list[str] = []

    for j, w in enumerate(chunk.words):
        w_escaped = _escape_ass(w.word.strip().upper())
        if j == active_idx:
            # Active word: pop scale + bright highlight color
            rendered_words.append(
                f"{{\\c{preset['highlight']}\\fscx112\\fscy112}}{w_escaped}"
                f"{{\\c{preset['primary']}\\fscx100\\fscy100}}"
            )
        else:
            # Context words: slightly muted transparency
            rendered_words.append(
                f"{{\\alpha&H35&}}{w_escaped}{{\\alpha&H00&}}"
            )

    if chunk.line2_words:
        split_idx = len(chunk.line1_words)
        line1 = " ".join(rendered_words[:split_idx])
        line2 = " ".join(rendered_words[split_idx:])
        return f"{{\\an2}}{line1}\\N{line2}"
    else:
        line1 = " ".join(rendered_words)
        return f"{{\\an2}}{line1}"


def _make_header(preset: dict, play_res_x: int, play_res_y: int) -> str:
    """Build the ASS file header with safe-zone style definitions."""
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,{preset['fontname']},{preset['fontsize']},{preset['primary']},&H000000FF&,{preset['outline']},{preset['back']},{preset['bold']},0,0,0,100,100,0,0,1,{preset['outline_size']},{preset['shadow_size']},{preset['alignment']},{preset['margin_l']},{preset['margin_r']},{preset['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds to ASS time format: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    """Escape special ASS characters."""
    return text.replace("{", "\\{").replace("}", "\\}")


def _write_empty_ass(path: Path, preset: dict, rx: int, ry: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = _make_header(preset, rx, ry)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
    return path
