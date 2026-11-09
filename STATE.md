# STATE: Clipedics Development State & Mission Control

> **Methodology**: GSD (Get Shit Done) — Spec-Driven, Context-Engineered  
> **Status**: ACTIVE — Phase 2 (Architecture Wiring) implemented; bugs documented  
> **Last Updated**: 2026-11-09

---

## 1. Audit Findings (2026-11-09)

An honest code review revealed two categories of problems:

### Phase 1 — Fabricated Baseline (now fixed)
The old `evals/bench_v2/` evaluation harness fed real metric functions invented data:
- `build_dev_cache.py` synthesized `audio.wav` from sine-wave bursts; has been moved to `tests/fixtures/synthetic/`
- `init_annotations.py` populated ground truth from same synthetic data; also moved
- All `cache/*/audio.wav`, `transcript.json`, `crop_path.json` and all `ground_truth/` JSON files have been **deleted**
- `evals/BASELINE_V2.md` has been **deleted** — every number in it was fabricated
- `evals/run.py` has been **rewritten** to call `select_clips()` on real cached data with no canned analysis text

**Resolution**: Bench v2 cache and ground_truth directories are now in `.gitignore`. See `evals/bench_v2/README.md` for instructions on populating real data.

### Phase 2 — Real but Buggy
Core architecture wiring (`core/pipeline.py`, `workers/pipeline.py`, `api/routers/clips.py`) is real. Seven bugs were identified and partially fixed (see section 3).

---

## 2. Phase Execution State

| Phase | Description | Status | Gate |
|-------|-------------|--------|------|
| **Phase 1** | **Real Evaluation Harness** | **INCOMPLETE** — metric engine exists; no real data yet. See `evals/bench_v2/README.md` | Real cached transcripts + hand-annotated GT on >=3 real videos |
| **Phase 2** | **Production Architecture Wiring** | **IMPLEMENTED (bugs listed below)** | End-to-end run on 3 real videos with working editor re-renders |
| Phase 3 | ASR, Alignment & Boundaries | QUEUED | Word timing <60ms, >=95% silence cuts, >=90% sentence bounds |
| Phase 4 | Speaker-Aware Reframing | QUEUED | >=95% active speaker in crop, DER <=15%, 0 whip pans |
| Phase 5 | Selection Quality & Ranking | QUEUED | Recall@5 beats plain-LLM; blind A/B vs Vizard >=45% |
| Phase 6 | Presentation Polish | QUEUED | Visual styling pass across 9:16, 1:1, 16:9 |
| Phase 7 | Feedback Loop & Learned Ranker | QUEUED | Generalization on held-out AUC/Spearman after >=200 ratings |

---

## 3. Phase 2 Bug Tracker

| # | Bug | File | Status |
|---|-----|------|--------|
| 1 | `rerender_clip_task` drops captions — passes no words | `workers/pipeline.py` | **FIXED** — words serialized into `clip_plan_json["words"]` and loaded on rerender |
| 2 | Audio dips at every camera cut — fades applied even at contiguous shot boundaries | `core/renderer.py` | **FIXED** — fades only applied when `abs(beat_i.src_start - beat_{i-1}.src_end) > 1ms` |
| 3 | `face_detected` wrongly True whenever crop_path exists | `core/pipeline.py` | **FIXED** — set from `shot_plans[].face_detected`; falls back to False |
| 4 | Beat swap scrambles speech; `except: pass` hides broker failure | `api/routers/clips.py` | **FIXED** — single-beat guard added; broker error raised as 503; task ID surfaced |
| 5 | Crop still static per shot (no real per-frame tracking) | `core/reframer.py` | OPEN — needs MediaPipe face detection wired per-frame |
| 6a | `scipy` missing from `pyproject.toml` | `pyproject.toml` | **FIXED** — added `scipy>=1.11.0` |
| 6b | `clip_plan_json` column without migration | `api/database.py` | **FIXED** — `_apply_inline_migrations()` runs `ALTER TABLE ... ADD COLUMN` on startup |
| 7a | Dead flag `enable_narrative` calls `to_clip_plan_beats()` that doesn't exist | `core/pipeline.py` | **FIXED** — `hasattr` guard added |
| 7b | Dead flag `enable_cold_open` reads `_cold_open_plan` that nothing sets | `core/pipeline.py` | Guarded with `getattr(..., None)` — open until Phase 5 wires it |

---

## 4. Next Steps (Priority Order)

1. **Run pipeline on 3 real videos** — download, extract audio, run ASR, copy outputs to `evals/bench_v2/cache/<id>/`
2. **Hand-annotate ground truth** — 100 words per video, 40 reframe frames, real clip intervals
3. **Run `python evals/run.py`** — verify runner produces non-N/A numbers on real data
4. **Fix Bug 5** (static crop) — wire MediaPipe per-frame face detection
5. **Full end-to-end re-render test** — trigger trim/rerender via API; confirm captions appear

---

## 5. Services

| Service | Command | Port |
|---------|---------|------|
| FastAPI backend | `uvicorn api.main:app --host 127.0.0.1 --port 8000` | 8000 |
| Celery worker | `celery -A workers.celery_app worker --loglevel=info --pool=solo` | — |
| Next.js frontend | `npm run dev` (from `frontend/`) | 3000 |
| Redis (Celery broker) | `redis-server` | 6379 |

---

## 6. Constraints

- **No synthetic data as benchmark** — user constraint; enforced by `.gitignore` and rewritten runner
- **No `except: pass`** — all silent exception swallows have been replaced with explicit raises or logged errors
- **Empirical verification required** — every claimed metric must trace to a physical artifact
- **Single-user local setup** — no external billing/auth restrictions
