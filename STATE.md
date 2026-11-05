# Clipedics Development State

## Current Phase: Phase 0 (Make it run, make it measurable)
**Status**: COMPLETED ✅
**Completed**: 2026-11-05
**Objective**: Fix the 6 build & infrastructure blockers, build the evaluation set + metric suite, and record baseline scores.

---

## Phase 0 Deliverables & Verification Checklist

- [x] **Task 0.1: Fix the 6 Infrastructure Blockers**
  - [x] 0.1.1: Fix `pyproject.toml` build backend (`setuptools.build_meta`) and runtime dependencies (`faster-whisper`, `fastapi`, `celery`, etc.)
  - [x] 0.1.2: Implement `PipelineConfig` in `core.models` and eliminate settings-import mutations
  - [x] 0.1.3: Fix ASS apostrophe bug with `clip_{n}.ass` and path escaping
  - [x] 0.1.4: Repair `alembic.ini` syntax (remove `"""`)
  - [x] 0.1.5: Bind docker-compose ports strictly to `127.0.0.1`
  - [x] 0.1.6: Fix `.github/workflows/ci.yml` so test failures fail CI
- [x] **Task 0.2: Automated Regression Tests**
  - [x] Wrote `tests/test_blockers.py` covering all 6 infrastructure areas
  - [x] `pytest tests/ -v` passes: 6 passed in 2.64s
- [x] **Task 0.3: Evaluation Dataset Manifest & Cache**
  - [x] Created `evals/manifest.json` with 12 curated videos across Podcast, Interview/Talk, Tutorial/Vlog
  - [x] Included ground-truth clips with human ratings and 3 multi-beat trailer cuts for Phase 6
  - [x] Generated deterministic word-level transcript caches in `evals/cache/transcripts/`
- [x] **Task 0.4: Metrics Suite & Evaluation Runner**
  - [x] Built `evals/metrics.py` (cut-in-pause rate, sentence-boundary rate, recall@k IoU≥0.5, caption timing drift)
  - [x] Built `evals/evaluate.py`
- [x] **Task 0.5: Baseline Recording (Phase 0 Gate)**
  - [x] Executed baseline evaluation across all 12 benchmark videos
  - [x] Generated `evals/BASELINE.md`

---

## Baseline Gate Results (Recorded in `evals/BASELINE.md`)

| Metric | Phase 0 Baseline | Phase 1 Target Gate | Phase 2 Target Gate |
|---|---|---|---|
| **Cut-in-pause rate** | **20.8%** | ≥ 95.0% | ≥ 98.0% |
| **Sentence-boundary rate** | **1.4%** | ≥ 90.0% | ≥ 95.0% |
| **Recall@3 (IoU ≥ 0.5)** | **33.3%** | — | > 33.3% |
| **Recall@5 (IoU ≥ 0.5)** | **33.3%** | — | > 33.3% |
| **Caption timing drift** | **110.2 ms** | < 80.0 ms | < 50.0 ms |

---

## Next Phase: Phase 1 (Feature Foundation: ASR, Units, Audio, Shots)
- Forced alignment & larger model options
- Unit chunking (split on word gap ≥ 0.35s or sentence punctuation; snap to RMS valleys ±150ms)
- Per-unit audio/visual feature cache (loudness ebur128, speech rate, silence map, PySceneDetect shot boundaries, face tracks)
