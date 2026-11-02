"""
Clipedics – Face Tracker & Auto-Reframer
Tracks the dominant speaker's face across video frames and computes
a smoothed 9:16 crop path for the FFmpeg reframe pipeline.

Key design (reverse-engineered from Vizard.ai):
  - Sample faces at 5 FPS (not every frame) → huge compute saving
  - Smooth the crop X with a moving-average window (prevents jitter)
  - Fallback to center crop when no face is detected
"""
from __future__ import annotations
import subprocess
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

console = Console()

# Target output dimensions for 9:16 vertical
TARGET_W = 1080
TARGET_H = 1920

# Face sampling rate (every N frames)
SAMPLE_EVERY_N_FRAMES = 6  # ~5 FPS if video is 30 FPS

# Smoothing window (frames)
SMOOTH_WINDOW = 45  # ~1.5 seconds at 30 FPS


def compute_crop_path(video_path: Path) -> tuple[list[int], int, int, float]:
    """
    Analyze a video file and return a per-frame crop X path.

    Returns:
        (crop_x_list, src_width, src_height, fps)
        crop_x_list[i] = left-pixel for crop on frame i
    """
    try:
        import cv2
        import mediapipe as mp
    except ImportError:
        raise ImportError(
            "mediapipe and opencv-python-headless are required for face tracking.\n"
            "Run: .venv\\Scripts\\pip.exe install mediapipe opencv-python-headless"
        )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Crop window width for 9:16 from the source height
    crop_w = int(src_h * 9 / 16)
    crop_w = min(crop_w, src_w)  # can't be wider than source
    default_x = max(0, (src_w - crop_w) // 2)

    console.print(
        f"[cyan]👁 Face tracking:[/cyan] {src_w}×{src_h} @ {fps:.1f}fps, "
        f"crop_w={crop_w}px, {total_frames} frames"
    )

    mp_face = mp.solutions.face_detection

    # ── Sample faces at reduced FPS ────────────────────────────────────────
    sampled: dict[int, int] = {}  # frame_idx → center_x

    with mp_face.FaceDetection(
        model_selection=1, min_detection_confidence=0.45
    ) as detector:
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                "Analyzing face positions...", total=total_frames
            )
            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % SAMPLE_EVERY_N_FRAMES == 0:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    result = detector.process(rgb)
                    if result.detections:
                        det = result.detections[0]
                        bbox = det.location_data.relative_bounding_box
                        cx = int((bbox.xmin + bbox.width / 2) * src_w)
                        sampled[frame_idx] = cx
                    else:
                        sampled[frame_idx] = None  # no face detected

                progress.update(task, advance=1)
                frame_idx += 1

    cap.release()

    # ── Interpolate sampled values to every frame ─────────────────────────
    raw_cx = _interpolate(sampled, total_frames, default_x)

    # ── Convert center_x → crop left-edge x ──────────────────────────────
    raw_crop_x = [
        max(0, min(cx - crop_w // 2, src_w - crop_w))
        for cx in raw_cx
    ]

    # ── Smooth with moving average to prevent jitter ──────────────────────
    smooth_x = _moving_average(raw_crop_x, SMOOTH_WINDOW)

    console.print(
        f"[green]✓ Face tracking done:[/green] "
        f"{len(sampled)} samples, crop={crop_w}px wide"
    )

    return smooth_x, src_w, src_h, fps


# ── Private helpers ───────────────────────────────────────────────────────────

def _interpolate(
    sampled: dict[int, int | None],
    total_frames: int,
    default_x: int,
) -> list[int]:
    """
    Fill in face center_x for every frame by linearly interpolating
    between sampled keyframes. Falls back to default_x for no-face gaps.
    """
    result = [default_x] * total_frames

    sample_frames = sorted(sampled.keys())
    if not sample_frames:
        return result

    # Forward fill first sample to start
    first = sample_frames[0]
    fill = sampled[first] if sampled[first] is not None else default_x
    for i in range(first):
        result[i] = fill

    # Interpolate between keyframes
    for i in range(len(sample_frames) - 1):
        fa, fb = sample_frames[i], sample_frames[i + 1]
        va = sampled[fa] if sampled[fa] is not None else default_x
        vb = sampled[fb] if sampled[fb] is not None else default_x
        for f in range(fa, fb):
            t = (f - fa) / max(1, fb - fa)
            result[f] = int(va + t * (vb - va))

    # Forward fill to end
    last = sample_frames[-1]
    fill = sampled[last] if sampled[last] is not None else default_x
    for i in range(last, total_frames):
        result[i] = fill

    return result


def _moving_average(values: list[int], window: int) -> list[int]:
    """Apply a centered moving average to smooth a list of integers."""
    if len(values) == 0:
        return values
    half = window // 2
    n = len(values)
    smoothed = []
    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        smoothed.append(int(sum(values[start:end]) / (end - start)))
    return smoothed

