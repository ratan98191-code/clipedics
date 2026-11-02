# 🎬 Clipedics — Complete Start Guide

All 5 phases are **DONE**.

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

Your Groq API key is already configured in `.env` (`LLM_PROVIDER=groq`, `GROQ_MODEL=qwen/qwen3.8-27b`).
You get **14,400 free requests per day** with instant 1-second responses.

Optional additional settings in `.env`:
```env
# AI Provider (currently active: Groq)
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=qwen/qwen3.8-27b

# Auth secret (already set)
JWT_SECRET=clipedics-secret-key-super-secure-2026-production

# Required for Stripe (get from dashboard.stripe.com)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_AGENCY=price_...

# Optional: social publishing OAuth keys
YOUTUBE_CLIENT_ID=...
TIKTOK_CLIENT_KEY=...
META_APP_ID=...

# Optional: S3 storage (uses local disk by default)
USE_S3=false
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

## Full System Map

```
Browser :3000         (Next.js)
    ↓
API :8000            (FastAPI)
    ├── /api/auth    → register, login, JWT
    ├── /api/projects → create, list, get
    ├── /api/clips   → get, update, download
    ├── /api/jobs    → SSE progress stream
    ├── /api/billing → Stripe plans/checkout/webhook
    └── /api/social  → YouTube/TikTok/Instagram OAuth + publish
    ↓
Celery Worker        (Redis broker)
    ├── run_pipeline → Whisper → Gemini → FFmpeg → SQLite
    └── publish_to_platform → YouTube / TikTok / Instagram
    ↓
SQLite DB            (clipedics.db)
output/              (rendered MP4s)
```

---

## Phase Completion

| Phase | Description | Status |
|---|---|---|
| 1 | CLI — ingest → Whisper → Gemini AI clip → FFmpeg slice | ✅ |
| 2 | Auto-reframe 9:16 + MediaPipe face tracking + ASS karaoke subtitles | ✅ |
| 3 | FastAPI REST API + Celery + SQLite + SSE job stream | ✅ |
| 4 | Next.js dashboard — upload, live progress, clip viewer, edit/download | ✅ |
| 5 | Auth (JWT), Stripe billing, S3 storage, social publish, GitHub Actions CI/CD | ✅ |

---

## What's needed to go live

| Item | What to do |
|---|---|
| Gemini API key | `GEMINI_API_KEY=` in `.env` |
| Stripe account | Create products → copy Price IDs to `.env` |
| Domain + server | Deploy with `docker compose up` on any VPS |
| S3 bucket (optional) | Set `USE_S3=true` + AWS keys in `.env` |
| Social OAuth apps | Register apps on YouTube/TikTok/Meta developer portals |
