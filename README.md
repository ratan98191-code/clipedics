# 🎬 Clipedics

> **AI-powered video clip generator** — automatically extracts the best viral short-form clips from long videos.
> Inspired by Vizard.ai and Kixy.ai. Built with WhisperX + Gemini 2.5 Flash + FFmpeg.

---

## ✨ Features (Phase 1)

- 📥 **YouTube + Local file** ingestion via `yt-dlp`
- 🎤 **Word-level transcription** via WhisperX (faster-whisper)
- 🤖 **AI clip selection** via Gemini 2.5 Flash — full-context clipping (no mid-thought cuts)
- 📊 **Virality scoring** (1–100) with rationale per clip
- ✂️ **Fast FFmpeg slicing** — stream-copy (no re-encode) for speed
- 💾 **Metadata JSON export** with titles, captions, hashtags per clip

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.11+
- FFmpeg (install via `winget install Gyan.FFmpeg` on Windows)
- A free Gemini API key: https://aistudio.google.com/app/apikey

### 2. Install

```bash
# Clone or navigate to project
cd clipedics

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -e .
```

### 3. Configure

```bash
# Copy the example env file
copy .env.example .env

# Edit .env and add your GEMINI_API_KEY
notepad .env
```

### 4. Run

```bash
# From a YouTube URL
python main.py --input "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"

# From a local video file
python main.py --input path/to/your/video.mp4

# Custom settings
python main.py --input video.mp4 --clips 7 --min 20 --max 60
```

---

## 📂 Project Structure

```
clipedics/
├── core/
│   ├── models.py          # Pydantic data models
│   ├── ingestion.py       # Video download + audio extraction
│   ├── transcriber.py     # WhisperX transcription
│   ├── clipper.py         # Gemini AI clip selection
│   └── slicer.py          # FFmpeg video cutting
├── config/
│   └── settings.py        # Environment config
├── output/                # Generated clips go here
├── temp/                  # Intermediate files
├── main.py                # CLI entry point
├── pyproject.toml         # Package config + dependencies
├── .env.example           # Environment variables template
└── README.md
```

---

## ⚙️ CLI Options

| Flag | Default | Description |
|---|---|---|
| `--input` / `-i` | required | YouTube URL or local file path |
| `--clips` / `-n` | 5 | Number of clips to generate |
| `--min` | 30 | Minimum clip duration (seconds) |
| `--max` | 90 | Maximum clip duration (seconds) |
| `--output` / `-o` | `./output` | Output directory |
| `--transcript` | false | Save full transcript JSON |
| `--whisper-model` | `base` | Whisper model size |

---

## 🗺️ Roadmap

| Phase | Status | Description |
|---|---|---|
| **Phase 1** | ✅ Complete | Core CLI engine |
| **Phase 2** | 🔜 Next | Face tracking + 9:16 reframe + kinetic subtitles |
| **Phase 3** | 📋 Planned | FastAPI backend + Celery job queue |
| **Phase 4** | 📋 Planned | Next.js web dashboard |
| **Phase 5** | 📋 Planned | Billing, social publishing, cloud deployment |

