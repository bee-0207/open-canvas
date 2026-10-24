"""Build content/edges.png (where the fingertip motor buzzes) from content/regions.png.

Usage (from the repo root, venv active; note the -m):
    python -m tools.make_edge_map                    # writes content/edges.png + a preview
    python -m tools.make_edge_map --band 0.03        # wider band (fraction of image width)

Output:
    content/edges.png           white = edge band (motor on), black = no edge
    content/edges_preview.png   the painting with the band drawn in red, to eyeball it

app/lookup.py uses content/edges.png if it exists, otherwise builds the same band itself,
so this tool is only needed to inspect the band or hand-edit it. Rerun it whenever the BME
updates regions.png.
"""

import argparse
import os

import cv2
import numpy as np

from app.lookup import CONTENT, edge_band


def main():
    ap = argparse.ArgumentParser(description="Region boundaries -> dilated edge map")
    ap.add_argument("--content", default=CONTENT)
    ap.add_argument("--band", type=float, default=0.02, help="band width as a fraction of image width")
    args = ap.parse_args()

    regions = cv2.imread(os.path.join(args.content, "regions.png"), cv2.IMREAD_UNCHANGED)
    if regions is None:
        raise SystemExit(f"Missing {args.content}/regions.png")
    if regions.ndim == 3:
        regions = regions[:, :, 0]
    band = edge_band(regions, args.band)
    cv2.imwrite(os.path.join(args.content, "edges.png"), band.astype(np.uint8) * 255)

    painting = cv2.imread(os.path.join(args.content, "painting.png"), cv2.IMREAD_COLOR)
    if painting is not None:
        preview = painting.copy()
        preview[band] = (0.4 * preview[band] + 0.6 * np.array([0, 0, 255])).astype(np.uint8)
        cv2.imwrite(os.path.join(args.content, "edges_preview.png"), preview)
    print(f"edges.png: {band.mean() * 100:.1f}% of the painting is edge band "
          f"(band {args.band:.3f} x width = {args.band * regions.shape[1]:.0f} px)")


if __name__ == "__main__":
    main()
