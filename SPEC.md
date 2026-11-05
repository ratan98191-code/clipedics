# SPEC: Accuracy Measurement & Narrative Engine Roadmap (Phases 0–7)

## Overview
Transform Clipedics from an ad-hoc heuristic clipper into an empirical, narrative-driven video engine.
Prior to any advanced feature work, accuracy must be defined, measurable, and falsifiable with ground-truth evaluation sets and quantitative metrics.

---

## Phase Matrix

| Phase | Goal | Size | Depends on | Gate |
|---|---|---|---|---|
| **0** | **Make it run, make it measurable** | **S** | **none** | **Baseline recorded across 5 metrics; 6 blockers resolved; CI fails on error** |
| 1 | Feature foundation: ASR, units, audio, shots | M | 0 | ≥95% cuts in pauses; median word timing error <80ms |
| 2 | Better contiguous clips (LLM unit IDs, temporal NMS) | M | 1 | Recall@k and human rating beat Phase 0 baseline |
| 3 | Reframe rewrite (IoU tracker, active speaker, One-Euro) | L | 1 | Subject-in-crop rate and jitter threshold |
| 4 | Caption rewrite (2-4 words, hold to next word, safe zones) | S | 1 | Visual QA checklist passed |
| 5 | EDL data model & non-linear renderer (cold open first) | M | 2, 3, 4 | No audio clicks, caption sync within 1 frame, blind human A/B |
| 6 | Narrative planner (hook → build → peak → cliffhanger) | L | 5 | Hook in first 3s, role order respected, 100% faithfulness check |
| 7 | Editor UI & learned ranker | M | 2 | Fitted ranker outperforming hand-set salience weights |

Critical Path: `0 → 1 → 2 → 5 → 6`. (Phases 2, 3, 4 can run in parallel once 1 completes).

---

## Phase 0 Specification: Run and Measure

### 1. Fix Infrastructure Blockers
1. **`pyproject.toml` Build Backend & Dependencies**:
   - Set standard PEP 517 build backend: `setuptools.build_meta`.
   - Replace brittle `whisperx` with `faster-whisper>=1.0.0`.
   - Declare all runtime dependencies: `fastapi`, `uvicorn`, `celery`, `redis`, `sqlalchemy`, `aiosqlite`, `groq`, `pydantic`, `ffmpeg-python`, `yt-dlp`, `rich`, `typer`, `httpx`.
2. **Explicit `PipelineConfig`**:
   - Eliminate module-level variable mutations on `config.settings`.
   - Introduce `core.models.PipelineConfig` (or `core.config.PipelineConfig`) with strongly-typed overrides.
   - Pass `PipelineConfig` explicitly through `workers.pipeline`, `core.clipper`, `core.transcriber`, and `core.renderer`.
3. **Apostrophe Filename Bug in ASS Subtitles**:
   - In `core.renderer`, write ASS files as `clip_{candidate.clip_number:02d}.ass`.
   - Escape special characters (`'`, `:`, `\`) in FFmpeg filter string paths.
4. **Repair `alembic.ini`**:
   - Remove Python docstring `"""` from the top of the INI file so `alembic` commands parse correctly.
5. **Docker Compose Port Binding**:
   - Bind all ports strictly to `127.0.0.1` (`127.0.0.1:6379:6379`, `127.0.0.1:8000:8000`, `127.0.0.1:5555:5555`).
6. **CI Test Enforcement**:
   - Update `.github/workflows/ci.yml` so `pytest` failure fails the CI job (no `|| echo ...` suppression).

### 2. Evaluation Dataset
- **Manifest**: `evals/manifest.json` containing 12–15 curated videos across 3 target genres:
  - Podcast (dialogue, multi-topic, conversational turns)
  - Interview / Talk (keynote, Q&A, tech talks)
  - Tutorial / Vlog (fast-paced, screen share, single-speaker instructions)
- **Ground Truth**: Human-selected top clips with `[start_seconds, end_seconds]`, quality score (1–5), and narrative rationale.
- **Transcript Cache**: `evals/cache/transcripts/{video_id}.json` containing pre-computed word-level transcripts to guarantee zero API cost and deterministic evaluation.

### 3. Quantitative Metric Suite (`evals/metrics.py`)
1. **Cut-in-Pause Rate**:
   $$\text{PauseCutRate} = \frac{\text{Cuts landing in silence/pause } (\ge 0.3\text{s})}{\text{Total Cuts}}$$
2. **Sentence-Boundary Rate**:
   $$\text{SentenceBoundaryRate} = \frac{\text{Cuts landing at sentence-final punctuation (. ! ?)}}{\text{Total Cuts}}$$
3. **Recall@k (IoU $\ge 0.5$)**:
   Recall of candidate clips against human ground truth clips using temporal Intersection over Union.
4. **Caption Timing Error**:
   Mean absolute discrepancy between word audio boundary and displayed subtitle timing.
5. **Processing Speed**:
   Seconds of wall-clock processing time per minute of input video.

### 4. Phase 0 Gate
- Baseline run executed via `python evals/evaluate.py --baseline`.
- Results persisted to `evals/BASELINE.md`.
