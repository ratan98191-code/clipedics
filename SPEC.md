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

---

## Phase 2 Specification: Better Contiguous Clips

### 1. Numbered Unit-ID Prompting & Parsing
- Format transcript for LLM context as numbered atomic blocks:
  `[Unit {id}] ({duration}s): {text}`
- Prompt instructs LLM to select:
  - `start_unit_id`: integer
  - `end_unit_id`: integer
  - Strict prohibition against hallucinating or outputting raw timestamps.
- Clip boundaries resolve deterministically to `units[start_unit_id].start_seconds` and `units[end_unit_id].end_seconds`.

### 2. Boundary Constrained Search
- Ensure `end_unit_id >= start_unit_id`.
- Enforce `[min_seconds, max_seconds]` duration constraints:
  - If duration < `min_seconds`: expand unit boundary forward to the next natural pause/sentence.
  - If duration > `max_seconds`: trim unit boundary backward to the nearest complete thought ending.

### 3. Multi-Modal Composite Scoring
- Rank candidates by combining LLM salience with extracted physical features:
  $$Score = 0.50 \cdot S_{LLM} + 0.20 \cdot S_{Audio} + 0.15 \cdot S_{Visual} + 0.15 \cdot S_{Hook}$$
  - $S_{Audio}$: Loudness consistency and speech rate pacing.
  - $S_{Visual}$: Face presence ratio and camera shot transitions.
  - $S_{Hook}$: Impact of opening unit (punchy duration, no trailing pause).

### 4. Temporal Non-Maximum Suppression (NMS)
- Pool candidates across transcript windows.
- Suppress overlapping candidates with temporal $\text{IoU} \ge 0.40$.
- Select top-$K$ non-redundant clips globally.

### 5. Phase 2 Gate
- Run evaluation across 12 benchmark videos:
  - Recall@3 and Recall@5 beat Phase 0 baseline (33.3%).
  - Cut-in-pause rate $\ge 95.0\%$.
  - Results recorded in `evals/PHASE2_GATE.md`.

---

## Phase 3 Specification: Reframe Rewrite

### 1. 1080p Quality Ceiling Upgrade
- Remove 720p cap in `core/ingestion.py`. Set format string to `height<=1080`.
- Maintain full 1080×1920 (9:16 vertical) output resolution across rendering pipeline.

### 2. Shot-Aware Video Segmentation
- Video temporal segmentation via PySceneDetect (`detect_shot_boundaries`).
- All tracking, identity assignment, and smoothing are strictly scoped to individual shots $[t_{start}, t_{end}]$.
- Resets tracking and filter state on shot cuts to completely eliminate cross-shot whip-panning and drunken camera slides.

### 3. Multi-Face Identity Tracker (IoU Tracker)
- Frame-level multi-face detection using MediaPipe Face Detection.
- Maintain tracks across frames using 2D spatial IoU bipartite matching with confidence threshold:
  $$\text{IoU}(B_{det}, B_{track}) \ge 0.30$$
- Persistent `track_id` assigned to each speaker across the shot duration.

### 4. Active Speaker & Layout Decision Engine
- Evaluate frame layout per shot based on face count, bounding box size, and speech activity:
  1. **Single Dominant Speaker (`center_crop`)**:
     - Track active speaker's center $x$. Frame smoothly re-centered on the speaker.
  2. **Dual-Speaker Interview / Dialogue (`split_screen`)**:
     - When two prominent face tracks are detected simultaneously (e.g. host & guest in 2-shot).
     - Render dual vertical stack (top half speaker 1, bottom half speaker 2) or active switch.
  3. **No Face / Screen Share / Presentation (`blur_background`)**:
     - When no faces are detected (tutorials, code demos, presentation slides).
     - Scale 16:9 content to 1080px width centered in 1080×1920 frame, with blurred background fill on top and bottom margins.

### 5. Shot-Bounded One-Euro Filter & Deadband Smoothing
- **Deadband**: A threshold zone ($\pm 25\text{px}$) where minor head movements do not alter the camera crop $\rightarrow$ eliminates stationary camera jitter.
- **One-Euro Filter**: Dynamic cutoff frequency $f_c = f_{c\_min} + \beta \cdot |\dot{x}|$:
  - When stationary ($|\dot{x}| \approx 0$): low cutoff frequency ($f_{c\_min} = 0.5\text{Hz}$) filters out sensor noise.
  - When moving ($|\dot{x}| > 0$): cutoff frequency scales with speed ($\beta = 0.05$) to eliminate tracking latency.
- Instantaneous reset at shot cuts ensures instantaneous camera transitions.

### 6. Phase 3 Gate Metrics
- **Subject-in-Crop Rate**: $\ge 95.0\%$ of face frames have the active speaker's face bounding box fully within the 9:16 crop window.
- **Crop Jitter Threshold**: Standard deviation of stationary crop displacement $\sigma(\Delta crop\_x) < 3.5\text{px}$.
- **Zero Cross-Shot Whip-Pan**: $100\%$ of shot cuts have zero gradual smoothing transitions across boundaries.
- Gate report saved to `evals/PHASE3_GATE.md`.

---

## Phase 4 Specification: Caption Rewrite

### 1. 2–4 Word Micro-Chunking with Max 2 Lines
- Segment words into 2 to 4 word chunks based on speech pacing and punctuation boundaries.
- Maximum 2 lines per display chunk; short 2-3 word chunks display on 1 line, longer 4-word phrases wrap cleanly using `\N`.
- Natural breaks forced on commas, periods, question marks, and exclamation marks.

### 2. Zero-Gap Hold Protocol
- Each word/chunk presentation window is held until the exact start timestamp of the next spoken word ($t_{hold} = t_{next\_word.start}$).
- If pause between words $> 1.5\text{s}$ (inter-topic silence), release caption after $t_{word.end} + 0.35\text{s}$.
- Completely eliminates subtitle flickering and black screen blinks between words.

### 3. Platform Safe Zones (TikTok, Instagram Reels, YouTube Shorts)
- Target canvas: 1080×1920 (9:16 vertical).
- Safe Vertical Placement: `MarginV = 420px` (or $Y \approx 1350\text{px}$).
- Avoids obstruction by:
  - Bottom controls: profile handle, sound title, description, and navigation ($Y \in [1500, 1920]$).
  - Right-rail engagement buttons: like, comment, bookmark, share ($X \in [960, 1080]$).
  - Top header: status bar, search bar, and notch ($Y \in [0, 240]$).
- Text width constrained with `MarginL = 80px` and `MarginR = 120px`.

### 4. Piecewise `remap()` Engine for Non-Linear Edits
- Function `remap_words(words: list[WordSegment], cuts: list[tuple[float, float]]) -> list[WordSegment]`:
  - Translates source timestamps $(src\_start, src\_end)$ to contiguous timeline $(0.0, target\_end)$ across non-linear EDL cuts.
  - Guarantees seamless synchronization for Phase 5 cold opens and Phase 6 narrative planners.

### 5. Font Bundling & High-Impact Styling
- Font stack with universal fallback: `Impact`, `Arial Black`, `Montserrat`, `sans-serif`.
- Scale-pop karaoke animation (`\fscx115\fscy115`) on the currently spoken word with glowing primary highlight.
- Context words displayed with muted contrast.

### 6. Phase 4 Gate Metrics & Visual QA
- Chunk word count: strictly $2 \le N \le 4$ words.
- Max lines per chunk: $\le 2$ lines.
- Safe zone compliance: $100.0\%$ inside $[Y_{min}=250, Y_{max}=1500]$.
- Inter-word blank gap duration: $0.0\text{s}$ (Zero gap hold).
- Non-linear remap synchronization error: $< 1$ frame ($< 33.3\text{ms}$).
- Verification recorded in `evals/PHASE4_GATE.md`.

---

## Phase 5 Specification: EDL Data Model & Non-Linear Renderer

### 1. Edit Decision List (EDL) Data Model
- **`Beat`**: Atomic unit of non-linear editing:
  - `beat_id`: Sequential index (1, 2, 3...)
  - `role`: Narrative function (`"cold_open"`, `"hook"`, `"build"`, `"peak"`, `"cliffhanger"`, `"body"`)
  - `unit_ids`: List of atomic Unit IDs composing this beat
  - `src_start`, `src_end`: Source video timestamps
  - `target_start`, `target_end`: Presentation timeline timestamps
  - `layout_mode`: `"center_crop"` | `"split_screen"` | `"blur_background"`
  - `crop_x`: Left crop pixel coordinate for the beat
- **`ClipPlan`**: Full non-linear edit plan:
  - Ordered sequence of `beats`
  - Computed non-linear cuts: `[(beat.src_start, beat.src_end), ...]`
  - Metadata: `virality_score`, `virality_rationale`, `hook_sentence`, `suggested_caption`, `hashtags`
  - Format variant: `"cold_open"` | `"contiguous"` | `"trailer"`

### 2. Cold Open Variant Generator
- Identifies the highest salience curiosity/hook statement from the candidate unit pool.
- Front-loads this peak statement as Beat 1 (Cold Open: 3–6s) before transitioning to the narrative body.
- If the strongest line is already at the beginning of the clip, keeps the body contiguous without redundant duplication.

### 3. Non-Linear FFmpeg Filtergraph Engine
- **Multi-Trim Execution**:
  - Video stream trim: `[0:v]trim=start=src_start:end=src_end,setpts=PTS-STARTPTS[v_raw_i]`
  - Audio stream trim: `[0:a]atrim=start=src_start:end=src_end,asetpts=PTS-STARTPTS[a_raw_i]`
- **Anti-Click Audio Crossfading**:
  - Applies 30ms micro-fade (`afade=t=in:ss=0:d=0.03,afade=t=out:st={dur-0.03}:d=0.03`) at cut boundaries.
  - Completely eliminates audio popping and speaker phase discontinuities.
- **Concat Filter**:
  - `[v0][a0][v1][a1]...concat=n={N}:v=1:a=1[v_concat][a_concat]` seamlessly merges segments.
- **Broadcast Loudness Normalization**:
  - `loudnorm=I=-16:TP=-1.5:LRA=11` standardizes loudness to -16 LUFS broadcast target.

### 4. Piecewise Subtitle & Crop Remapping
- **Caption Remapping**: `remap_words(words, cuts)` translates word boundaries to contiguous presentation time.
- **Crop Remapping**: `remap_crop_path(crop_path, cuts, fps)` samples source frames per cut into a contiguous crop array.

### 5. Phase 5 Gate Metrics
- **Audio Click / Pop Rate**: 0.0% (Zero audible clicks; waveform discontinuity $\Delta A < 0.05$).
- **Caption Synchronization Drift**: $< 1$ frame ($< 33.3\text{ms}$).
- **Cold Open Human A/B Win Rate**: $\ge 80.0\%$ preference over contiguous cuts on high-salience moments.
- **Report**: Recorded in `evals/PHASE5_GATE.md`.




