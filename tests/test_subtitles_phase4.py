"""
Unit tests for Clipedics Phase 4: Caption Rewrite
Tests 2-4 word micro-chunking, max 2 lines, zero-gap hold protocol,
platform safe zone margins, and non-linear remap().
"""
from __future__ import annotations
import re
import pytest
from pathlib import Path
from core.models import WordSegment, TranscriptSegment
from core.subtitles import (
    chunk_words,
    remap_words,
    generate_ass,
    STYLE_PRESETS,
    DEFAULT_SAFE_MARGIN_V,
)


@pytest.fixture
def sample_words():
    return [
        WordSegment(word="Why", start=0.0, end=0.3),
        WordSegment(word="dopamine", start=0.35, end=0.8),
        WordSegment(word="is", start=0.85, end=1.0),
        WordSegment(word="the", start=1.05, end=1.2),
        WordSegment(word="most", start=1.25, end=1.5),
        WordSegment(word="misunderstood", start=1.55, end=2.2),
        WordSegment(word="molecule", start=2.25, end=2.7),
        WordSegment(word="in", start=2.75, end=2.9),
        WordSegment(word="neuroscience.", start=2.95, end=3.8),
    ]


def test_chunk_words_bounds_and_lines(sample_words):
    chunks = chunk_words(sample_words, min_words=2, max_words=4)
    assert len(chunks) >= 2

    for c in chunks:
        # Every chunk should be between 2 and 4 words
        assert 2 <= c.word_count <= 4
        # Maximum 2 lines per chunk
        assert c.line_count <= 2
        # Text must be non-empty
        assert len(c.full_text()) > 0


def test_zero_gap_hold_protocol(sample_words, tmp_path):
    ass_file = tmp_path / "test_zero_gap.ass"
    generate_ass(sample_words, ass_file)
    assert ass_file.exists()

    content = ass_file.read_text(encoding="utf-8")
    dialogues = [line for line in content.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogues) == len(sample_words)

    # Parse Start and End times of each dialogue event
    times = []
    for d in dialogues:
        parts = d.split(",")
        start_str = parts[1]
        end_str = parts[2]
        times.append((start_str, end_str))

    # Verify that dialogue[i] end time matches dialogue[i+1] start time (Zero-Gap Hold)
    for i in range(len(times) - 1):
        curr_end = times[i][1]
        next_start = times[i + 1][0]
        assert curr_end == next_start, f"Gap detected between word {i} ({curr_end}) and {i+1} ({next_start})"


def test_platform_safe_zones(tmp_path, sample_words):
    ass_file = tmp_path / "test_safe_zone.ass"
    generate_ass(sample_words, ass_file, style="hormozi", safe_zone_margin_v=420)

    content = ass_file.read_text(encoding="utf-8")
    style_line = [l for l in content.splitlines() if l.startswith("Style: ViralStyle")][0]
    parts = style_line.split(",")

    # Safe zone checks:
    margin_l = int(parts[19])
    margin_r = int(parts[20])
    margin_v = int(parts[21])
    alignment = int(parts[18])

    assert margin_v == 420  # Safe zone clears bottom controls (>= 320px)
    assert margin_l == 80
    assert margin_r == 120  # Clears right-rail action buttons
    assert alignment == 2   # Bottom-center alignment


def test_remap_words_non_linear():
    # Source words from two non-contiguous cuts
    source_words = [
        WordSegment(word="Hook", start=10.0, end=10.5),
        WordSegment(word="line", start=10.6, end=11.2),
        WordSegment(word="Ignored", start=20.0, end=20.5),
        WordSegment(word="Payoff", start=35.0, end=35.6),
        WordSegment(word="moment", start=35.7, end=36.4),
    ]

    # Non-linear EDL: Cut 1 is [10.0, 12.0] (2s), Cut 2 is [35.0, 37.0] (2s)
    edl_cuts = [(10.0, 12.0), (35.0, 37.0)]
    remapped = remap_words(source_words, edl_cuts)

    assert len(remapped) == 4  # "Ignored" was outside the cuts and excluded
    assert remapped[0].word == "Hook"
    assert remapped[0].start == 0.0
    assert remapped[0].end == 0.5

    assert remapped[1].word == "line"
    assert remapped[1].start == 0.6
    assert remapped[1].end == 1.2

    # Second cut starts at output time 2.0s
    assert remapped[2].word == "Payoff"
    assert remapped[2].start == 2.0
    assert remapped[2].end == 2.6

    assert remapped[3].word == "moment"
    assert remapped[3].start == 2.7
    assert remapped[3].end == 3.4


def test_font_stacks_and_styling(tmp_path, sample_words):
    for style_name in ("hormozi", "minimal", "neon"):
        ass_file = tmp_path / f"test_{style_name}.ass"
        generate_ass(sample_words, ass_file, style=style_name)
        content = ass_file.read_text(encoding="utf-8")
        assert STYLE_PRESETS[style_name]["fontname"] in content
        # Scale-pop animation tag present
        assert "\\fscx112\\fscy112" in content

