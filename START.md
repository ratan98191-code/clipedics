# 🎬 Clipedics — Personal AI Video Studio Guide

Clipedics is configured as your **personal AI video clipping studio** — frictionless, single-user, without login gates, subscription paywalls, or artificial quotas.

---

## ⚡ Quick Start (One-Click Launcher)

Double-click `start_clipedics.bat` in the project root, or run:
```powershell
.\start_clipedics.bat
```
This automatically verifies Redis, starts the FastAPI backend, Celery worker, and Next.js frontend in separate terminal windows, and opens **http://localhost:3000** in your browser.

To stop all services:
```powershell
.\stop_clipedics.bat
```

---

## 1. Environment variables

Your Groq API key is configured in `.env` (`LLM_PROVIDER=groq`, `GROQ_MODEL=qwen/qwen3.8-27b`).
You get **14,400 free requests per day** with instant 1-second responses.

Standard settings in `.env`:
```env
# AI Provider (active: Groq)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=qwen/qwen3.8-27b

# Local SQLite Database
DATABASE_URL=sqlite+aiosqlite:///./clipedics.db

# Redis / Celery Pipeline
REDIS_URL=redis://localhost:6379/0

# Faster-Whisper Model (base, small, medium, large-v3)
WHISPER_MODEL=base
WHISPER_DEVICE=cpu

# Output Directory
OUTPUT_DIR=./output
```

---

## 2. Start Redis (Celery broker)

**Option A — Docker (easiest):**
```powershell
docker compose up redis -d
```

**Option B — winget:**
```powershell
winget install Redis.Redis
redis-server
```

---

## 3. Start the FastAPI Backend

```powershell
cd c:\Users\ratan\OneDrive\Desktop\clipedics
.venv\Scripts\uvicorn.exe api.main:app --reload --port 8000
```

→ API docs: **http://localhost:8000/docs**

---

## 4. Start the Celery Worker

```powershell
cd c:\Users\ratan\OneDrive\Desktop\clipedics
.venv\Scripts\celery.exe -A workers.celery_app worker --loglevel=info --pool=solo
```

---

## 5. Start the Next.js Frontend

```powershell
cd c:\Users\ratan\OneDrive\Desktop\clipedics\frontend
npm run dev
```

→ App: **http://localhost:3000**

---

## 6. Or: Run everything with Docker

```powershell
docker compose up
```

---

## 7. CLI (no API needed)

```powershell
cd c:\Users\ratan\OneDrive\Desktop\clipedics
.venv\Scripts\python.exe main.py `
  --input "https://www.youtube.com/watch?v=VIDEO_ID" `
  --clips 5 --min 30 --max 90 `
  --style hormozi
```

Output → `output\<job_id>\`

---

## System Architecture (Personal Studio)

```
Browser :3000         (Next.js Personal UI & Interactive Clip Editor)
    ↓
API :8000            (FastAPI Backend)
    ├── /api/projects        → create, list, get, delete
    ├── /api/clips           → get, trim, swap beats, re-render, download MP4
    ├── /api/clips/feedback  → log thumbs up/down, star rating
    ├── /api/clips/ranker    → train & status for learned ridge ranker
    ├── /api/jobs            → real-time progress stream (SSE)
    └── /api/system          → local engine status & config
    ↓
Celery Worker        (Background Worker)
    └── run_pipeline → yt-dlp → WhisperX → Unit Splitting (RMS Snapping)
                     → Groq AI → 4-Part Narrative Beam Search (Faithfulness Gate)
                     → Multi-Face IoU Tracker → FFmpeg filter_complex EDL Assembly
                     → Micro-Chunk Subtitles (Safe Zones)
    ↓
SQLite DB / JSON     (clipedics.db, data/feedback_logs.json, data/learned_ranker.json)
output/              (rendered vertical MP4 clips)
```

---

## Direct Personal Use Features

- **No login or account needed**: Open http://localhost:3000 and immediately generate clips.
- **Unlimited generation**: No billing barriers, plan upgrades, or quota throttles.
- **High-speed clipping**: Groq LPU with Qwen 2.5 32B / Llama 3.3 models.
- **Interactive Single-User Studio**: Real-time clip boundary trimming, 4-beat narrative re-ordering, subtitle styling (`hormozi`, `beast`, `neon`), and instant re-rendering.
- **Learned Ranker & Editorial Feedback**: Thumbs up/down and 1–5 star ratings dynamically train an internal L2 Ridge Regression model tailored to your viral clip preferences.
- **Local privacy**: All videos, transcripts, and database records remain on your local machine.
