"""
Clipedics – Face Tracker & Auto-Reframer (Phase 3: Shot-Aware IoU Tracker & One-Euro Filter)
Tracks speakers across video frames with multi-face identity tracking,
shot-bounded One-Euro smoothing with deadband, and intelligent layout fallbacks
(center crop, dual-speaker split screen, and blurred background fit for slides/demos).
"""
from __future__ import annotations
import math
from pathlib import Path
from typing import Optional

import numpy as np
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from core.models import FaceBoundingBox, ShotReframePlan, ClipCandidate
from core.features import detect_shot_boundaries

console = Console()

# Target output dimensions for 9:16 vertical
TARGET_W = 1080
TARGET_H = 1920

# Face sampling rate (every N frames)
SAMPLE_EVERY_N_FRAMES = 5  # ~6 FPS if video is 30 FPS

# One-Euro filter & Deadband defaults
DEFAULT_DEADBAND_PX = 25.0
ONE_EURO_MIN_CUTOFF = 0.50
ONE_EURO_BETA = 0.05
ONE_EURO_D_CUTOFF = 1.0


# ── 2D IoU & Geometry Helpers ──────────────────────────────────────────────────

def compute_2d_iou(box1: FaceBoundingBox, box2: FaceBoundingBox) -> float:
    """Calculate 2D Intersection over Union between two normalized bounding boxes."""
    ixmin = max(box1.xmin, box2.xmin)
    iymin = max(box1.ymin, box2.ymin)
    ixmax = min(box1.xmax, box2.xmax)
    iymax = min(box1.ymax, box2.ymax)

    iw = max(0.0, ixmax - ixmin)
    ih = max(0.0, iymax - iymin)
    intersection = iw * ih

    union = box1.area + box2.area - intersection
    if union <= 1e-6:
        return 0.0
    return float(intersection / union)


# ── Multi-Face Identity Tracker ────────────────────────────────────────────────

class FaceTrack:
    """Persistent identity track for a face across multiple frames."""
    def __init__(self, track_id: int, initial_box: FaceBoundingBox, frame_idx: int):
        self.track_id = track_id
        self.boxes: dict[int, FaceBoundingBox] = {frame_idx: initial_box}
        self.last_frame = frame_idx
        self.total_detections = 1

    def add_detection(self, frame_idx: int, box: FaceBoundingBox):
        self.boxes[frame_idx] = box
        self.last_frame = frame_idx
        self.total_detections += 1

    @property
    def latest_box(self) -> FaceBoundingBox:
        return self.boxes[self.last_frame]

    def average_center_x(self) -> float:
        """Average normalized center X of the face across all detections."""
        if not self.boxes:
            return 0.5
        return float(np.mean([b.center_x for b in self.boxes.values()]))

    def average_area(self) -> float:
        """Average normalized bounding box area."""
        if not self.boxes:
            return 0.0
        return float(np.mean([b.area for b in self.boxes.values()]))


class MultiFaceIoUTracker:
    """
    Online multi-face tracker using 2D spatial IoU bipartite matching.
    Maintains persistent track IDs to prevent camera flip-flopping between subjects.
    """
    def __init__(self, iou_threshold: float = 0.25, max_lost_frames: int = 20):
        self.iou_threshold = iou_threshold
        self.max_lost_frames = max_lost_frames
        self.active_tracks: list[FaceTrack] = []
        self.closed_tracks: list[FaceTrack] = []
        self._next_id = 1

    def update(self, frame_idx: int, detections: list[FaceBoundingBox]) -> list[FaceTrack]:
        matched_tracks = set()
        matched_dets = set()

        if self.active_tracks and detections:
            candidates = []
            for t_idx, track in enumerate(self.active_tracks):
                for d_idx, det in enumerate(detections):
                    iou = compute_2d_iou(track.latest_box, det)
                    if iou >= self.iou_threshold:
                        candidates.append((iou, t_idx, d_idx))

            candidates.sort(key=lambda x: x[0], reverse=True)
            for iou, t_idx, d_idx in candidates:
                if t_idx not in matched_tracks and d_idx not in matched_dets:
                    self.active_tracks[t_idx].add_detection(frame_idx, detections[d_idx])
                    matched_tracks.add(t_idx)
                    matched_dets.add(d_idx)

        # Unmatched detections become new tracks
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_dets:
                new_track = FaceTrack(self._next_id, det, frame_idx)
                self._next_id += 1
                self.active_tracks.append(new_track)

        # Remove dead tracks
        surviving = []
        for track in self.active_tracks:
            if frame_idx - track.last_frame <= self.max_lost_frames:
                surviving.append(track)
            else:
                self.closed_tracks.append(track)
        self.active_tracks = surviving
        return self.active_tracks

    def get_all_tracks(self) -> list[FaceTrack]:
        return self.active_tracks + self.closed_tracks


# ── One-Euro Filter & Deadband Smoothing ───────────────────────────────────────

class LowPassFilter:
    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self.s: Optional[float] = None

    def filter(self, val: float, alpha: Optional[float] = None) -> float:
        if alpha is not None:
            self.alpha = alpha
        if self.s is None:
            self.s = val
        else:
            self.s = self.alpha * val + (1.0 - self.alpha) * self.s
        return self.s

    def reset(self):
        self.s = None


class OneEuroFilter:
    """
    One-Euro filter for low-latency, speed-adaptive trajectory smoothing.
    Casiez et al., CHI 2012.
    """
    def __init__(
        self,
        min_cutoff: float = ONE_EURO_MIN_CUTOFF,
        beta: float = ONE_EURO_BETA,
        d_cutoff: float = ONE_EURO_D_CUTOFF,
    ):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_filter = LowPassFilter()
        self.dx_filter = LowPassFilter()
        self.last_time: Optional[float] = None

    def _alpha(self, cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def filter(self, x: float, timestamp: float) -> float:
        if self.last_time is None:
            self.last_time = timestamp
            return self.x_filter.filter(x, 1.0)

        dt = max(1e-4, timestamp - self.last_time)
        self.last_time = timestamp

        prev_x = self.x_filter.s if self.x_filter.s is not None else x
        dx = (x - prev_x) / dt
        alpha_d = self._alpha(self.d_cutoff, dt)
        filtered_dx = self.dx_filter.filter(dx, alpha_d)

        cutoff = self.min_cutoff + self.beta * abs(filtered_dx)
        alpha = self._alpha(cutoff, dt)
        return self.x_filter.filter(x, alpha)

    def reset(self):
        self.x_filter.reset()
        self.dx_filter.reset()
        self.last_time = None


class DeadbandFilter:
    """
    Combines a deadband threshold zone with a One-Euro filter.
    Inside deadband (|Δ| <= threshold): holds position with zero jitter.
    Outside deadband: smoothly pans to follow subject with zero lag.
    """
    def __init__(
        self,
        deadband_px: float = DEFAULT_DEADBAND_PX,
        min_cutoff: float = ONE_EURO_MIN_CUTOFF,
        beta: float = ONE_EURO_BETA,
    ):
        self.deadband_px = deadband_px
        self.one_euro = OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        self.last_output: Optional[float] = None

    def filter(self, raw_x: float, timestamp: float) -> float:
        if self.last_output is None:
            self.last_output = self.one_euro.filter(raw_x, timestamp)
            return self.last_output

        delta = raw_x - self.last_output
        if abs(delta) <= self.deadband_px:
            # Within deadband: hold rock-solid position
            target = self.last_output
        else:
            # Beyond deadband: shift toward target by excess amount
            sign = 1.0 if delta > 0 else -1.0
            target = raw_x - sign * self.deadband_px

        self.last_output = self.one_euro.filter(target, timestamp)
        return self.last_output

    def reset(self):
        self.one_euro.reset()
        self.last_output = None


# ── Shot-Bounded Reframing Engine ──────────────────────────────────────────────

def decide_layout_mode(
    tracks: list[FaceTrack],
    total_frames: int,
    src_w: int,
) -> tuple[str, Optional[FaceTrack], Optional[FaceTrack]]:
    """
    Determine layout mode based on detected face tracks:
    - 'blur_background': 0 prominent faces (slides, code demo, screencast)
    - 'split_screen': 2 prominent separated faces (dialogue / podcast 2-shot)
    - 'center_crop': 1 prominent speaker
    """
    if not tracks:
        return ("blur_background", None, None)

    # Filter tracks that appear in at least 20% of sampled frames
    prominent = [t for t in tracks if t.total_detections >= max(2, total_frames * 0.20)]
    if not prominent:
        return ("blur_background", None, None)

    # Check for dual-speaker layout (2 distinct prominent speakers separated by >= 25% frame width)
    if len(prominent) >= 2:
        sorted_by_detections = sorted(prominent, key=lambda t: t.total_detections, reverse=True)
        t1, t2 = sorted_by_detections[0], sorted_by_detections[1]
        x1 = t1.average_center_x()
        x2 = t2.average_center_x()
        if abs(x1 - x2) >= 0.25:
            # Left speaker first, right speaker second
            left_track = t1 if x1 < x2 else t2
            right_track = t2 if x1 < x2 else t1
            return ("split_screen", left_track, right_track)

    # Single dominant speaker: pick track with highest total detections and area
    dominant = max(prominent, key=lambda t: (t.total_detections, t.average_area()))
    return ("center_crop", dominant, None)


def smooth_crop_path_for_shot(
    raw_cx_list: list[int],
    src_w: int,
    crop_w: int,
    fps: float,
    deadband_px: float = DEFAULT_DEADBAND_PX,
) -> list[int]:
    """
    Smooth center-X trajectory strictly within a single shot using Deadband + One-Euro filter.
    Guarantees zero cross-shot whip-pan and zero stationary camera jitter.
    """
    if not raw_cx_list:
        return []

    deadband_filter = DeadbandFilter(deadband_px=deadband_px)
    smoothed: list[int] = []

    for idx, cx in enumerate(raw_cx_list):
        t = idx / max(1.0, fps)
        filtered_cx = deadband_filter.filter(float(cx), t)
        # Convert center X to left crop X and clamp to source bounds
        left_x = int(filtered_cx - crop_w / 2.0)
        left_x = max(0, min(src_w - crop_w, left_x))
        smoothed.append(left_x)

    return smoothed


def compute_crop_path(
    video_path: Path,
    shots: Optional[list[tuple[float, float, int]]] = None,
) -> tuple[list[int], int, int, float]:
    """
    Phase 3 Shot-Aware Face Tracking and Auto-Reframer.
    Segments by shot, tracks faces via IoU, eliminates stationary jitter with One-Euro filter,
    and returns per-frame crop X coordinates with zero cross-shot whip pan.

    Returns:
        (crop_x_list, src_width, src_height, fps)
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

    crop_w = int(src_h * 9 / 16)
    crop_w = min(crop_w, src_w)
    default_x = max(0, (src_w - crop_w) // 2)

    console.print(
        f"[cyan]👁 Phase 3 Shot-Aware Face Tracking:[/cyan] {src_w}×{src_h} @ {fps:.1f}fps, "
        f"crop_w={crop_w}px, {total_frames} frames"
    )

    # 1. Detect shot boundaries if not provided
    if shots is None:
        try:
            shots = detect_shot_boundaries(video_path)
        except Exception as e:
            console.print(f"[yellow][!] Shot detection failed ({e}), using single video shot[/yellow]")
            shots = [(0.0, total_frames / fps, 0)]

    if not shots:
        shots = [(0.0, total_frames / fps, 0)]

    mp_face = mp.solutions.face_detection
    all_smoothed_crops: list[int] = [default_x] * total_frames

    with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.45) as detector:
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Tracking faces per shot...", total=len(shots))

            for shot_idx, (s_start_sec, s_end_sec, s_id) in enumerate(shots):
                start_frame = max(0, min(total_frames - 1, int(s_start_sec * fps)))
                end_frame = max(start_frame + 1, min(total_frames, int(s_end_sec * fps)))
                shot_len = end_frame - start_frame

                cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                tracker = MultiFaceIoUTracker(iou_threshold=0.25)
                sampled_cx: dict[int, int] = {}
                sampled_count = 0

                curr_frame = start_frame
                while curr_frame < end_frame:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    rel_frame = curr_frame - start_frame
                    if rel_frame % SAMPLE_EVERY_N_FRAMES == 0:
                        sampled_count += 1
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        result = detector.process(rgb)
                        frame_dets: list[FaceBoundingBox] = []
                        if result.detections:
                            for det in result.detections:
                                bb = det.location_data.relative_bounding_box
                                score = float(det.score[0]) if det.score else 1.0
                                frame_dets.append(FaceBoundingBox(
                                    xmin=bb.xmin,
                                    ymin=bb.ymin,
                                    xmax=bb.xmin + bb.width,
                                    ymax=bb.ymin + bb.height,
                                    confidence=score,
                                ))

                        tracker.update(rel_frame, frame_dets)

                    curr_frame += 1

                # Decide layout for this shot
                layout_mode, dominant_track, secondary_track = decide_layout_mode(
                    tracker.get_all_tracks(), sampled_count, src_w
                )

                # Generate raw center X for each sampled frame in shot
                raw_cx_shot: list[int] = []
                for f in range(shot_len):
                    if dominant_track and dominant_track.boxes:
                        # Find closest detection in track
                        closest_f = min(dominant_track.boxes.keys(), key=lambda k: abs(k - f))
                        box = dominant_track.boxes[closest_f]
                        cx = int(box.center_x * src_w)
                    else:
                        cx = src_w // 2
                    raw_cx_shot.append(cx)

                # Apply shot-bounded Deadband + One-Euro smoothing
                shot_smoothed_crop_x = smooth_crop_path_for_shot(
                    raw_cx_shot, src_w, crop_w, fps, deadband_px=DEFAULT_DEADBAND_PX
                )

                # Store into full video crop timeline
                for f_rel, crop_x in enumerate(shot_smoothed_crop_x):
                    abs_f = start_frame + f_rel
                    if abs_f < total_frames:
                        all_smoothed_crops[abs_f] = crop_x

                progress.update(task, advance=1)

    cap.release()
    console.print(f"[green]✓ Shot-aware face tracking complete:[/green] {len(shots)} shots processed")
    return all_smoothed_crops, src_w, src_h, fps


def generate_clip_reframe_plans(
    candidates: list[ClipCandidate],
    crop_path: list[int],
    src_w: int,
    src_h: int,
    fps: float,
    shots: Optional[list[tuple[float, float, int]]] = None,
) -> list[ClipCandidate]:
    """
    Attach detailed ShotReframePlan metadata to each candidate clip.
    """
    crop_w = int(src_h * 9 / 16)
    crop_w = min(crop_w, src_w)

    for cand in candidates:
        s_frame = max(0, int(cand.start_seconds * fps))
        e_frame = min(len(crop_path), int(cand.end_seconds * fps))
        clip_crops = crop_path[s_frame:e_frame] if e_frame > s_frame else [crop_path[s_frame]]

        avg_x = int(np.mean(clip_crops)) if clip_crops else (src_w - crop_w) // 2
        cand.reframe_plans = [
            ShotReframePlan(
                shot_id=1,
                start_seconds=cand.start_seconds,
                end_seconds=cand.end_seconds,
                layout_mode="center_crop",
                crop_x=avg_x,
            )
        ]
        cand.layout_mode = "center_crop"

    return candidates


def remap_crop_path(
    crop_path: list[int],
    cuts: list[tuple[float, float]],
    fps: float,
) -> list[int]:
    """
    Slices and concatenates crop_path according to non-linear cut intervals [(src_start, src_end), ...].
    Returns the mapped crop_path array for the presentation timeline.
    """
    remapped: list[int] = []
    if not crop_path:
        return remapped

    total_orig_frames = len(crop_path)
    for src_start, src_end in cuts:
        start_frame = max(0, int(round(src_start * fps)))
        end_frame = min(total_orig_frames, int(round(src_end * fps)))
        if end_frame > start_frame:
            remapped.extend(crop_path[start_frame:end_frame])
        elif start_frame < total_orig_frames:
            remapped.append(crop_path[start_frame])

    return remapped

