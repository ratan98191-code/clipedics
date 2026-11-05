# Clipedics Development State

## Phase 0: Make it run, make it measurable
**Status**: COMPLETED ✅
**Completed**: 2026-11-05
- Fixed all 6 infrastructure blockers
- Created 12-video eval manifest with ground truth
- Built deterministic transcript cache and metrics runner
- Baseline recorded in `evals/BASELINE.md`

---

## Phase 1: Feature foundation (ASR, units, audio, shots)
**Status**: COMPLETED ✅
**Completed**: 2026-11-05
**Gate Goal**: Cut-in-pause rate ≥ 95.0%, Sentence-boundary rate ≥ 90.0%, Caption drift < 80.0 ms.

### Phase 1 Deliverables & Verification Checklist
- [x] **Unit Data Model (`core.models.Unit`)**:
  - Sequential `unit_id` (1, 2, 3...) for unambiguous LLM prompting
  - `start_seconds`, `end_seconds`, `raw_start_seconds`, `raw_end_seconds`
  - Multi-modal features: `loudness_lufs`, `speech_rate_wpm`, `pause_before_sec`, `pause_after_sec`, `shot_ids`, `face_detected`, `dominant_face_x`
- [x] **Unit Segmentation & RMS Valley Snapping (`core/units.py`)**:
  - Split on word gap ≥ 0.35s OR sentence-final punctuation (`.`, `!`, `?`)
  - Vectorized RMS envelope calculation (`compute_rms_envelope`) with local minimum detection (`find_rms_valley`) in ±150ms window
  - Inter-word silence padding fallback when audio waveform is not in memory
  - `assemble_contiguous_clips_from_units` for atomic unit-aligned candidate generation
- [x] **Multi-Modal Feature Extraction (`core/features.py`)**:
  - RMS dBFS / integrated loudness per unit (`compute_audio_loudness_lufs`)
  - Silence map detector (`extract_silence_map`) for quiet intervals (< -38 dBFS)
  - PySceneDetect shot boundary detector (`detect_shot_boundaries`)
  - Unit feature enrichment (`enrich_units_with_features`)
- [x] **Persistent Feature Cache (`core/cache.py`)**:
  - Fast JSON serialization and retrieval of pre-computed units
  - Populated 12 benchmark unit caches in `evals/cache/units/`
- [x] **Automated Test Suite**:
  - 10 automated unit and regression tests passing (`pytest tests/ -v`)
- [x] **Empirical Gate Verification (`evals/PHASE1_GATE.md`)**:
  - Evaluated on all 12 benchmark videos in `evals/manifest.json`

---

## Empirical Comparison: Baseline vs. Phase 1 Gate

| Metric | Phase 0 Baseline | Phase 1 Result | Phase 1 Target Gate | Gate Status |
|---|---|---|---|---|
| **Cut-in-pause rate** | 20.8% | **97.2%** | ≥ 95.0% | **✅ PASS** |
| **Sentence-boundary rate** | 1.4% | **97.2%** | ≥ 90.0% | **✅ PASS** |
| **Recall@3 (IoU ≥ 0.5)** | 33.3% | **75.0%** | Reference | **+41.7%** |
| **Recall@5 (IoU ≥ 0.5)** | 33.3% | **75.0%** | Reference | **+41.7%** |
| **Caption timing drift** | 110.2 ms | **72.5 ms** | < 80.0 ms | **✅ PASS** |
| **Processing speed** | < 1.0s / min | **< 1.0s / video-min** | < 15.0s / min | **✅ PASS** |

---

## Next Phase: Phase 2 (Better contiguous clips)
- Prompt LLM with numbered Unit IDs (never raw timestamps)
- Global candidate pool per window, temporal NMS on IoU, global ranking
- Combine LLM salience with audio (loudness, speech rate) and visual features
- Boundary constrained search: end after start, duration constraints, re-snap
- **Gate**: Recall@k and human ratings beat Phase 0 baseline (Goal: Recall@3 > 75%, Recall@5 > 75%)
