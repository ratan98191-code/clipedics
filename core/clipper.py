"""
Clipedics – AI Clip Selection Engine (Multi-Provider: Groq / Gemini / Ollama)
Sends the timestamped transcript to the configured LLM and gets back
structured clip candidates with virality scores, titles, hooks, and captions.

Supported providers:
- groq (default): Llama 3.3 70B via Groq Cloud (14,400 free requests/day, ultra-fast)
- gemini: Gemini 2.0 Flash via Google GenAI SDK
- ollama: Local offline models (e.g. llama3.2:3b)
"""
from __future__ import annotations
import json
import re
from typing import Optional

import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config.settings import (
    LLM_PROVIDER,
    GROQ_API_KEY,
    GROQ_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    TARGET_CLIPS,
    CLIP_MIN_SECONDS,
    CLIP_MAX_SECONDS,
)
from core.models import ClipCandidate, Transcript, PipelineConfig

console = Console()

# ── Prompts ───────────────────────────────────────────────────────────────────
CLIPPING_SYSTEM_PROMPT = """You are an expert viral short-form video editor and content strategist.
Your job is to analyze video transcripts and identify the HIGHEST VIRALITY segments to cut into short-form clips for TikTok, Instagram Reels, and YouTube Shorts.

CRITICAL RULES:
1. Each clip MUST start at a natural sentence boundary — never mid-sentence or mid-thought.
2. Each clip MUST be self-contained and make complete sense on its own.
3. Prioritize: explosive opening hooks, contrarian insights, intense emotional peaks, actionable tips, or humor.
4. Avoid clips that reference "earlier" or "as I said" without context.
5. Structure: HOOK (first 3-5s) → MEAT (insight/story) → RESOLUTION/PUNCHLINE.
6. Return a JSON object with a "clips" key containing an array of clip objects."""

CLIPPING_USER_PROMPT = """Analyze this video transcript and extract the top {target_clips} most viral clips.

VIDEO DURATION: {duration}
LANGUAGE: {language}

TIMESTAMPED TRANSCRIPT:
{transcript}

Return a valid JSON object matching this schema exactly:
{{
  "clips": [
    {{
      "clip_number": 1,
      "start_seconds": 12.5,
      "end_seconds": 55.0,
      "title": "Short catchy title (under 60 chars)",
      "virality_score": 88,
      "virality_rationale": "Why this specific moment hooks viewers and drives shares",
      "hook_sentence": "The exact first spoken sentence of this clip",
      "suggested_caption": "Ready-to-post caption with emojis and curiosity loop",
      "hashtags": ["viral", "podcast", "mindset", "shorts"]
    }}
  ]
}}

REQUIREMENTS:
- Extract exactly {target_clips} clips.
- Each clip duration must be between {min_seconds}s and {max_seconds}s.
- "start_seconds" and "end_seconds" must align with actual speech timestamps in the transcript.
"""


def select_clips(transcript: Transcript, config: Optional[PipelineConfig] = None) -> list[ClipCandidate]:
    """
    Dispatch transcript analysis to the configured LLM provider using explicit PipelineConfig.
    """
    cfg = config or PipelineConfig.from_env()
    provider = (cfg.llm_provider or LLM_PROVIDER).lower()

    if provider == "groq" or (provider not in ("gemini", "ollama") and GROQ_API_KEY):
        return _select_clips_groq(transcript, cfg)
    elif provider == "gemini":
        return _select_clips_gemini(transcript, cfg)
    elif provider == "ollama":
        return _select_clips_ollama(transcript, cfg)
    else:
        # Default fallback to Groq if key available, else error
        if GROQ_API_KEY:
            return _select_clips_groq(transcript, cfg)
        raise ValueError(
            f"No valid LLM configuration found for provider '{provider}'.\n"
            f"Set GROQ_API_KEY in .env (get a free key at https://console.groq.com)"
        )


# ── Groq Provider ─────────────────────────────────────────────────────────────

def _format_compact_transcript(segments: list, start_time: float = 0.0, end_time: Optional[float] = None) -> str:
    """Format segments into compact timestamped lines to minimize tokens."""
    lines = []
    curr = []
    c_start = None

    for s in segments:
        if s.start < start_time:
            continue
        if end_time is not None and s.start >= end_time:
            break

        if c_start is None:
            c_start = s.start

        text = s.text.strip()
        curr.append(text)

        # Emit block every ~15 seconds or when sentence ends with punctuation
        if (s.end - c_start >= 15.0) or text.endswith((".", "!", "?")):
            combined = " ".join(curr)
            lines.append(f"[{int(c_start)}s - {int(s.end)}s] {combined}")
            curr = []
            c_start = None

    if curr and c_start is not None:
        lines.append(f"[{int(c_start)}s] {' '.join(curr)}")

    return "\n".join(lines)


def _call_groq_single(prompt: str, config: Optional[PipelineConfig] = None) -> str:
    """Perform a single Groq API call."""
    cfg = config or PipelineConfig.from_env()
    model = cfg.groq_model or GROQ_MODEL
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": CLIPPING_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    with httpx.Client(timeout=60.0) as client:
        res = client.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            raise ValueError(f"Groq API error ({res.status_code}): {res.text}")
        data = res.json()
    return data["choices"][0]["message"]["content"]


def _select_clips_groq(transcript: Transcript, config: Optional[PipelineConfig] = None) -> list[ClipCandidate]:
    cfg = config or PipelineConfig.from_env()
    target_clips = cfg.num_clips
    min_seconds = cfg.min_seconds
    max_seconds = cfg.max_seconds

    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set.\n"
            "Get a free key at https://console.groq.com and add it to your .env file."
        )

    duration = transcript.duration_seconds
    total_segs = len(transcript.segments)

    # Chunk into ~360s (6 min) windows to stay strictly under Groq's 7,000 ITPM limit
    CHUNK_DURATION = 360.0
    num_chunks = max(1, int(round(duration / CHUNK_DURATION)))
    if num_chunks > 1:
        chunk_len = duration / num_chunks
        chunks = [(i * chunk_len, (i + 1) * chunk_len) for i in range(num_chunks)]
    else:
        chunks = [(0.0, duration)]

    target_per_chunk = max(1, (target_clips + len(chunks) - 1) // len(chunks))
    all_candidates: list[ClipCandidate] = []

    console.print(f"[cyan][Groq] Analyzing transcript ({duration:.0f}s, {total_segs} segments) across {len(chunks)} window(s)...[/cyan]")

    for idx, (c_start, c_end) in enumerate(chunks, 1):
        compact_text = _format_compact_transcript(transcript.segments, start_time=c_start, end_time=c_end)
        if not compact_text.strip():
            continue

        chunk_prompt = CLIPPING_USER_PROMPT.format(
            target_clips=target_per_chunk,
            duration=_fmt_duration(c_end - c_start),
            language=transcript.language,
            transcript=compact_text,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )

        try:
            raw_json = _call_groq_single(chunk_prompt, cfg)
            chunk_clips = _parse_clips(raw_json, transcript, cfg)
            all_candidates.extend(chunk_clips)
            console.print(f"[green]✓ Groq found {len(chunk_clips)} clips in window {idx}/{len(chunks)}[/green]")
        except Exception as e:
            console.print(f"[yellow][!] Window {idx}/{len(chunks)} clipping failed: {e}[/yellow]")

        if idx < len(chunks):
            import time
            time.sleep(1.0)  # brief pause between chunk calls to avoid burst rate limits

    if not all_candidates:
        raise ValueError("Could not extract any valid clips from Groq.")

    # Deduplicate and sort by virality score
    unique_candidates = []
    seen_starts = set()
    for c in sorted(all_candidates, key=lambda x: x.virality_score, reverse=True):
        if not any(abs(c.start_seconds - s) < 15 for s in seen_starts):
            seen_starts.add(c.start_seconds)
            unique_candidates.append(c)

    final_candidates = unique_candidates[:target_clips]
    for i, c in enumerate(final_candidates, 1):
        c.clip_number = i

    console.print(f"[bold green]✓ Groq completed: {len(final_candidates)} top viral clips selected![/bold green]")
    return final_candidates


# ── Google Gemini Provider ────────────────────────────────────────────────────

def _select_clips_gemini(transcript: Transcript, config: Optional[PipelineConfig] = None) -> list[ClipCandidate]:
    cfg = config or PipelineConfig.from_env()
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )

    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=GEMINI_API_KEY)
    console.print(f"[cyan][Gemini] Sending transcript to Gemini ({GEMINI_MODEL})...[/cyan]")

    prompt = _build_user_prompt(transcript, cfg)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Gemini analyzing viral moments...", total=None)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=CLIPPING_SYSTEM_PROMPT,
                temperature=0.4,
                response_mime_type="application/json",
            ),
        )
        progress.update(task, description="Gemini analysis complete ✓")

    candidates = _parse_clips(response.text.strip(), transcript, cfg)
    candidates.sort(key=lambda c: c.virality_score, reverse=True)
    return candidates[:cfg.num_clips]


# ── Ollama Provider (Local) ───────────────────────────────────────────────────

def _select_clips_ollama(transcript: Transcript, config: Optional[PipelineConfig] = None) -> list[ClipCandidate]:
    cfg = config or PipelineConfig.from_env()
    console.print(f"[cyan][Ollama] Sending transcript to local Ollama ({OLLAMA_MODEL})...[/cyan]")

    prompt = _build_user_prompt(transcript, cfg)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"Ollama running {OLLAMA_MODEL} on CPU...", total=None)

        url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": CLIPPING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "format": "json",
            "stream": False,
        }

        try:
            with httpx.Client(timeout=180.0) as client:
                res = client.post(url, json=payload)
                if res.status_code != 200:
                    raise ValueError(f"Ollama error ({res.status_code}): {res.text}")
                data = res.json()
        except httpx.RequestError as e:
            raise RuntimeError(
                f"Could not connect to Ollama at {OLLAMA_BASE_URL}.\n"
                f"Ensure Ollama is running (`ollama serve`). Error: {e}"
            ) from e

        progress.update(task, description="Ollama analysis complete ✓")

    raw_text = data.get("message", {}).get("content", "")
    candidates = _parse_clips(raw_text, transcript, cfg)
    candidates.sort(key=lambda c: c.virality_score, reverse=True)
    return candidates[:cfg.num_clips]


# ── Shared Helpers ────────────────────────────────────────────────────────────

def _build_user_prompt(transcript: Transcript, config: Optional[PipelineConfig] = None) -> str:
    """Format prompt with compressed timestamp text."""
    cfg = config or PipelineConfig.from_env()
    return CLIPPING_USER_PROMPT.format(
        target_clips=cfg.num_clips,
        duration=_fmt_duration(transcript.duration_seconds),
        language=transcript.language,
        transcript=transcript.to_timestamped_text(),
        min_seconds=cfg.min_seconds,
        max_seconds=cfg.max_seconds,
    )


def _parse_clips(raw_json: str, transcript: Transcript, config: Optional[PipelineConfig] = None) -> list[ClipCandidate]:
    """Parse JSON and snap clip boundaries to transcript segments."""
    cfg = config or PipelineConfig.from_env()
    min_sec = cfg.min_seconds
    max_sec = cfg.max_seconds
    cleaned = re.sub(r"```json\s*|\s*```", "", raw_json).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        console.print(f"[red]Failed to parse JSON response:[/red] {e}")
        console.print(f"[dim]{cleaned[:400]}[/dim]")
        raise ValueError(f"LLM returned invalid JSON: {e}") from e

    # Extract clips array (handles {"clips": [...]} or raw [...])
    clips_list = []
    if isinstance(data, list):
        clips_list = data
    elif isinstance(data, dict):
        for key in ("clips", "data", "segments", "results"):
            if key in data and isinstance(data[key], list):
                clips_list = data[key]
                break
        if not clips_list and data:
            # Maybe single clip dict or numbered keys
            if "start_seconds" in data:
                clips_list = [data]

    if not clips_list:
        raise ValueError(f"No clips array found in response: {list(data.keys()) if isinstance(data, dict) else type(data)}")

    candidates = []
    for i, item in enumerate(clips_list):
        try:
            start = _snap_to_segment(float(item["start_seconds"]), transcript, mode="start")
            end = _snap_to_segment(float(item["end_seconds"]), transcript, mode="end")

            duration = end - start
            if duration < min_sec:
                console.print(f"[yellow][!] Clip {i+1} too short ({duration:.1f}s), adjusting[/yellow]")
                end = min(transcript.duration_seconds, start + min_sec)

            if duration > max_sec:
                end = start + max_sec

            candidates.append(ClipCandidate(
                clip_number=i + 1,
                start_seconds=round(start, 2),
                end_seconds=round(end, 2),
                title=str(item.get("title", f"Clip {i+1}"))[:80],
                virality_score=int(item.get("virality_score", 70)),
                virality_rationale=str(item.get("virality_rationale", "")),
                hook_sentence=str(item.get("hook_sentence", "")),
                suggested_caption=str(item.get("suggested_caption", "")),
                hashtags=[str(h).lstrip("#") for h in item.get("hashtags", [])],
            ))
        except (KeyError, ValueError, TypeError) as e:
            console.print(f"[yellow][!] Skipping malformed clip {i+1}: {e}[/yellow]")
            continue

    if not candidates:
        raise ValueError("Could not parse any valid clips from LLM response.")

    return candidates


def _snap_to_segment(time_seconds: float, transcript: Transcript, mode: str = "start") -> float:
    if not transcript.segments:
        return time_seconds

    best = None
    best_dist = float("inf")

    for seg in transcript.segments:
        boundary = seg.start if mode == "start" else seg.end
        dist = abs(boundary - time_seconds)
        if dist < best_dist:
            best_dist = dist
            best = boundary

    return best if best is not None else time_seconds


def _fmt_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"
