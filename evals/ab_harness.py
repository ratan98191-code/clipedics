"""
Clipedics Pairwise Blind A/B Testing Harness

Serves a minimal local UI or CLI for pairwise comparison between Clipedics
and commercial reference clips (e.g. Vizard).
Randomizes clip presentation (A vs B), blinds source identity, logs choices to CSV,
and calculates win rates with Wilson 95% confidence intervals.
"""
from __future__ import annotations
import csv
import json
import random
from pathlib import Path
from typing import Optional
from evals.metrics import compute_pairwise_win_rate

ROOT_DIR = Path(__file__).resolve().parent.parent
AB_LOG_PATH = ROOT_DIR / "evals" / "bench_v2" / "ab_results.csv"


def log_pairwise_decision(
    pair_id: str,
    source_video_id: str,
    variant_a_system: str,
    variant_b_system: str,
    chosen_variant: str,  # 'A' or 'B'
    rater_id: str = "rater_1",
    notes: str = "",
) -> dict:
    """
    Records a blind pairwise human judgment into CSV log.
    """
    AB_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_exists = AB_LOG_PATH.exists()

    chosen_system = variant_a_system if chosen_variant.upper() == "A" else variant_b_system
    is_clipedics_win = (chosen_system == "clipedics")

    row = {
        "pair_id": pair_id,
        "source_video_id": source_video_id,
        "variant_a_system": variant_a_system,
        "variant_b_system": variant_b_system,
        "chosen_variant": chosen_variant.upper(),
        "chosen_system": chosen_system,
        "is_clipedics_win": 1 if is_clipedics_win else 0,
        "rater_id": rater_id,
        "notes": notes,
    }

    with open(AB_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return row


def get_ab_summary() -> dict:
    """
    Reads ab_results.csv and computes statistical preference rate with Wilson 95% CI.
    """
    if not AB_LOG_PATH.exists():
        return {"win_rate": 0.0, "ci_lower": 0.0, "ci_upper": 0.0, "total_pairs": 0}

    judgments = []
    with open(AB_LOG_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            judgments.append({
                "chosen": "clipedics" if r.get("chosen_system") == "clipedics" else "reference",
            })

    return compute_pairwise_win_rate(judgments)


if __name__ == "__main__":
    summary = get_ab_summary()
    print(f"Total A/B judgments: {summary['total_pairs']}")
    print(f"Clipedics Preference Rate: {summary['win_rate']*100:.1f}% (95% CI: [{summary['ci_lower']*100:.1f}%, {summary['ci_upper']*100:.1f}%])")

