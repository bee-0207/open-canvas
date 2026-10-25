"""ArUco marker detection and the camera -> painting homography.

Four DICT_4X4_50 markers (printed by tools/make_markers.py) sit diagonally outside the
painting's corners: 0 = top-left, 1 = top-right, 2 = bottom-right, 3 = bottom-left.
Other printed paintings use other IDs (content/library.yaml); pass them as `ids`.
Each frame, MarkerTracker.update() looks for them. When all four are visible it solves a
homography H (3x3 matrix) that maps camera pixels to painting coordinates (u, v). When a
hand hides a marker, it keeps using the last good H (CLAUDE.md section 11).

Contents:
    MarkerLayout   where the markers physically sit relative to the painting, in mm
    Detection      what one frame's detection found (for drawing and debugging)
    quad_center    true center of a marker seen in perspective
    MarkerTracker  update() per frame; camera_to_uv / uv_to_camera / flatten using H

Coordinates: (u, v) in [0, 1], origin at the painting's top-left (CLAUDE.md section 7).
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

ARUCO_DICT = cv2.aruco.DICT_4X4_50
CORNER_IDS = (0, 1, 2, 3)  # TL, TR, BR, BL; every array below follows this order


@dataclass(frozen=True)
class MarkerLayout:
    """Physical placement of the markers, measured on the real print.

    Each marker sits diagonally outside one painting corner, edges parallel to the
    painting's edges, with gap_mm of white between the black square and the painting edge
    (the same in x and y). Tiles from tools/make_markers.py placed with their inner corner
    touching the painting's corner give gap_mm = the tile border (10 mm by default).
    """

    painting_w_mm: float
    painting_h_mm: float
    marker_mm: float = 50.0
    gap_mm: float = 10.0

    def marker_centers_mm(self):
        """Marker centers in painting mm (origin = painting top-left), shape (4, 2)."""
        d = self.gap_mm + self.marker_mm / 2  # painting corner -> marker center, along x and y
        w, h = self.painting_w_mm, self.painting_h_mm
        return np.array([[-d, -d], [w + d, -d], [w + d, h + d], [-d, h + d]], dtype=np.float32)


@dataclass
class Detection:
    """Result of one MarkerTracker.update() call. corners/centers keep only the tracker's IDs;
    `seen` has every ID in view (used to recognize which painting is on the table)."""

    ids: tuple = CORNER_IDS  # the tracker's 4 IDs: TL, TR, BR, BL
    seen: set = field(default_factory=set)
    corners: dict = field(default_factory=dict)  # id -> (4, 2) camera px, OpenCV corner order
    centers: dict = field(default_factory=dict)  # id -> (2,) camera px
    updated: bool = False  # True if this frame produced a new homography

    @property
    def all_found(self):
        return all(i in self.corners for i in self.ids)

    @property
    def missing(self):
        return [i for i in self.ids if i not in self.corners]


def quad_center(quad):
    """Center of a marker as the camera sees it: the point where its diagonals cross.

    The plain average of the 4 corners drifts under perspective (the near side of the
    marker looks bigger). Straight lines stay straight under perspective, so the diagonal
    crossing is the exact image of the marker's physical center.

    Uses homogeneous coordinates: the cross product of two points is the line through
    them, and the cross product of two lines is the point where they meet.
    """
    p = np.hstack([quad, np.ones((4, 1))])
    diag_a = np.cross(p[0], p[2])
    diag_b = np.cross(p[1], p[3])
    x = np.cross(diag_a, diag_b)
    return x[:2] / x[2]


class MarkerTracker:
    """Finds the corner markers each frame and keeps the camera -> (u, v) homography."""

    def __init__(self, layout, ids=CORNER_IDS):
        self.layout = layout
        self.ids = tuple(ids)  # TL, TR, BR, BL

        params = cv2.aruco.DetectorParameters()
        # Sub-pixel corner refinement: steadier corners -> less jitter in H
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self._detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO_DICT), params)

        self._centers_mm = layout.marker_centers_mm()
        # Scales painting mm to normalized (u, v): u = x / width, v = y / height
        self._mm_to_uv = np.diag([1 / layout.painting_w_mm, 1 / layout.painting_h_mm, 1.0])

        self.H = None  # camera px -> (u, v); None until all four markers have been seen once
        self.frames_since_update = 0  # how old the current H is, for the debug overlay

    def update(self, frame_bgr):
        """Detect markers in one frame and refresh H if all four are visible.

        Returns a Detection. self.H is left as the last good value when a marker is missing.
        """
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        corners, ids, _rejected = self._detector.detectMarkers(gray)

        det = Detection(ids=self.ids)
        if ids is not None:
            for quad, marker_id in zip(corners, ids.flatten()):
                marker_id = int(marker_id)
                det.seen.add(marker_id)
                # Ignore other paintings' IDs, and keep only the first copy of a duplicated ID
                if marker_id in self.ids and marker_id not in det.corners:
                    q = quad.reshape(4, 2).astype(np.float64)
                    det.corners[marker_id] = q
                    det.centers[marker_id] = quad_center(q)

        self.frames_since_update += 1
        if det.all_found:
            H = self._solve(det)
            if H is not None:
                self.H = H
                self.frames_since_update = 0
                det.updated = True
        return det

    def _solve(self, det):
        """Homography from the 4 marker centers (camera px) to painting (u, v)."""
        src = np.array([det.centers[i] for i in self.ids], dtype=np.float32)
        # Markers taped in the wrong corners make a self-crossing quad. Reject it instead of
        # producing a garbage mapping (the last good H stays in use).
        if not cv2.isContourConvex(src):
            return None
        # Exactly 4 point pairs, so the homography is solved directly (no fitting needed)
        H_mm = cv2.getPerspectiveTransform(src, self._centers_mm)
        return self._mm_to_uv @ H_mm

    def camera_to_uv(self, x, y):
        """Camera pixel -> (u, v), or None before the first good H.

        Values outside [0, 1] mean the point is off the painting; the caller decides what
        to do with that.
        """
        if self.H is None:
            return None
        u, v = cv2.perspectiveTransform(np.array([[[x, y]]], dtype=np.float64), self.H)[0, 0]
        return float(u), float(v)

    def uv_to_camera(self, uv_points):
        """(u, v) points, shape (N, 2) -> camera pixels (N, 2). For drawing overlays."""
        if self.H is None:
            return None
        pts = np.asarray(uv_points, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, np.linalg.inv(self.H)).reshape(-1, 2)

    def flatten(self, frame_bgr, width_px=800):
        """Warp the painting area of a frame to a straight-on (top-down) image.

        The output keeps the painting's aspect ratio. Pixel (x, y) in it corresponds to
        (u, v) = (x / width, y / height). Returns None before the first good H.
        """
        if self.H is None:
            return None
        height_px = round(width_px * self.layout.painting_h_mm / self.layout.painting_w_mm)
        # H gives (u, v) in [0, 1]; scale up to output pixels
        to_px = np.diag([width_px, height_px, 1.0])
        return cv2.warpPerspective(frame_bgr, to_px @ self.H, (width_px, height_px))
