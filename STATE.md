# STATE: Clipedics Development State & Mission Control

> **Methodology**: GSD (Get Shit Done) — Spec-Driven, Context-Engineered  
> **Status**: ACTIVE — Phase 1 (Real Evaluation Harness) Reset  
> **Last Updated**: 2026-11-09

---

## 1. Reality Check & Baseline Reset
A static codebase audit revealed:
1. Previous evaluation metrics in `evals/evaluate.py` relied on synthetic hand-typed transcripts (`evals/build_cache.py`) and hardcoded constants for downstream phases ($0.978$ subject in crop, $0.884$ ranker $R^2$, etc.).
2. Production worker (`workers/pipeline.py`) called unit builder without audio samples (skipping true RMS snapping), flattened face tracks to a single static crop, and bypassed advanced modules.
3. Editor API endpoints (`trim`, `swap-beats`, `rerender`) updated database state and logged feedback without triggering FFmpeg re-rendering.

**Resolution**: All synthetic claims have been invalidated. Development is now governed by the **Roadmap to Vizard-Level Clip Quality** with empirical, artifact-computed verification at every gate.

---

## 2. Phase Execution State

| Phase | Description | Size | Status | Verification Gate |
|---|---|---|---|---|
| **Phase 1** | **Real Evaluation Harness** | M | **ACTIVE** | `python evals/run.py --split dev` produces full artifact-backed baseline |
| Phase 2 | Production Architecture Wiring | M | QUEUED | End-to-end dev run with piecewise reframe & working editor re-renders |
| Phase 3 | ASR, Alignment & Boundaries | M | QUEUED | Word timing $<60\text{ms}$, $\ge 95\%$ silence cuts, $\ge 90\%$ sentence bounds |
| Phase 4 | Speaker-Aware Reframing | L | QUEUED | $\ge 95\%$ active speaker in crop, DER $\le 15\%$, 0 whip pans |
| Phase 5 | Selection Quality & Ranking | L | QUEUED | Recall@5 beats plain-LLM; blind A/B vs Vizard $\ge 45\%$ |
| Phase 6 | Presentation Polish | S | QUEUED | Visual styling pass across 9:16, 1:1, 16:9 |
| Phase 7 | Feedback Loop & Learned Ranker | Ongoing | QUEUED | Generalization on held-out AUC/Spearman after $\ge 200$ ratings |

---

## 3. Active Phase 1 Checklist (Real Evaluation Harness)

- [ ] **Step 3.1: Clean Up & Quarantine Synthetic Fixtures**
  - [ ] Move `evals/cache/*` and `evals/build_cache.py` to `tests/fixtures/synthetic/`
  - [ ] Strip hardcoded constants and fake formulas from `evals/evaluate.py` and `evals/metrics.py`
  - [ ] Update `README.md` to remove synthetic benchmark numbers
- [ ] **Step 3.2: Benchmark Dataset (`evals/bench_v2/`)**
  - [ ] Curate 24 real videos (8 podcast, 8 talk/keynote, 8 tutorial/vlog) with source URLs and metadata
  - [ ] Create `evals/bench_v2/manifest.json` with 16 dev / 8 held-out test split
- [ ] **Step 3.3: Ground Truth Annotations Schema & Data**
  - [ ] Define ground-truth clip intervals (published shorts, blind human picks, reference)
  - [ ] Define gold word timing references
  - [ ] Define reframe active speaker bounding boxes
- [ ] **Step 3.4: Real Metric Engine (`evals/metrics.py`)**
  - [ ] Implement true audio waveform silence measurement at cuts ($\pm 150\text{ms}$ vs noise floor)
  - [ ] Implement true sentence boundary calculation from transcript word punct
  - [ ] Implement real word timing error against gold timestamps
  - [ ] Implement bounding-box subject-in-crop & real crop jitter
  - [ ] Implement pairwise A/B testing harness
- [ ] **Step 3.5: Baseline Evaluation Runner (`evals/run.py`)**
  - [ ] Build `evals/run.py` to execute real baselines on dev split
  - [ ] Record true unvarnished baselines to `evals/BASELINE_V2.md`
