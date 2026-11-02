"""
Clipedics – Configuration & Settings
Loads all environment variables with sensible defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Ensure FFmpeg and Python Scripts in PATH ─────────────────────────────────
def _ensure_binaries_in_path():
    import shutil
    import sys

    # Add venv Scripts directory to PATH
    scripts_dir = str(Path(sys.executable).parent)
    if scripts_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = scripts_dir + os.pathsep + os.environ.get("PATH", "")

    if shutil.which("ffmpeg"):
        return
    # Check winget default install location on Windows
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        winget_pkgs = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_pkgs.exists():
            for p in winget_pkgs.glob("**/ffmpeg.exe"):
                bin_dir = str(p.parent)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                return

_ensure_binaries_in_path()

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output"))
# Use local AppData temp directory on Windows to avoid OneDrive file-locking & syncing
_default_temp = Path(os.getenv("LOCALAPPDATA", str(BASE_DIR))) / "clipedics" / "temp"
TEMP_DIR = Path(os.getenv("TEMP_DIR", _default_temp))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ── LLM & AI Providers ───────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").lower()

# Groq (Recommended: 14,400 free requests/day, Llama 3.3 70B)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

# Google Gemini (Alternative)
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Ollama (Local offline)
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

# ── Whisper / Transcription ───────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE: str = "float16" if WHISPER_DEVICE == "cuda" else "int8"
WHISPER_BATCH_SIZE: int = 16 if WHISPER_DEVICE == "cuda" else 4

# ── Clipping ──────────────────────────────────────────────────────────────────
TARGET_CLIPS: int = int(os.getenv("TARGET_CLIPS", 5))
CLIP_MIN_SECONDS: int = int(os.getenv("CLIP_MIN_SECONDS", 30))
CLIP_MAX_SECONDS: int = int(os.getenv("CLIP_MAX_SECONDS", 90))

