"""Generate a printable PDF of the four ArUco corner markers at actual size.

Usage (from the repo root, venv active):
    python tools/make_markers.py                      # -> assets/markers.pdf
    python tools/make_markers.py --size-mm 50 --border-mm 10 --out assets/markers.pdf

Print at 100% / "Actual size" (NOT "Fit to page"), then check the 10 cm bar with a ruler.

One US Letter page holds four cut-out tiles: a black 4x4 ArUco marker (DICT_4X4_50,
IDs 0-3) surrounded by a white border (the "quiet zone" the detector needs to find the
marker's outline), with a dashed cut line around each tile.

The PDF is written by hand as vector rectangles instead of a rendered bitmap, so marker
edges stay sharp at any printer resolution and no PDF library is needed. A one-page PDF
is just five numbered objects plus a table of their byte offsets (see write_pdf).
"""

import argparse
from pathlib import Path

import cv2

ARUCO_DICT = cv2.aruco.DICT_4X4_50
CORNER_NAMES = {0: "TOP-LEFT", 1: "TOP-RIGHT", 2: "BOTTOM-RIGHT", 3: "BOTTOM-LEFT"}

PAGE_W_MM, PAGE_H_MM = 215.9, 279.4  # US Letter
PT_PER_MM = 72 / 25.4  # PDF units are points (1/72 inch)


class Page:
    """Collects PDF drawing commands for one page.

    Takes positions in mm with the origin at the top-left and y pointing down (like an
    image). PDF uses points with the origin at the bottom-left and y pointing up, so every
    coordinate is converted here.
    """

    def __init__(self):
        self.ops = []

    def _pt(self, x_mm, y_mm):
        return x_mm * PT_PER_MM, (PAGE_H_MM - y_mm) * PT_PER_MM

    def fill_rect(self, x, y, w, h, gray=0.0):
        """Filled rectangle; (x, y) is its top-left corner. gray: 0 = black, 1 = white."""
        px, py = self._pt(x, y + h)  # PDF rectangles are anchored at their bottom-left
        self.ops.append(f"{gray:.3f} g {px:.3f} {py:.3f} {w * PT_PER_MM:.3f} {h * PT_PER_MM:.3f} re f")

    def dashed_rect(self, x, y, w, h, gray=0.6):
        """Thin dashed outline (cut line). q/Q save and restore so the dash doesn't leak."""
        px, py = self._pt(x, y + h)
        self.ops.append(
            f"q [3 3] 0 d 0.5 w {gray:.3f} G "
            f"{px:.3f} {py:.3f} {w * PT_PER_MM:.3f} {h * PT_PER_MM:.3f} re S Q"
        )

    def text(self, x, y, s, size=9):
        """Helvetica text with its baseline starting at (x, y)."""
        px, py = self._pt(x, y)
        s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # PDF string escapes
        self.ops.append(f"BT /F1 {size} Tf 0 g {px:.3f} {py:.3f} Td ({s}) Tj ET")


def draw_marker(page, dictionary, marker_id, x, y, size_mm, border_mm):
    """Draw one tile: dashed cut line, white border, then the marker with top-left at (x, y)."""
    # One pixel per cell: 4x4 data bits plus a 1-cell black frame = 6x6, 0 = black, 255 = white
    n = dictionary.markerSize + 2
    cells = cv2.aruco.generateImageMarker(dictionary, marker_id, n)
    cell = size_mm / n

    # Paint the border white explicitly: the page itself has no background, and some viewers
    # and converters render unpainted areas as transparent (which reads as black)
    tile = size_mm + 2 * border_mm
    page.fill_rect(x - border_mm, y - border_mm, tile, tile, gray=1.0)
    page.dashed_rect(x - border_mm, y - border_mm, tile, tile)
    page.fill_rect(x, y, size_mm, size_mm, gray=0.0)

    # Paint white cells over the black square, merging horizontal runs into one rectangle.
    # (On-screen viewers may still show faint seams between rows; printers don't.)
    for r in range(n):
        c = 0
        while c < n:
            if cells[r, c] == 255:
                start = c
                while c < n and cells[r, c] == 255:
                    c += 1
                page.fill_rect(x + start * cell, y + r * cell, (c - start) * cell, cell, gray=1.0)
            else:
                c += 1


def draw_ruler(page, x, y):
    """10 cm bar with 1 cm ticks, to confirm the print came out at actual size."""
    page.fill_rect(x, y, 100, 1.5)
    for i in range(11):
        page.fill_rect(x + i * 10 - 0.25, y - 3, 0.5, 3)
    page.text(x, y + 6, "This bar must measure exactly 10.0 cm. If not, reprint at 100% / Actual size.", 8)


def build_page(size_mm, border_mm):
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    page = Page()

    tile = size_mm + 2 * border_mm
    gap = 20  # space between tiles, room for the labels
    left = (PAGE_W_MM - (2 * tile + gap)) / 2
    top = 30
    if left < 10 or top + 2 * tile + gap + 50 > PAGE_H_MM:
        raise SystemExit(f"{tile:.0f} mm tiles don't fit on one Letter page; use a smaller size or border")

    page.text(left, 18, f"Open Canvas corner markers  -  ArUco DICT_4X4_50, {size_mm:g} mm, {border_mm:g} mm border", 11)

    for marker_id in range(4):
        row, col = divmod(marker_id, 2)
        # Lay out tiles in the same arrangement as the corners: 0 1 / 3 2
        if row == 1:
            col = 1 - col
        tile_x = left + col * (tile + gap)
        tile_y = top + row * (tile + gap)
        draw_marker(page, dictionary, marker_id, tile_x + border_mm, tile_y + border_mm, size_mm, border_mm)
        page.text(tile_x, tile_y + tile + 5, f"ID {marker_id}  -  {CORNER_NAMES[marker_id]} corner", 9)

    y = top + 2 * tile + gap + 15
    draw_ruler(page, left, y)
    notes = [
        "1. Cut along the dashed lines (keep the white border; the detector needs it).",
        "2. Place each tile diagonally outside its corner of the picture, with the tile's",
        "   inner corner touching the picture's corner. Tile edges parallel to picture edges.",
        "3. Rotation of the marker itself doesn't matter. Keep tiles flat; matte paper if possible.",
        f"4. Then the marker-to-picture gap is {border_mm:g} mm: pass --gap-mm {border_mm:g} to the test script.",
    ]
    for i, line in enumerate(notes):
        page.text(left, y + 16 + i * 5, line, 8)
    return page


def write_pdf(path, page):
    """Write a one-page PDF: catalog -> page list -> page -> (font, content stream)."""
    stream = "\n".join(page.ops).encode("latin-1")
    w_pt, h_pt = PAGE_W_MM * PT_PER_MM, PAGE_H_MM * PT_PER_MM
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.3f} {h_pt:.3f}] "
        f"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"

    # Cross-reference table: byte offset of each object, so readers can jump straight to it
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--size-mm", type=float, default=50.0, help="black marker square side (default 50)")
    ap.add_argument("--border-mm", type=float, default=10.0, help="white border around each marker (default 10)")
    ap.add_argument("--out", type=Path, default=repo_root / "assets" / "markers.pdf")
    args = ap.parse_args()

    # The quiet zone should be at least one marker cell wide or detection gets unreliable
    cell_mm = args.size_mm / 6
    if args.border_mm < cell_mm:
        print(f"Warning: border {args.border_mm:g} mm is narrower than one cell ({cell_mm:.1f} mm)")

    write_pdf(args.out, build_page(args.size_mm, args.border_mm))
    print(f"Wrote {args.out}  (print at 100% / Actual size)")


if __name__ == "__main__":
    main()
