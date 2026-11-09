# SPEC: Clipedics — Roadmap to Vizard-Level Clip Quality

## 1. Objective & Philosophy
Transform Clipedics into an autonomous, professional-grade AI video clipping studio with empirical parity to market leaders (e.g. Vizard).
Every claim, metric, and quality score must be computed directly from real physical artifacts (audio waveforms, video frames, human ground-truth labels, rendered MP4s).
No synthetic fixtures or hardcoded constants in evaluation reporting. If a metric is not measured from artifacts, it must raise `NotMeasuredError` or report `None`.

---

## 2. Definition of "Vizard Level" (Target Parity)
1. **Head-to-Head Preference**: Blind pairwise A/B testing on identical source videos yields $\ge 45\%$ preference (parity band 45–55%) across 3+ independent raters over $\ge 60$ randomized pairs.
2. **Component Performance Floors**:
   - Cuts in true silence: $\ge 95\%$ (RMS / VAD energy under noise floor for $\ge 150\text{ms}$).
   - Cuts at natural sentence boundary: $\ge 90\%$.
   - Median word timing error: $< 60\text{ms}$ against human gold timing annotations.
   - Active speaker inside crop: $\ge 95\%$ of labeled frames.
   - Recall@5 vs human picks ($\text{IoU} \ge 0.5$): statistically significant gain over plain-LLM baseline.
   - Zero mid-sentence truncations or dangling contextual references ("as I said earlier").
3. **Operational Reality**: $\le 1.0\times$ realtime wall-clock processing for 60-minute inputs on local GPU/CPU hardware.

---

## 3. Master Phase Roadmap

| Phase | Title | Size | Focus | Gate |
|---|---|---|---|---|
| **Phase 1** | **Real Evaluation Harness** | M | Clean synthetic fixtures, 24-video benchmark (`evals/bench_v2/`), ground truth, artifact-computed metrics, real baselines | `python evals/run.py --split dev` produces full artifact-backed report for baselines |
| **Phase 2** | **Production Architecture Wiring** | M | Shared `core/pipeline.py`, audio-backed units, piecewise per-shot reframe, ClipPlan rendering, real editor re-renders | Dev split renders with per-shot layouts, loudnorm, captions; editor produces real MP4s |
| **Phase 3** | **ASR, Alignment & Boundaries** | M | WhisperX forced alignment, Silero VAD, pyannote diarization, boundary refinement & stand-alone check | Word timing error $<60\text{ms}$, $\ge 95\%$ cuts in silence, $\ge 90\%$ sentence boundaries |
| **Phase 4** | **Speaker-Aware Reframing** | L | Robust face detection, identity tracking across cuts, audio-visual active speaker detection, multi-speaker layout engine | Active speaker in crop $\ge 95\%$, DER $\le 15\%$, 0 cross-shot whip pans |
| **Phase 5** | **Selection Quality & Ranking** | L | Video outline context, multi-signal candidate generation, global listwise/pairwise LLM ranker, audio/text signals | Recall@5 beats plain-LLM baseline; blind A/B vs Vizard $\ge 45\%$ |
| **Phase 6** | **Presentation Polish** | S | Safe-zone dynamic subtitles, keyword styling, headline overlays, aspect-ratio options (9:16, 1:1, 16:9) | Visual checklist pass across all aspect ratios |
| **Phase 7** | **Feedback Loop & Learned Ranker** | Ongoing | 7-feature extraction on real interactions, retrainable L2 Ridge/Ranker on $\ge 200$ human judgments | Generalization on held-out AUC/Spearman correlation |

---

## 4. Phase 1 Detailed Specification: Real Evaluation Harness

### 4.1 Synthetic Fixture Quarantine
- Move `evals/build_cache.py` synthetic dictionaries and `evals/cache/*` to `tests/fixtures/synthetic/` for unit-level parser tests.
- Remove all artificial constants (`0.978`, `6.4`, `0.884`, etc.) from `evals/evaluate.py`.
- Delete heuristic caption timing formula (`median * 180`).
- Mark all unmeasured metrics explicitly.

### 4.2 Benchmark Dataset (`evals/bench_v2/manifest.json`)
- 24 curated real-world videos across 3 domains (15–60 min each):
  - 8 Podcasts / Multi-speaker interviews
  - 8 Talks / Keynotes with presentation slides
  - 8 Tutorials / Vlogs / Technical screen shares
- Split: 16 Dev (open evaluation & tuning), 8 Test (held-out blind evaluation).

### 4.3 Ground Truth Annotations
- **Clip Intervals**: Union of published Shorts/Reels, author blind human picks (1–5 scale), and Vizard free-tier references.
- **Gold Word Timings**: Hand-aligned $\sim 100$ word segments per video.
- **Reframe Ground Truth**: 40 randomly sampled frames per video annotated with active speaker bounding box $[x_1, y_1, x_2, y_2]$ or `"screen_share"`.
- **Speaker Turns**: 5 minutes of verified speaker turn diarization for multi-speaker videos.

### 4.4 Real Metric Computation (`evals/metrics.py`)
- `measure_boundary_silence(cut_timestamp, audio_samples, sample_rate, window_ms=150)`: Computes RMS around cut vs global noise floor.
- `measure_sentence_boundary(cut_timestamp, transcript)`: Evaluates terminal punctuation (`.`, `!`, `?`) and pause duration from aligned words.
- `measure_word_timing_error(predicted_words, gold_words)`: Computes median and p90 timing deltas in milliseconds.
- `measure_temporal_iou_and_recall(candidates, ground_truth_clips, k=5, iou_thresh=0.5)`: Real IoU and Recall@k.
- `measure_subject_in_crop(crop_boxes, gold_boxes)`: Exact bounding-box containment ratio.
- `measure_crop_jitter(crop_path)`: Standard deviation of frame-to-frame velocity during stationary shots.
- `measure_pipeline_performance(runtime_stats)`: Wall-clock seconds per video-minute and token consumption.

---

## 5. Phase 2 Detailed Specification: Production Architecture Wiring

### 5.1 Shared Pipeline Core (`core/pipeline.py`)
Unifies CLI (`main.py`) and background worker (`workers/pipeline.py`):
`ingest -> audio -> asr -> units(+audio) -> features -> select -> plan -> reframe -> render`.
Eliminates duplicated code and cross-imports (`from main import _get_clip_segments`).

### 5.2 Real Audio in Units & Features
- Load 16kHz mono audio into numpy float array.
- Pass `audio_samples` to `build_units_from_transcript` to trigger true RMS valley snapping.
- Populate `Unit.face_detected` and `dominant_face_x` from face tracking data.

### 5.3 Piecewise Per-Shot Reframe
- `compute_crop_path` returns `ShotReframePlan` (per-shot layout: `center_crop`, `split_screen`, `blur_background`, active speaker track).
- Renderer crops video per shot according to the plan rather than flattening to a single global average.

### 5.4 ClipPlan Non-Linear Rendering
- Every clip renders through the unified `ClipPlan` engine with 30ms anti-click audio crossfades and loudnorm (`-16 LUFS`).
- Persist `ClipPlan` JSON in database `Clip` record for fast re-rendering.

### 5.5 Working Editor Endpoints
- `POST /api/clips/{id}/trim`: Snaps new bounds to RMS valleys, updates `ClipPlan`, enqueues Celery render job.
- `POST /api/clips/{id}/swap-beats`: Reorders plan timeline, enqueues Celery render job.
- `POST /api/clips/{id}/rerender`: Re-renders with updated style presets using cached assets.
