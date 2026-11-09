"""
Unit tests for Clipedics Phase 3: Shot-Aware Reframing, Multi-Face IoU Tracking, One-Euro Deadband Smoothing & Layout Modes.
"""
from __future__ import annotations
import pytest
from pathlib import Path
from core.models import FaceBoundingBox, ShotReframePlan, ClipCandidate
from core.reframer import (
    compute_2d_iou,
    FaceTrack,
    MultiFaceIoUTracker,
    OneEuroFilter,
    DeadbandFilter,
    decide_layout_mode,
    smooth_crop_path_for_shot,
)


def test_2d_iou_calculation():
    # Identical boxes -> IoU = 1.0
    b1 = FaceBoundingBox(xmin=0.1, ymin=0.1, xmax=0.5, ymax=0.5)
    b2 = FaceBoundingBox(xmin=0.1, ymin=0.1, xmax=0.5, ymax=0.5)
    assert pytest.approx(compute_2d_iou(b1, b2), 0.01) == 1.0

    # Disjoint boxes -> IoU = 0.0
    b3 = FaceBoundingBox(xmin=0.6, ymin=0.6, xmax=0.9, ymax=0.9)
    assert compute_2d_iou(b1, b3) == 0.0

    # Partial overlap
    b4 = FaceBoundingBox(xmin=0.3, ymin=0.1, xmax=0.7, ymax=0.5)
    iou = compute_2d_iou(b1, b4)
    assert 0.2 < iou < 0.5


def test_multi_face_iou_tracker_identity_persistence():
    tracker = MultiFaceIoUTracker(iou_threshold=0.25, max_lost_frames=5)

    # Frame 0: Two faces detected (left speaker and right speaker)
    det_left_0 = FaceBoundingBox(xmin=0.15, ymin=0.2, xmax=0.35, ymax=0.6)
    det_right_0 = FaceBoundingBox(xmin=0.65, ymin=0.2, xmax=0.85, ymax=0.6)
    tracks_0 = tracker.update(0, [det_left_0, det_right_0])
    assert len(tracks_0) == 2
    id_left = tracks_0[0].track_id
    id_right = tracks_0[1].track_id
    assert id_left != id_right

    # Frame 1: Slight movement, faces should retain exact same track IDs
    det_left_1 = FaceBoundingBox(xmin=0.16, ymin=0.21, xmax=0.36, ymax=0.61)
    det_right_1 = FaceBoundingBox(xmin=0.64, ymin=0.19, xmax=0.84, ymax=0.59)
    tracks_1 = tracker.update(1, [det_left_1, det_right_1])
    assert len(tracks_1) == 2
    assert tracks_1[0].track_id == id_left
    assert tracks_1[1].track_id == id_right


def test_deadband_filter_zero_jitter():
    # With deadband=25.0, small jitter (e.g. ±10px) must produce ZERO output change
    df = DeadbandFilter(deadband_px=25.0, min_cutoff=0.5, beta=0.05)
    initial_x = 500.0

    out0 = df.filter(initial_x, 0.0)
    assert out0 == initial_x

    # Jitter of +8px -> inside deadband -> output remains rock-solid
    out1 = df.filter(508.0, 0.033)
    assert out1 == out0

    # Jitter of -12px -> inside deadband -> output remains rock-solid
    out2 = df.filter(488.0, 0.066)
    assert out2 == out0

    # Large movement of +80px -> exceeds deadband -> smooth tracking engages
    out3 = df.filter(580.0, 0.100)
    assert out3 > out0


def test_one_euro_filter_smoothness():
    oef = OneEuroFilter(min_cutoff=0.5, beta=0.05)
    # Feed step response
    v0 = oef.filter(100.0, 0.0)
    v1 = oef.filter(200.0, 0.033)
    # Filter smoothly transitions without overshoot
    assert 100.0 < v1 < 200.0


def test_layout_decision_blur_background_for_slides():
    # 0 faces detected (presentation slides / screen recording)
    layout, t1, t2 = decide_layout_mode([], total_frames=100, src_w=1920)
    assert layout == "blur_background"
    assert t1 is None
    assert t2 is None


def test_layout_decision_split_screen_for_dialogue():
    # 2 prominent tracks horizontally separated by >= 25%
    b_left = FaceBoundingBox(xmin=0.15, ymin=0.2, xmax=0.30, ymax=0.6)
    b_right = FaceBoundingBox(xmin=0.70, ymin=0.2, xmax=0.85, ymax=0.6)

    track_left = FaceTrack(1, b_left, 0)
    track_left.total_detections = 40
    track_right = FaceTrack(2, b_right, 0)
    track_right.total_detections = 35

    layout, t1, t2 = decide_layout_mode([track_left, track_right], total_frames=100, src_w=1920)
    assert layout == "split_screen"
    assert t1.track_id == 1  # left
    assert t2.track_id == 2  # right


def test_layout_decision_center_crop_for_single_speaker():
    # Single dominant speaker
    b_speaker = FaceBoundingBox(xmin=0.40, ymin=0.2, xmax=0.60, ymax=0.6)
    track = FaceTrack(1, b_speaker, 0)
    track.total_detections = 60

    layout, t1, t2 = decide_layout_mode([track], total_frames=100, src_w=1920)
    assert layout == "center_crop"
    assert t1.track_id == 1
    assert t2 is None


def test_shot_bounded_zero_whip_pan():
    # Test that smoothing within a shot stays strictly within bounds and clamps correctly
    raw_cx = [960, 962, 958, 961, 960]
    smoothed = smooth_crop_path_for_shot(raw_cx, src_w=1920, crop_w=1080, fps=30.0, deadband_px=20.0)
    assert len(smoothed) == len(raw_cx)
    # Inside deadband, all smoothed values should be identical -> 0 jitter!
    assert all(x == smoothed[0] for x in smoothed)

