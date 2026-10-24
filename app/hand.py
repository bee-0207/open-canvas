"""Index fingertip tracking with MediaPipe HandLandmarker (Tasks API).

MediaPipe finds up to N hands per frame and returns 21 landmarks each. The index fingertip
is landmark 8 (CLAUDE.md section 2). This module only reports where the fingertip is in
camera pixels; main.py maps it to painting (u, v) with the marker homography and applies
smoothing and the fingertip offset (CLAUDE.md section 11).

Contents:
    Fingertip         one frame's result: fingertip px, all 21 landmarks px, confidence
    FingertipTracker  detect(frame) per frame; close() when done (or use `with`)

Running mode is VIDEO: MediaPipe tracks the hand between frames instead of searching the
whole image every time, which is faster and steadier. It needs strictly increasing
timestamps, which the tracker generates itself from a monotonic clock.

Model file: assets/models/hand_landmarker.task (float16, from Google's MediaPipe model
storage, committed to the repo so the demo doesn't depend on a download).
"""

import os
import time
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "assets", "models", "hand_landmarker.task")
INDEX_TIP = 8

# Pairs of landmark indices that form the hand skeleton, for drawing only
HAND_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
                    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
                    (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]


@dataclass
class Fingertip:
    """Result of one FingertipTracker.detect() call when a hand was found."""

    x: float            # index fingertip, camera px
    y: float
    landmarks: np.ndarray  # (21, 2) camera px, for drawing the skeleton
    score: float        # handedness confidence in [0, 1] (MediaPipe's per-hand score)
    handedness: str     # "Left" or "Right" as MediaPipe sees it (flipped vs. a selfie view)


class FingertipTracker:
    def __init__(self, model_path=MODEL_PATH, num_hands=1, min_confidence=0.5):
        # One hand for now: the user explores with one finger. With 2+ hands we'd have to
        # pick which one is "the" finger (e.g. the one wearing the motor).
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_confidence,
            min_hand_presence_confidence=min_confidence,
            min_tracking_confidence=min_confidence,
        )
        self._landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self._t0 = time.monotonic()
        self._last_ts = -1

    def detect(self, frame_bgr):
        """Find the index fingertip in a BGR frame. Returns a Fingertip, or None if no hand."""
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)  # MediaPipe expects RGB
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # VIDEO mode rejects a timestamp that isn't larger than the previous one
        ts = max(int((time.monotonic() - self._t0) * 1000), self._last_ts + 1)
        self._last_ts = ts
        result = self._landmarker.detect_for_video(image, ts)

        if not result.hand_landmarks:
            return None
        # Landmarks come back normalized to [0, 1] of the image size; convert to pixels
        pts = np.array([[lm.x * w, lm.y * h] for lm in result.hand_landmarks[0]], dtype=np.float32)
        cat = result.handedness[0][0]
        return Fingertip(x=float(pts[INDEX_TIP, 0]), y=float(pts[INDEX_TIP, 1]), landmarks=pts,
                         score=float(cat.score), handedness=cat.category_name)

    def close(self):
        self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
