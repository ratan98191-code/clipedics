# STATE: Clipedics Development State & Mission Control

> **Methodology**: GSD (Get Shit Done) — Spec-Driven, Context-Engineered  
> **Status**: ACTIVE — Phase 1 runner & Phase 2 architecture bugs resolved & verified  
> **Last Updated**: 2026-11-10

---

## 1. Reality Check & Baseline Reset

An honest code review and audit confirmed:
1. `evals/bench_v2/` synthetic fixtures quarantined to `tests/fixtures/synthetic/`; `cache/` and `ground_truth/` deleted and gitignored.
2. `evals/run.py` metric signatures corrected (`compute_cut_in_silence_rate`, `compute_sentence_boundary_rate`, `measure_word_timing_error`, `compute_recall_and_iou`, `measure_subject_in_crop`, `measure_crop_jitter`); tested via `tests/test_evals_runner.py`.
3. `evals/bench_v2/manifest.json` candidate descriptions clarified and fake sha256 hashes blanked pending real media downloads.
4. Phase 2 architecture verified with unit and golden tests (consecutive rerender persistence, filtergraph cuts, interval-based face detection).

---

## 2. Phase Execution State

| Phase | Description | Status | Gate |
|-------|-------------|--------|------|
| **Phase 1** | **Real Evaluation Harness** | **INCOMPLETE** — runner & metrics verified; awaits download and hand-labeling of >=3 real videos | Real cached transcripts + hand-annotated GT on >=3 real videos |
| **Phase 2** | **Production Architecture Wiring** | **VERIFIED** (7/7 bugs addressed or tracked) | End-to-end run on 3 real dev videos with working editor re-renders |
| Phase 3 | ASR, Alignment & Boundaries | QUEUED | Word timing <60ms, >=95% silence cuts, >=90% sentence bounds |
| Phase 4 | Speaker-Aware Reframing | QUEUED (Bug 5 open) | >=95% active speaker in crop, DER <=15%, 0 whip pans |
| Phase 5 | Selection Quality & Ranking | QUEUED | Recall@5 beats plain-LLM; blind A/B vs Vizard >=45% |
| Phase 6 | Presentation Polish | QUEUED | Visual styling pass across 9:16, 1:1, 16:9 |
| Phase 7 | Feedback Loop & Learned Ranker | QUEUED | Generalization on held-out AUC/Spearman after >=200 ratings |

---

## 3. Bug Tracker & Resolution Log

| # | Bug | Component | Status | Verification |
|---|-----|-----------|--------|--------------|
| 1 | Rerender drops captions | `workers/pipeline.py` | **FIXED** | `words` and `beats` persisted in `clip_plan_json`; tested across 2 consecutive rerenders |
| 2 | Audio dips at every camera cut | `core/renderer.py` | **FIXED** | Fades applied only at non-contiguous timeline gaps (> 1ms); verified with filtergraph golden test |
| 3 | `face_detected` wrongly set | `core/pipeline.py` | **FIXED** | Replaced shot start-key with interval overlap (`max(u.s, sp.s) < min(u.e, sp.e)`); mid-shot test passes |
| 4 | Beat swap speech scramble & task tracking | `api/routers/clips.py` | **FIXED** | Single-beat guard, duplicate & unknown ID validation; task ID surfaced via `ClipRead.task_id` |
| 5 | Crop still static per shot | `core/reframer.py` | OPEN | Phase 4 (per-frame speaker tracking) |
| 6a | `scipy` missing from dependencies | `pyproject.toml` | **FIXED** | Added `scipy>=1.11.0` |
| 6b | `clip_plan_json` without migration | `alembic/versions/` | **FIXED** | Generated & applied Alembic migration `919a20ddaa11`; removed inline migration & `patch_db.py` |
| 7a | Dead flag `enable_narrative` | `core/pipeline.py` | **FIXED** | Guarded with `hasattr(arc, "to_clip_plan_beats")` |
| 7b | Dead flag `enable_cold_open` | `core/pipeline.py` | Guarded | Guarded with `getattr(..., None)` |
| 8 | Uncalibrated feedback score mutation | `api/routers/clips.py` | **FIXED** | Removed `virality_score + 5` mutation on accept |
| 9a | Hardcoded 1080p fallback causes crop failure | `core/pipeline.py` | **FIXED** | `_probe()` runs `ffprobe` upfront for true `src_w, src_h, fps` with cv2 fallback |
| 9b | MediaPipe AttributeError swallowed | `core/reframer.py`, `core/pipeline.py` | **FIXED** | Safe `solutions.face_detection` check; exceptions log traceback with red console alerts |
| 9c | Odd / out-of-bounds crop dimensions | `core/pipeline.py`, `core/renderer.py`, `core/reframer.py` | **FIXED** | Enforced `crop_w = min(int(src_h * 9 / 16), src_w)` and rounded down to even integers (`crop_w - (crop_w % 2)`) |
| 9d | Render failure masked as successful job | `workers/pipeline.py` | **FIXED** | Jobs where 100% of clips fail are marked `error` with the FFmpeg error message; added `libx264` encoder fallback |
| 9e | Windows backslash path break in ClipCard | `frontend/src/components/ClipCard.tsx` | **FIXED** | Normalized backslashes with `.replace(/\\/g, "/")` before splitting `/output/` |

---

## 4. Next Actions (Ordered)

1. **Phase 1 Real Benchmark Collection**:
   - Download 3 real YouTube videos using `yt-dlp`.
   - Extract real 16kHz mono audio via ffmpeg into `evals/bench_v2/cache/<video_id>/audio.wav`.
   - Run faster-whisper on real audio to produce real `transcript.json`.
   - Hand-correct ~100 consecutive words per video in Audacity/Praat for `word_timing/<video_id>.json`.
   - Label 40 frames for active speaker bounding boxes for `reframe/<video_id>.json`.
   - Execute `python evals/run.py` to record the first unvarnished baseline.
2. **Phase 3 (ASR & Alignment)**:
   - Integrate wav2vec2 forced aligner (WhisperX) for sub-60ms word timestamps.
   - Implement `core/boundaries.py` for filler word trimming and referent backward extension.
3. **Phase 4 (Speaker-Aware Reframing)**:
   - Wire per-frame speaker tracking and pyannote diarization (resolving Bug 5).
