# Clipedics Benchmark v2 — Real Data Guide

This directory holds the evaluation dataset for Clipedics.

> **No synthetic data lives here.** The `cache/` and `ground_truth/` directories
> must be populated from real video processing. They are listed in `.gitignore`
> and must never be committed.

---

## Directory Layout

```
bench_v2/
  manifest.json          — 24 video metadata entries (URLs, splits, genre)
  cache/
    <video_id>/
      audio.wav          — 16 kHz mono WAV extracted from the real video
      transcript.json    — faster-whisper ASR output (or hand-corrected)
      crop_path.json     — per-frame crop-x list from compute_crop_path()
  ground_truth/
    clips/<video_id>.json       — hand-labelled clip intervals [{start, end, label}]
    word_timing/<video_id>.json — hand-corrected word timestamps (>=100 words)
    reframe/<video_id>.json     — manually annotated face bboxes (>=40 frames)
    turns/<video_id>.json       — speaker diarization turns [{start, end, speaker}]
```

---

## Step-by-Step: Generating Real Cache Data

Pick any 3+ videos from the dev split in `manifest.json` and run:

```bash
# 1. Download video
yt-dlp -o "tmp/%(id)s.%(ext)s" "<youtube_url>"

# 2. Extract 16kHz mono audio
ffmpeg -i tmp/<file>.mp4 -ar 16000 -ac 1 evals/bench_v2/cache/<video_id>/audio.wav

# 3. Run faster-whisper to get transcript with word timestamps
python - <<'EOF'
from faster_whisper import WhisperModel
import json, pathlib
model = WhisperModel("base.en")
segs, info = model.transcribe(
    "evals/bench_v2/cache/<video_id>/audio.wav",
    word_timestamps=True,
)
out = {"language": info.language, "duration_seconds": info.duration, "segments": []}
for s in segs:
    out["segments"].append({
        "start": s.start, "end": s.end, "text": s.text,
        "words": [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])]
    })
pathlib.Path("evals/bench_v2/cache/<video_id>/transcript.json").write_text(
    json.dumps(out, indent=2), encoding="utf-8"
)
EOF

# 4. Run the reframer to get crop_path.json
python - <<'EOF'
from core.reframer import compute_crop_path
import json, pathlib
crop, w, h, fps, _ = compute_crop_path(pathlib.Path("tmp/<file>.mp4"))
pathlib.Path("evals/bench_v2/cache/<video_id>/crop_path.json").write_text(
    json.dumps(crop), encoding="utf-8"
)
EOF
```

---

## Step-by-Step: Hand-Annotating Ground Truth

### Ground-truth clips (`ground_truth/clips/<video_id>.json`)

Watch the video and identify 3–5 high-quality viral clip segments:
```json
[
  {"start": 142.5, "end": 187.2, "label": "key insight on dopamine"},
  {"start": 310.0, "end": 345.8, "label": "actionable takeaway"}
]
```

### Word timing (`ground_truth/word_timing/<video_id>.json`)

Pick 100+ consecutive words from the transcript and correct their timestamps
using a waveform editor (e.g., Audacity):
```json
[
  {"word": "dopamine", "start": 23.41, "end": 23.78},
  {"word": "is", "start": 23.80, "end": 23.88}
]
```

### Reframe labels (`ground_truth/reframe/<video_id>.json`)

Sample 40+ frames uniformly across the video.  For each frame annotate the
active speaker's face bounding box:
```json
[
  {"frame": 450, "time_s": 15.0, "face_x1": 820, "face_y1": 120, "face_x2": 1100, "face_y2": 480},
  {"frame": 900, "time_s": 30.0, "face_x1": 810, "face_y1": 115, "face_x2": 1095, "face_y2": 475}
]
```

---

## Running the Evaluator

```bash
# Evaluate all dev videos that have cache data
python evals/run.py

# Single video
python evals/run.py --video pod_lex_altman_openai

# Write markdown report (raw numbers only — no auto-generated analysis)
python evals/run.py --report evals/BASELINE_V3.md
```

The runner skips any video whose `transcript.json` is missing and reports `N/A`
for metrics whose ground-truth file is absent.  It never fabricates numbers.
