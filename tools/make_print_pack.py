"""Generate the print pack: one US Letter (landscape) page per painting in content/library.yaml,
with the painting and its own four ArUco markers printed on the page. Nothing to cut or tape
together: print it, lay a page flat under the camera, and Open Canvas recognizes it.

Usage (from the repo root, venv active; note the -m):
    python -m tools.make_print_pack                 # -> assets/print_pack.pdf

Print at "Actual size". "Fit to page" on bigger paper (11x17, A3) also works and gives a
bigger painting to explore: it scales the markers and the painting together, and Open Canvas
only cares about their proportions (app/library.py pack_layout).

Page layout (all numbers from app/library.py, the same ones the program uses):
    title + artist centered above the painting, between the two top markers
    the painting, as large as fits with a marker diagonally outside each corner
    a short how-to line under the painting
    a dashed line across the top-left page corner: cut it off so a blind user can feel which
    way is up (the cut corner goes at the top left)

The PDF is written by hand (like tools/make_markers.py): vector rectangles for the markers so
their edges stay sharp, and the painting embedded as a JPEG image (PDF reads JPEG directly).
"""

import argparse
from pathlib import Path

import cv2

from app.library import PAGE_H_MM, PAGE_W_MM, Library
from app.markers import MarkerLayout
from tools.make_markers import ARUCO_DICT, PT_PER_MM, draw_marker


class LandscapePage:
    """PDF drawing commands for one page, in mm with the origin top-left and y down."""

    def __init__(self):
        self.ops = []
        self.image = None  # (jpeg bytes, px width, px height); one image per page

    def _pt(self, x_mm, y_mm):
        return x_mm * PT_PER_MM, (PAGE_H_MM - y_mm) * PT_PER_MM

    def fill_rect(self, x, y, w, h, gray=0.0):
        px, py = self._pt(x, y + h)
        self.ops.append(f"{gray:.3f} g {px:.3f} {py:.3f} {w * PT_PER_MM:.3f} {h * PT_PER_MM:.3f} re f")

    def dashed_rect(self, *args, **kwargs):
        pass  # draw_marker's cut line: nothing to cut on this page

    def dashed_line(self, x1, y1, x2, y2):
        (a, b), (c, d) = self._pt(x1, y1), self._pt(x2, y2)
        self.ops.append(f"q [3 3] 0 d 0.6 w 0.4 G {a:.3f} {b:.3f} m {c:.3f} {d:.3f} l S Q")

    def text(self, x, y, s, size=9, center=False):
        if center:
            x -= len(s) * size * 0.5 / PT_PER_MM / 2  # Helvetica averages ~0.5 em per character
        px, py = self._pt(x, y)
        s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        self.ops.append(f"BT /F1 {size} Tf 0 g {px:.3f} {py:.3f} Td ({s}) Tj ET")

    def draw_image(self, bgr, x, y, w, h):
        ok, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        self.image = (jpg.tobytes(), bgr.shape[1], bgr.shape[0])
        px, py = self._pt(x, y + h)
        # The image is drawn in a 1x1 unit square; cm scales and moves it onto the page
        self.ops.insert(0, f"q {w * PT_PER_MM:.3f} 0 0 {h * PT_PER_MM:.3f} {px:.3f} {py:.3f} cm /Im0 Do Q")


def build_page(pr, n, total):
    page = LandscapePage()
    lay = pr.layout
    w, h, m, g = lay.painting_w_mm, lay.painting_h_mm, lay.marker_mm, lay.gap_mm
    x0, y0 = (PAGE_W_MM - w) / 2, (PAGE_H_MM - h) / 2   # painting centered on the page

    painting = cv2.imread(str(Path(pr.painting.content) / "painting.png"), cv2.IMREAD_COLOR)
    page.draw_image(painting, x0, y0, w, h)

    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    tl, tr, br, bl = pr.ids
    for marker_id, (mx, my) in [(tl, (x0 - g - m, y0 - g - m)), (tr, (x0 + w + g, y0 - g - m)),
                                (br, (x0 + w + g, y0 + h + g)), (bl, (x0 - g - m, y0 + h + g))]:
        draw_marker(page, dictionary, marker_id, mx, my, m, g)

    cx = PAGE_W_MM / 2
    page.text(cx, y0 - 15, pr.painting.title, 15, center=True)
    page.text(cx, y0 - 7, pr.painting.artist, 10, center=True)
    page.text(cx, y0 + h + 10, "Lay flat under the camera with all four corner squares visible.", 8, center=True)
    page.text(cx, y0 + h + 16, f"Open Canvas print pack, page {n} of {total}. Print at Actual size, "
                               "or Fit to page on bigger paper.", 7, center=True)
    page.dashed_line(0, 14, 14, 0)
    page.text(3, 18, "cut", 6)
    return page


def write_pdf(path, pages):
    """Multi-page PDF: catalog, page list, shared font, then per page (page, contents, image)."""
    w_pt, h_pt = PAGE_W_MM * PT_PER_MM, PAGE_H_MM * PT_PER_MM
    n = len(pages)
    page_ids = [4 + 3 * i for i in range(n)]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % i for i in page_ids) + b"] /Count %d >>" % n,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for pid, page in zip(page_ids, pages):
        stream = "\n".join(page.ops).encode("latin-1")
        jpg, iw, ih = page.image
        objects += [
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.3f} {h_pt:.3f}] "
            f"/Resources << /Font << /F1 3 0 R >> /XObject << /Im0 {pid + 2} 0 R >> >> "
            f"/Contents {pid + 1} 0 R >>".encode(),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
            b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n" % (iw, ih, len(jpg))
            + jpg + b"\nendstream",
        ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)


def main():
    repo = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Print pack: one page per painting, markers included")
    ap.add_argument("--out", type=Path, default=repo / "assets" / "print_pack.pdf")
    args = ap.parse_args()
    # The taped board isn't in the pack; its layout here is a placeholder
    prints = [p for p in Library.load(MarkerLayout(1, 1)).prints if p.kind == "pack"]
    pages = [build_page(pr, i + 1, len(prints)) for i, pr in enumerate(prints)]
    write_pdf(args.out, pages)
    for pr in prints:
        print(f"  {pr.painting.title}: {pr.layout.painting_w_mm:.0f} x {pr.layout.painting_h_mm:.0f} mm, "
              f"markers {list(pr.ids)}")
    print(f"wrote {args.out} ({len(pages)} pages)")


if __name__ == "__main__":
    main()
