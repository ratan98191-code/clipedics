"""
Clipedics Feature & Unit Cache Ledger (Phase 1)

Persists and reloads per-video atomic units and multi-modal feature matrices as JSON/parquet.
Eliminates redundant GPU/CPU recomputation across pipeline runs and evaluations.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

from core.models import Unit

DEFAULT_CACHE_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "clipedics" / "cache" / "units"
LOCAL_CACHE_DIR = Path(__file__).parent.parent / "evals" / "cache" / "units"


def get_cache_path(video_id: str, custom_dir: Optional[Path] = None) -> Path:
    base_dir = custom_dir or LOCAL_CACHE_DIR
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f"{video_id}_units.json"


def save_units_cache(video_id: str, units: list[Unit], cache_dir: Optional[Path] = None) -> Path:
    """Save extracted units with features to persistent JSON cache."""
    out_path = get_cache_path(video_id, cache_dir)
    data = [u.model_dump() for u in units]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out_path


def load_units_cache(video_id: str, cache_dir: Optional[Path] = None) -> Optional[list[Unit]]:
    """Load units from persistent cache if available, else None."""
    path = get_cache_path(video_id, cache_dir)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [Unit.model_validate(item) for item in data]
    except Exception:
        return None
