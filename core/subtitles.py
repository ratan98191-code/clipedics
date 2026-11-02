"""
Clipedics – ASS Subtitle Generator
Generates Advanced SubStation Alpha (.ass) subtitle files with
kinetic word-by-word karaoke-style animations (as seen on TikTok/Reels).

Reverse-engineered from Vizard.ai's subtitle format:
  - Each word gets its own Dialogue line with precise start/end times
  - Active word gets scale-pop animation {\fscx120\fscy120}
  - Word-level primary colour changes to highlight colour
  - All other words in the same "phrase group" shown simultaneously
    but in a muted style
"""
from __future__ import annotations
from pathlib import Path

from core.models import TranscriptSegment

# ── Style Presets ─────────────────────────────────────────────────────────────
STYLE_PRESETS = {
    "hormozi": {
        "fontname": "Impact",
        "fontsize": 85,
        "primary": "&H00FFFFFF&",       # White
        "highlight": "&H0000FFFF&",     # Cyan (active word)
        "outline": "&H00000000&",       # Black outline
        "back": "&H80000000&",          # 50% black shadow
        "bold": 1,
        "outline_size": 5,
        "shadow_size": 2,
        "alignment": 2,                 # Bottom-center
        "margin_v": 120,
    },
    "minimal": {
        "fontname": "Montserrat",
        "fontsize": 72,
        "primary": "&H00FFFFFF&",
        "highlight": "&H00FFE500&",     # Yellow
        "outline": "&H00000000&",
        "back": "&H60000000&",
        "bold": 1,
        "outline_size": 3,
        "shadow_size": 1,
        "alignment": 2,
        "margin_v": 100,
    },
    "neon": {
        "fontname": "Arial Black",
        "fontsize": 78,
        "primary": "&H00FFFFFF&",
        "highlight": "&H0000FF00&",     # Neon green
        "outline": "&H00000000&",
        "back": "&HA0000000&",
        "bold": 1,
        "outline_size": 4,
        "shadow_size": 3,
        "alignment": 2,
        "margin_v": 110,
    },
}


def generate_ass(
    segments: list[TranscriptSegment],
    output_path: Path,
    style: str = "hormozi",
    play_res_x: int = 1080,
    play_res_y: int = 1920,
) -> Path:
    """
    Generate a word-by-word karaoke ASS subtitle file.

    Args:
        segments: Transcript segments with word timestamps
        output_path: Where to write the .ass file
        style: One of 'hormozi', 'minimal', 'neon'
        play_res_x/y: Video resolution (must match output video)

    Returns:
        Path to the generated .ass file
    """
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["hormozi"])

    lines = [_make_header(preset, play_res_x, play_res_y)]

    for seg in segments:
        words = [w for w in seg.words if w.start is not None and w.end is not None]
        if not words:
            # Fall back to segment-level timing if no word timestamps
            start_str = _fmt_ass_time(seg.start)
            end_str = _fmt_ass_time(seg.end)
            text = _escape_ass(seg.text.strip())
            lines.append(
                f"Dialogue: 0,{start_str},{end_str},ViralStyle,,0,0,0,,{text}"
            )
            continue

        # ── Word-by-word kinetic rendering ──────────────────────────────
        # Collect all words in segment for context display
        all_words_text = " ".join(w.word.strip() for w in words)

        for i, word in enumerate(words):
            start_str = _fmt_ass_time(word.start)
            end_str = _fmt_ass_time(word.end)

            # Build the text: highlighted current word + muted neighbours
            text_parts = []
            for j, w in enumerate(words):
                w_text = _escape_ass(w.word.strip())
                if j == i:
                    # Active word: bright highlight + pop scale animation
                    text_parts.append(
                        f"{{\\c{preset['highlight']}\\fscx115\\fscy115}}{w_text}"
                        f"{{\\c{preset['primary']}\\fscx100\\fscy100}}"
                    )
                else:
                    # Context words: slightly transparent/muted
                    text_parts.append(
                        f"{{\\alpha&H60&}}{w_text}{{\\alpha&H00&}}"
                    )

            text = " ".join(text_parts)
            # Center alignment override + position
            text = f"{{\\an2}}{text}"

            lines.append(
                f"Dialogue: 0,{start_str},{end_str},ViralStyle,,0,0,0,,{text}"
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


# ── Private helpers ───────────────────────────────────────────────────────────

def _make_header(preset: dict, play_res_x: int, play_res_y: int) -> str:
    """Build the ASS file header with style definition."""
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 1
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,{preset['fontname']},{preset['fontsize']},{preset['primary']},&H000000FF&,{preset['outline']},{preset['back']},{preset['bold']},0,0,0,100,100,0,0,1,{preset['outline_size']},{preset['shadow_size']},{preset['alignment']},10,10,{preset['margin_v']},1

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

