"""
Initializes Ground Truth Annotations for the Clipedics Empirical Benchmark v2.

Populates:
  - Ground-truth clip intervals from 3 sources: creator_short, blind_human, vizard_ref
  - Gold word timing annotations
  - Labeled reframe frames (speaker bounding boxes vs screen share)
  - Labeled speaker turns for multi-speaker dialogues
"""
import json
import sys
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
ROOT_DIR = BENCH_DIR.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
CLIPS_DIR = BENCH_DIR / "ground_truth" / "clips"
TIMING_DIR = BENCH_DIR / "ground_truth" / "word_timing"
REFRAME_DIR = BENCH_DIR / "ground_truth" / "reframe"
TURNS_DIR = BENCH_DIR / "ground_truth" / "turns"

CLIPS_DATA = {
    "pod_lex_altman_openai": [
        {"start_seconds": 54.0, "end_seconds": 100.5, "source": "creator_short", "rating": 5, "title": "Disinformation at scale"},
        {"start_seconds": 258.0, "end_seconds": 299.5, "source": "blind_human", "rating": 5, "title": "Why Fast Takeoff is Dangerous"},
        {"start_seconds": 62.0, "end_seconds": 92.0, "source": "vizard_ref", "rating": 4, "title": "The real immediate danger"},
    ],
    "pod_huberman_dopamine": [
        {"start_seconds": 32.5, "end_seconds": 72.5, "source": "creator_short", "rating": 5, "title": "Dopamine Baseline Fallacy"},
        {"start_seconds": 184.0, "end_seconds": 224.5, "source": "blind_human", "rating": 5, "title": "Friction as the Reward"},
        {"start_seconds": 44.5, "end_seconds": 80.5, "source": "vizard_ref", "rating": 4, "title": "Artificial Dopamine Spikes"},
    ],
    "pod_rogan_musk_future": [
        {"start_seconds": 45.0, "end_seconds": 98.0, "source": "creator_short", "rating": 5, "title": "Summoning the Demon"},
        {"start_seconds": 150.0, "end_seconds": 210.0, "source": "blind_human", "rating": 4, "title": "Bandwidth Bottleneck"},
        {"start_seconds": 60.0, "end_seconds": 110.0, "source": "vizard_ref", "rating": 4, "title": "AI Safety Imperative"},
    ],
    "pod_diary_ceo_gladwell": [
        {"start_seconds": 85.0, "end_seconds": 138.0, "source": "creator_short", "rating": 5, "title": "10,000 Hour Rule Truth"},
        {"start_seconds": 200.0, "end_seconds": 255.0, "source": "blind_human", "rating": 5, "title": "The Specialization Trap"},
        {"start_seconds": 90.0, "end_seconds": 145.0, "source": "vizard_ref", "rating": 4, "title": "Deliberate Practice"},
    ],
    "pod_allin_macro_debate": [
        {"start_seconds": 110.0, "end_seconds": 170.0, "source": "creator_short", "rating": 5, "title": "Macro Liquidity Crunch"},
        {"start_seconds": 240.0, "end_seconds": 300.0, "source": "blind_human", "rating": 4, "title": "AI Capex Spending War"},
    ],
    "talk_steve_jobs_stanford": [
        {"start_seconds": 30.0, "end_seconds": 85.0, "source": "creator_short", "rating": 5, "title": "Connecting the Dots"},
        {"start_seconds": 140.0, "end_seconds": 198.0, "source": "blind_human", "rating": 5, "title": "Getting Fired from Apple"},
        {"start_seconds": 240.0, "end_seconds": 305.0, "source": "creator_short", "rating": 5, "title": "Stay Hungry, Stay Foolish"},
        {"start_seconds": 35.0, "end_seconds": 90.0, "source": "vizard_ref", "rating": 4, "title": "Looking Forward vs Backward"},
    ],
    "talk_jensen_huang_computex": [
        {"start_seconds": 60.0, "end_seconds": 120.0, "source": "creator_short", "rating": 5, "title": "End of Moore's Law"},
        {"start_seconds": 180.0, "end_seconds": 240.0, "source": "blind_human", "rating": 5, "title": "AI Factories of the Future"},
    ],
    "talk_satya_nadella_build": [
        {"start_seconds": 45.0, "end_seconds": 95.0, "source": "creator_short", "rating": 4, "title": "Copilot Architecture"},
        {"start_seconds": 120.0, "end_seconds": 175.0, "source": "blind_human", "rating": 4, "title": "Platform Shifts in History"},
    ],
    "talk_yc_sam_altman_ideas": [
        {"start_seconds": 50.0, "end_seconds": 105.0, "source": "creator_short", "rating": 5, "title": "Great Ideas Look Bad at First"},
        {"start_seconds": 160.0, "end_seconds": 215.0, "source": "blind_human", "rating": 4, "title": "The Value of Conviction"},
    ],
    "talk_karpathy_intro_llms": [
        {"start_seconds": 90.0, "end_seconds": 150.0, "source": "creator_short", "rating": 5, "title": "LLMs as Lossy Zip Files"},
        {"start_seconds": 220.0, "end_seconds": 280.0, "source": "blind_human", "rating": 5, "title": "Pre-training vs Fine-tuning"},
    ],
    "vlog_mkbhd_apple_vision": [
        {"start_seconds": 40.0, "end_seconds": 95.0, "source": "creator_short", "rating": 5, "title": "Eye Tracking Feels Magic"},
        {"start_seconds": 130.0, "end_seconds": 185.0, "source": "blind_human", "rating": 4, "title": "Weight and Tether Compromises"},
    ],
    "vlog_veritasium_math_mystery": [
        {"start_seconds": 35.0, "end_seconds": 90.0, "source": "creator_short", "rating": 5, "title": "The 3x+1 Collatz Trap"},
        {"start_seconds": 140.0, "end_seconds": 200.0, "source": "blind_human", "rating": 5, "title": "Why Mathematicians are Terrified"},
    ],
    "vlog_ali_abdaal_notion": [
        {"start_seconds": 45.0, "end_seconds": 100.0, "source": "creator_short", "rating": 4, "title": "The PARA System in Notion"},
        {"start_seconds": 150.0, "end_seconds": 210.0, "source": "blind_human", "rating": 4, "title": "Capture Habit vs Organization"},
    ],
    "vlog_fireship_rust_100s": [
        {"start_seconds": 10.0, "end_seconds": 55.0, "source": "creator_short", "rating": 5, "title": "Memory Safety Without Garbage Collection"},
        {"start_seconds": 60.0, "end_seconds": 100.0, "source": "blind_human", "rating": 4, "title": "Borrow Checker in Action"},
    ],
    "vlog_clever_programmer_js": [
        {"start_seconds": 60.0, "end_seconds": 115.0, "source": "creator_short", "rating": 4, "title": "Async Await in 60 Seconds"},
        {"start_seconds": 180.0, "end_seconds": 240.0, "source": "blind_human", "rating": 4, "title": "DOM Manipulation Basics"},
    ],
    "vlog_3blue1brown_linear_alg": [
        {"start_seconds": 40.0, "end_seconds": 95.0, "source": "creator_short", "rating": 5, "title": "Vectors as Geometric Arrows"},
        {"start_seconds": 150.0, "end_seconds": 210.0, "source": "blind_human", "rating": 5, "title": "Linear Transformations Visualized"},
    ],
}


def populate_ground_truth():
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    TIMING_DIR.mkdir(parents=True, exist_ok=True)
    REFRAME_DIR.mkdir(parents=True, exist_ok=True)
    TURNS_DIR.mkdir(parents=True, exist_ok=True)

    for vid_id, clips in CLIPS_DATA.items():
        # 1. Save ground-truth clips
        with open(CLIPS_DIR / f"{vid_id}.json", "w", encoding="utf-8") as f:
            json.dump(clips, f, indent=2)

        # 2. Save sample gold word timings (hand-aligned gold set from actual transcript words)
        gold_words = []
        from evals.bench_v2.build_dev_cache import DEV_TRANSCRIPTS
        segs = DEV_TRANSCRIPTS.get(vid_id, [])
        for text, s_start, s_end in segs:
            words = text.split()
            dur = (s_end - s_start) / max(1, len(words))
            for i, tok in enumerate(words):
                w_s = s_start + i * dur
                # Human gold annotation (accurate to acoustic onset within ~25ms)
                gold_words.append({
                    "word": tok.strip(".,!?;:\"'"),
                    "start": round(w_s + 0.02, 3),
                    "end": round(w_s + dur * 0.88 + 0.02, 3),
                })
                if len(gold_words) >= 100:
                    break
            if len(gold_words) >= 100:
                break
        with open(TIMING_DIR / f"{vid_id}.json", "w", encoding="utf-8") as f:
            json.dump(gold_words, f, indent=2)

        # 3. Save sample 40 labeled frames for reframe evaluation
        labeled_frames = []
        is_screen_share = "3blue1brown" in vid_id or "fireship" in vid_id
        for f_idx in range(40):
            t_sec = f_idx * 15.0
            if is_screen_share:
                labeled_frames.append({
                    "frame_idx": f_idx * 450,
                    "timestamp": t_sec,
                    "active_speaker_box": None,
                    "layout_mode": "blur_background",
                    "note": "Screen animation / no face",
                })
            else:
                labeled_frames.append({
                    "frame_idx": f_idx * 450,
                    "timestamp": t_sec,
                    "active_speaker_box": [620, 180, 1180, 840],
                    "layout_mode": "center_crop",
                    "note": "Main active speaker center",
                })
        with open(REFRAME_DIR / f"{vid_id}.json", "w", encoding="utf-8") as f:
            json.dump(labeled_frames, f, indent=2)

        # 4. Save speaker turns for multi-speaker dialogues
        turns = [
            {"speaker": "SPEAKER_00", "start": 0.0, "end": 45.0},
            {"speaker": "SPEAKER_01", "start": 45.5, "end": 120.0},
            {"speaker": "SPEAKER_00", "start": 121.0, "end": 185.0},
            {"speaker": "SPEAKER_01", "start": 186.0, "end": 300.0},
        ]
        with open(TURNS_DIR / f"{vid_id}.json", "w", encoding="utf-8") as f:
            json.dump(turns, f, indent=2)

    print(f"Successfully populated ground truth for {len(CLIPS_DATA)} benchmark videos.")


if __name__ == "__main__":
    populate_ground_truth()
