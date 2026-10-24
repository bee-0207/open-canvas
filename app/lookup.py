"""(u, v) on the painting -> color, region, and edge flag (CLAUDE.md sections 2 and 7).

Everything is sampled from the clean digital files in content/, never from the webcam
image: the webcam's colors shift with room lighting and the hand covers the spot being
asked about. The printed painting just has to be content/painting.png printed edge to edge.

Contents:
    edge_band     region map -> boolean "near a boundary" mask (used here and by
                  tools/make_edge_map.py)
    Lookup        sample(u, v) per frame; crop(u, v) for the describe feature

Edges come from region-map boundaries, not image edge detection: Canny on a painting
fires on every brushstroke and the motor would buzz constantly (CLAUDE.md section 7).
"""

import os

import cv2
import numpy as np

from app.audio.color_map import rgb_to_hsl

CONTENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "content")


def edge_band(regions, band_frac=0.02):
    """Pixels within a band around every boundary between two different regions.

    band_frac is the band's total width as a fraction of the image width. 0.02 on a
    279 mm wide print is about 5.6 mm: wide enough that a fingertip (and ~1-2 mm of
    tracking jitter) actually lands in it, narrow enough to feel like a line.
    """
    r = regions.astype(np.int32)
    boundary = np.zeros(r.shape, np.uint8)
    # A pixel is on a boundary if its right or lower neighbor has a different region ID
    boundary[:, :-1] |= (r[:, :-1] != r[:, 1:])
    boundary[:-1, :] |= (r[:-1, :] != r[1:, :])
    k = max(3, int(round(band_frac * r.shape[1])) | 1)  # odd kernel size
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.dilate(boundary, kernel) > 0


class Lookup:
    def __init__(self, content=CONTENT, band_frac=0.02, crop_frac=0.12):
        self.painting = cv2.imread(os.path.join(content, "painting.png"), cv2.IMREAD_COLOR)
        if self.painting is None:
            raise SystemExit(f"Missing {content}/painting.png")
        regions = cv2.imread(os.path.join(content, "regions.png"), cv2.IMREAD_UNCHANGED)
        if regions is None:
            raise SystemExit(f"Missing {content}/regions.png")
        self.regions = regions[:, :, 0] if regions.ndim == 3 else regions

        # Prefer the saved edge map (so it can be hand-touched in an image editor);
        # otherwise build it from the region map now. Both are the same function.
        edges = cv2.imread(os.path.join(content, "edges.png"), cv2.IMREAD_GRAYSCALE)
        self.edges = edges > 127 if edges is not None else edge_band(self.regions, band_frac)
        self.crop_frac = crop_frac

    def _px(self, img, u, v):
        """(u, v) in [0, 1] -> integer pixel (x, y) in img, clamped to the image."""
        h, w = img.shape[:2]
        x = min(max(int(u * (w - 1)), 0), w - 1)
        y = min(max(int(v * (h - 1)), 0), h - 1)
        return x, y

    def sample(self, u, v):
        """Returns (hsl, region_id, on_edge). hsl = (hue deg, sat 0..1, lightness 0..1)."""
        x, y = self._px(self.painting, u, v)
        b, g, r = self.painting[y, x]
        hsl = rgb_to_hsl((int(r), int(g), int(b)))
        x, y = self._px(self.regions, u, v)
        rid = int(self.regions[y, x])
        x, y = self._px(self.edges, u, v)
        return hsl, rid, bool(self.edges[y, x])

    def crop(self, u, v):
        """Square crop of the clean painting around (u, v), for audio.describe()."""
        h, w = self.painting.shape[:2]
        half = max(8, int(self.crop_frac * w / 2))
        x, y = self._px(self.painting, u, v)
        return self.painting[max(0, y - half):y + half, max(0, x - half):x + half].copy()
