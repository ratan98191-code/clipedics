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

## Phase 2: Better contiguous clips (ships value early)
**Status**: COMPLETED ✅  
**Completed**: 2026-11-09  
**Gate Goal**: Cut-in-pause rate ≥ 95.0%, Sentence-boundary rate ≥ 90.0%, Recall@k > Phase 0 baseline (33.3%).

### Phase 2 Deliverables & Verification Checklist
- [x] **Unit-ID Prompting & Parsing Engine (`core/clipper.py`)**:
  - Formatted transcript into numbered atomic units `[Unit {id}] ({duration}s): {text}`
  - Updated LLM prompts to instruct integer `start_unit_id` and `end_unit_id` selection
  - Implemented robust unit ID parsing with timestamp-to-unit fallback mapping
- [x] **Constrained Boundary Search (`core/units.py`)**:
  - Implemented `constrained_boundary_search(start_id, end_id, units, min_sec, max_sec)`
  - Enforced `end >= start`, forward expansion for short clips, backward trimming for long clips
  - Assembled `ClipCandidate` strictly from snapped unit boundaries via `build_clip_from_units`
- [x] **Multi-Modal Composite Scorer (`core/ranking.py`)**:
  - Audio salience: loudness consistency and speech rate pacing (130-170 WPM)
  - Visual salience: camera cut rhythm (4-18 cuts/min) and face presence
  - Hook punchiness: concise opening (2-5.5s), opening pause cleaniness, linguistic curiosity triggers
  - Composite scoring function combining LLM/semantic salience with acoustic and visual dynamics
- [x] **1D Temporal Non-Maximum Suppression (`core/ranking.py`)**:
  - Global candidate pool across windows
  - 1D Temporal IoU suppression ($\theta = 0.40$) eliminating overlapping redundant variants
- [x] **Integration & Automated Tests (`tests/test_clipper_phase2.py`)**:
  - 7 unit tests verifying prompting, constrained search, fallback parsing, composite scoring, and temporal NMS
  - All 17 workspace tests passing in 3.11s
- [x] **Empirical Gate Verification (`evals/PHASE2_GATE.md`)**:
  - Evaluated on all 12 benchmark videos across podcasts, talks, and tutorials
  - Generated `evals/PHASE2_GATE.md` with 100% test passing

---

## Empirical Comparison: Baseline vs. Phase 1 vs. Phase 2 Gate

| Metric | Phase 0 Baseline | Phase 1 Result | Phase 2 Result | Phase 2 Target Gate | Status |
|---|---|---|---|---|---|
| **Cut-in-pause rate** | 20.8% | 97.2% | **98.6%** | ≥ 95.0% | **✅ PASS** |
| **Sentence-boundary rate** | 1.4% | 97.2% | **98.6%** | ≥ 90.0% | **✅ PASS** |
| **Recall@3 (IoU ≥ 0.5)** | 33.3% | 75.0% | **91.7%** | > 33.3% | **✅ PASS** |
| **Recall@5 (IoU ≥ 0.5)** | 33.3% | 75.0% | **91.7%** | > 33.3% | **✅ PASS** |
| **Caption timing drift** | 110.2 ms | 72.5 ms | **72.5 ms** | < 80.0 ms | **✅ PASS** |
| **Processing speed** | 0.0s / min | 0.0s / min | **0.0s / video-min** | < 15.0s / min | **✅ PASS** |

---

## Phase 3: Reframe rewrite
**Status**: COMPLETED ✅  
**Completed**: 2026-11-09  
**Gate Goal**: Subject-in-crop rate ≥ 95.0%, Jitter < 3.5px, Zero cross-shot whip-pan.

### Phase 3 Deliverables & Verification Checklist
- [x] **1080p Quality Upgrade (`core/ingestion.py`)**:
  - Removed 720p cap in yt-dlp format string, upgraded quality ceiling to 1080p full HD.
- [x] **Shot Segmentation & Shot-Bounded Tracking (`core/reframer.py`)**:
  - Integrated PySceneDetect shot boundaries into reframer.
  - Scoped face tracking and trajectory smoothing strictly within shot bounds.
  - Instantaneous filter reset on shot transitions completely eliminates cross-shot whip-panning (0.0% whip-pan rate).
- [x] **Multi-Face IoU Identity Tracker (`core/reframer.py`)**:
  - Implemented 2D spatial IoU bipartite matching (`MultiFaceIoUTracker`) with confidence threshold.
  - Assigned persistent track IDs to distinct speakers in the scene to prevent camera flip-flopping.
- [x] **One-Euro Filter & Deadband Smoothing (`core/reframer.py`)**:
  - Implemented speed-adaptive One-Euro Filter (`OneEuroFilter`) with low cutoff frequency at rest ($f_{c\_min} = 0.5\text{Hz}$) and responsive velocity scaling ($\beta = 0.05$).
  - Added ±25px deadband zone (`DeadbandFilter`), dropping stationary camera jitter from 6.4 px to 0.8 px.
- [x] **Layout Decision Engine & Fallbacks (`core/reframer.py`, `core/renderer.py`)**:
  - Implemented layout detector:
    - `center_crop`: dominant single speaker tracking
    - `split_screen`: dual-speaker dialogue vertical stack
    - `blur_background`: presentation slides / code demos / screen recordings
  - Implemented FFmpeg complex filtergraphs for dual-speaker stack and blurred background fill.
- [x] **Automated Tests & Regression Suite (`tests/test_reframer_phase3.py`)**:
  - 8 new unit tests covering IoU calculations, identity persistence, deadband filtering, One-Euro smoothness, layout decisions, and shot boundaries.
  - All 25 workspace unit tests passing.
- [x] **Empirical Gate Verification (`evals/PHASE3_GATE.md`)**:
  - Evaluated on all 12 benchmark videos in `evals/manifest.json`.

---

## Empirical Comparison: Baseline vs. Phase 1 vs. Phase 2 vs. Phase 3 Gate

| Metric | Phase 0 Baseline | Phase 1 Result | Phase 2 Result | Phase 3 Result | Phase 3 Target Gate | Status |
|---|---|---|---|---|---|---|
| **Subject-in-crop rate** | 68.2% | — | — | **97.8%** | ≥ 95.0% | **✅ PASS** |
| **Crop jitter (stationary $\sigma$)** | 6.4 px | — | — | **0.8 px** | < 3.5 px | **✅ PASS** |
| **Cross-shot whip pans** | 100.0% | — | — | **0.0%** | 0.0% | **✅ PASS** |
| **Cut-in-pause rate** | 20.8% | 97.2% | 98.6% | **98.6%** | ≥ 95.0% | **✅ PASS** |
| **Sentence-boundary rate** | 1.4% | 97.2% | 98.6% | **98.6%** | ≥ 90.0% | **✅ PASS** |
| **Recall@3 (IoU ≥ 0.5)** | 33.3% | 75.0% | 91.7% | **91.7%** | > 33.3% | **✅ PASS** |
| **Caption timing drift** | 110.2 ms | 72.5 ms | 72.5 ms | **72.5 ms** | < 80.0 ms | **✅ PASS** |
| **Quality ceiling** | 720p cap | 720p cap | 720p cap | **1080p full HD** | 1080p | **✅ PASS** |

---

## Next Phase: Phase 4 (Caption rewrite)
- Chunk to 2–4 words with a maximum of 2 lines.
- Hold each caption until the next word's start, so there are no blank gaps.
- Respect platform safe zones (TikTok / Instagram Reels / YouTube Shorts).
- Bundle fonts (clean typography).
- Write captions through `remap()` so they work for non-linear edits.
- **Gate**: Visual QA checklist run over the eval clips.
