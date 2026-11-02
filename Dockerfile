FROM python:3.12-slim

# System dependencies (FFmpeg, build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    yt-dlp ffmpeg-python future pydantic python-dotenv rich typer \
    httpx google-genai faster-whisper mediapipe opencv-python-headless \
    fastapi "uvicorn[standard]" celery redis sqlalchemy alembic \
    aiosqlite python-multipart aiofiles

# Copy source
COPY . .

EXPOSE 8000

