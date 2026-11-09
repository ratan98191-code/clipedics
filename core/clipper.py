"""
Clipedics – AI Clip Selection Engine (Phase 2: Unit-ID Selection & Temporal NMS)
Sends numbered atomic semantic Units to LLM providers (Groq / Gemini / Ollama)
and returns boundary-constrained, non-overlapping viral clip candidates.

Key Phase 2 Features:
1. Unit-ID Prompting: LLM selects by integer unit IDs, eliminating boundary hallucinations.
2. Constrained Boundary Search: strictly validates duration bounds against unit boundaries.
3. Multi-Modal Composite Scoring: combines LLM virality with audio dynamics, visual pacing, and hooks.
4. 1D Temporal NMS: eliminates overlapping redundant cuts using temporal IoU suppression.
"""
from __future__ import annotations
import json
import re
import sys
import time
from typing import Optional, Any

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
from core.models import ClipCandidate, Transcript, PipelineConfig, Unit
from core.units import format_units_for_llm, build_clip_from_units, build_units_from_transcript
from core.ranking import compute_composite_score, temporal_nms

console = Console()

# ── Prompts ───────────────────────────────────────────────────────────────────
CLIPPING_SYSTEM_PROMPT = """You are an expert viral short-form video editor and content strategist.
Your job is to analyze video transcripts divided into numbered atomic units and select the HIGHEST VIRALITY continuous segments to cut into short-form clips for TikTok, Instagram Reels, and YouTube Shorts.

CRITICAL RULES:
1. Each clip is defined by a continuous span of atomic units from `start_unit_id` to `end_unit_id`.
2. NEVER return floating-point timestamps. ONLY return integer unit IDs (`start_unit_id`, `end_unit_id`).
3. Each clip MUST be self-contained and make complete sense on its own.
4. Structure: HOOK (first 3-5s) → MEAT (insight/story) → RESOLUTION/PUNCHLINE.
5. Prioritize: explosive opening hooks, contrarian insights, intense emotional peaks, actionable tips, or humor.
6. Avoid clips that reference "earlier" or "as I said" without context.
7. Return a JSON object with a "clips" key containing an array of clip objects."""

CLIPPING_USER_PROMPT = """Analyze this video transcript structured into numbered units and extract the top {target_clips} most viral clips.

VIDEO DURATION: {duration}
LANGUAGE: {language}

NUMBERED UNITS TRANSCRIPT:
{transcript}

Return a valid JSON object matching this schema exactly:
{{
  "clips": [
    {{
      "clip_number": 1,
      "start_unit_id": 1,
      "end_unit_id": 12,
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
- Return ONLY integer "start_unit_id" and "end_unit_id" (never floating-point seconds).
- Clip duration across the selected units must be between {min_seconds}s and {max_seconds}s.
- "end_unit_id" must be greater than or equal to "start_unit_id".
- Extract up to {target_clips} clips.
"""


def select_clips(
    transcript: Transcript,
    config: Optional[PipelineConfig] = None,
    units: Optional[list[Unit]] = None,
) -> list[ClipCandidate]:
    """
    Dispatch transcript analysis to the configured LLM provider using explicit PipelineConfig and Unit boundaries.
    """
    cfg = config or PipelineConfig.from_env()
    provider = (cfg.llm_provider or LLM_PROVIDER).lower()

    if units is None:
        units = build_units_from_transcript(transcript)

    if provider == "groq" or (provider not in ("gemini", "ollama") and GROQ_API_KEY):
        return _select_clips_groq(transcript, cfg, units=units)
    elif provider == "gemini":
        return _select_clips_gemini(transcript, cfg, units=units)
    elif provider == "ollama":
        return _select_clips_ollama(transcript, cfg, units=units)
    else:
        if GROQ_API_KEY:
            return _select_clips_groq(transcript, cfg, units=units)
        raise ValueError(
            f"No valid LLM configuration found for provider '{provider}'.\n"
            f"Set GROQ_API_KEY in .env (get a free key at https://console.groq.com)"
        )


# ── Groq Provider ─────────────────────────────────────────────────────────────

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


def _select_clips_groq(
    transcript: Transcript,
    config: Optional[PipelineConfig] = None,
    units: Optional[list[Unit]] = None,
) -> list[ClipCandidate]:
    cfg = config or PipelineConfig.from_env()
    target_clips = cfg.num_clips
    min_seconds = cfg.min_seconds
    max_seconds = cfg.max_seconds

    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set.\n"
            "Get a free key at https://console.groq.com and add it to your .env file."
        )

    if units is None:
        units = build_units_from_transcript(transcript)

    duration = transcript.duration_seconds
    total_units = len(units)

    # Chunk units into ~360s windows to avoid Groq rate limits
    CHUNK_DURATION = 360.0
    num_chunks = max(1, int(round(duration / CHUNK_DURATION)))
    units_per_chunk = max(1, (total_units + num_chunks - 1) // num_chunks)
    unit_windows = [units[i : i + units_per_chunk] for i in range(0, total_units, units_per_chunk)]
    if not unit_windows:
        unit_windows = [units]

    target_per_chunk = max(1, (target_clips + len(unit_windows) - 1) // len(unit_windows))
    all_candidates: list[ClipCandidate] = []

    console.print(f"[cyan][Groq] Analyzing transcript ({duration:.0f}s, {total_units} units) across {len(unit_windows)} window(s)...[/cyan]")

    for idx, window_units in enumerate(unit_windows, 1):
        if not window_units:
            continue
        formatted_units_text = format_units_for_llm(window_units)
        if not formatted_units_text.strip():
            continue

        w_dur = window_units[-1].end_seconds - window_units[0].start_seconds
        chunk_prompt = CLIPPING_USER_PROMPT.format(
            target_clips=target_per_chunk,
            duration=_fmt_duration(w_dur),
            language=transcript.language,
            transcript=formatted_units_text,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
        )

        try:
            raw_json = _call_groq_single(chunk_prompt, cfg)
            chunk_clips = _parse_clips(raw_json, transcript, cfg, units=units)
            all_candidates.extend(chunk_clips)
            console.print(f"[green]✓ Groq found {len(chunk_clips)} clips in window {idx}/{len(unit_windows)}[/green]")
        except Exception as e:
            console.print(f"[yellow][!] Window {idx}/{len(unit_windows)} clipping failed: {e}[/yellow]")

        if idx < len(unit_windows):
            time.sleep(1.0)

    if not all_candidates:
        raise ValueError("Could not extract any valid clips from Groq.")

    # Re-score candidates using composite multi-modal ranker
    for cand in all_candidates:
        cand.virality_score = compute_composite_score(cand, units)

    # 1D Temporal Non-Maximum Suppression to eliminate overlapping candidates
    final_candidates = temporal_nms(all_candidates, iou_threshold=0.40, top_k=target_clips)
    console.print(f"[bold green]✓ Groq completed: {len(final_candidates)} top viral clips selected with Temporal NMS![/bold green]")
    return final_candidates


# ── Google Gemini Provider ────────────────────────────────────────────────────

def _select_clips_gemini(
    transcript: Transcript,
    config: Optional[PipelineConfig] = None,
    units: Optional[list[Unit]] = None,
) -> list[ClipCandidate]:
    cfg = config or PipelineConfig.from_env()
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )

    if units is None:
        units = build_units_from_transcript(transcript)

    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=GEMINI_API_KEY)
    console.print(f"[cyan][Gemini] Sending transcript to Gemini ({GEMINI_MODEL})...[/cyan]")

    prompt = _build_user_prompt(transcript, cfg, units=units)

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

    candidates = _parse_clips(response.text.strip(), transcript, cfg, units=units)

    # Re-score candidates using composite multi-modal ranker
    for cand in candidates:
        cand.virality_score = compute_composite_score(cand, units)

    return temporal_nms(candidates, iou_threshold=0.40, top_k=cfg.num_clips)


# ── Ollama Provider (Local) ───────────────────────────────────────────────────

def _select_clips_ollama(
    transcript: Transcript,
    config: Optional[PipelineConfig] = None,
    units: Optional[list[Unit]] = None,
) -> list[ClipCandidate]:
    cfg = config or PipelineConfig.from_env()
    console.print(f"[cyan][Ollama] Sending transcript to local Ollama ({OLLAMA_MODEL})...[/cyan]")

    if units is None:
        units = build_units_from_transcript(transcript)

    prompt = _build_user_prompt(transcript, cfg, units=units)

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
    candidates = _parse_clips(raw_text, transcript, cfg, units=units)

    for cand in candidates:
        cand.virality_score = compute_composite_score(cand, units)

    return temporal_nms(candidates, iou_threshold=0.40, top_k=cfg.num_clips)


# ── Shared Helpers ────────────────────────────────────────────────────────────

def _build_user_prompt(
    transcript: Transcript,
    config: Optional[PipelineConfig] = None,
    units: Optional[list[Unit]] = None,
) -> str:
    """Format prompt with numbered units."""
    cfg = config or PipelineConfig.from_env()
    if units is None:
        units = build_units_from_transcript(transcript)
    formatted_units = format_units_for_llm(units)
    return CLIPPING_USER_PROMPT.format(
        target_clips=cfg.num_clips,
        duration=_fmt_duration(transcript.duration_seconds),
        language=transcript.language,
        transcript=formatted_units,
        min_seconds=cfg.min_seconds,
        max_seconds=cfg.max_seconds,
    )


def _extract_int(val: Any) -> Optional[int]:
    """Safely extract an integer from an int, float, or formatted string like '[Unit 5]'."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, (float, str)):
        m = re.search(r"\d+", str(val))
        if m:
            return int(m.group())
    return None


def _find_closest_unit_id(target_sec: float, units: list[Unit], mode: str = "start") -> int:
    """Find the Unit ID whose boundary is closest to target timestamp."""
    if not units:
        return 1
    best_id = units[0].unit_id
    best_dist = float("inf")
    for u in units:
        bound = u.start_seconds if mode == "start" else u.end_seconds
        dist = abs(bound - target_sec)
        if dist < best_dist:
            best_dist = dist
            best_id = u.unit_id
    return best_id


def _parse_clips(
    raw_json: str,
    transcript: Transcript,
    config: Optional[PipelineConfig] = None,
    units: Optional[list[Unit]] = None,
) -> list[ClipCandidate]:
    """Parse JSON and snap clip boundaries to atomic Units with constrained boundary search."""
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

    clips_list = []
    if isinstance(data, list):
        clips_list = data
    elif isinstance(data, dict):
        for key in ("clips", "data", "segments", "results"):
            if key in data and isinstance(data[key], list):
                clips_list = data[key]
                break
        if not clips_list and data:
            if "start_unit_id" in data or "start_seconds" in data:
                clips_list = [data]

    if not clips_list:
        raise ValueError(f"No clips array found in response: {list(data.keys()) if isinstance(data, dict) else type(data)}")

    if units is None:
        units = build_units_from_transcript(transcript)

    candidates: list[ClipCandidate] = []
    for i, item in enumerate(clips_list):
        try:
            start_u_id = _extract_int(item.get("start_unit_id"))
            end_u_id = _extract_int(item.get("end_unit_id"))

            # Fallback: if LLM returned timestamps instead of unit IDs
            if start_u_id is None and "start_seconds" in item:
                s_sec = float(item["start_seconds"])
                start_u_id = _find_closest_unit_id(s_sec, units, mode="start")
            if end_u_id is None and "end_seconds" in item:
                e_sec = float(item["end_seconds"])
                end_u_id = _find_closest_unit_id(e_sec, units, mode="end")

            if start_u_id is None or end_u_id is None:
                console.print(f"[yellow][!] Skipping clip {i+1}: missing unit IDs[/yellow]")
                continue

            clip = build_clip_from_units(
                start_unit_id=start_u_id,
                end_unit_id=end_u_id,
                units=units,
                clip_number=i + 1,
                title=str(item.get("title", f"Clip {i+1}"))[:80],
                virality_score=int(item.get("virality_score", 70)),
                virality_rationale=str(item.get("virality_rationale", "")),
                hook_sentence=str(item.get("hook_sentence", "")),
                suggested_caption=str(item.get("suggested_caption", "")),
                hashtags=[str(h).lstrip("#") for h in item.get("hashtags", [])],
                min_seconds=min_sec,
                max_seconds=max_sec,
            )
            candidates.append(clip)
        except Exception as e:
            console.print(f"[yellow][!] Skipping malformed clip {i+1}: {e}[/yellow]")
            continue

    if not candidates:
        raise ValueError("Could not parse any valid clips from LLM response.")

    return candidates


def _fmt_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"
