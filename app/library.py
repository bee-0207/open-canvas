"""Painting library: which paintings exist, and which printed page is under the camera.

Every printed page carries its own four ArUco markers (content/library.yaml lists their IDs),
so the main loop can tell the paintings apart from the markers alone. A blind visitor never
picks from a menu: they put a page on the table and Open Canvas speaks that painting.

Contents:
    pack_layout   marker + painting placement on one Letter page of the print pack, in mm
    Painting      one painting's files (content folder, voice folder) and its title
    Print         one printed copy: its painting, its 4 marker IDs, its MarkerLayout
    Library       load() from content/library.yaml; identify(seen IDs) -> Print or None
"""

import os
from dataclasses import dataclass

import cv2
import yaml

from app.markers import MarkerLayout

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, "content", "library.yaml")

# Print pack page (tools/make_print_pack.py): US Letter landscape. The page is drawn from
# these numbers and the runtime layout is computed from the same numbers, so they can't drift.
PAGE_W_MM, PAGE_H_MM = 279.4, 215.9
PAGE_MARGIN_MM = 10.0   # most home printers can't print closer to the edge than ~6 mm
PACK_MARKER_MM = 25.0   # ~70 px wide at the demo camera height: plenty for detection
PACK_GAP_MM = 5.0       # white between each marker and the painting's corner


def pack_layout(aspect):
    """Biggest painting of this width/height ratio that fits the page with its 4 markers.

    The markers sit diagonally outside the painting's corners (same geometry as the taped
    board), so each one adds gap + marker to both sides: 2 * 30 mm in each direction.
    Printing the page scaled up (e.g. "fit to page" on 11x17) scales everything together,
    which leaves (u, v) unchanged, so the same layout works at any print size.
    """
    extra = 2 * (PACK_GAP_MM + PACK_MARKER_MM)
    max_w = PAGE_W_MM - 2 * PAGE_MARGIN_MM - extra
    max_h = PAGE_H_MM - 2 * PAGE_MARGIN_MM - extra
    w = min(max_w, max_h * aspect)
    return MarkerLayout(w, w / aspect, PACK_MARKER_MM, PACK_GAP_MM)


@dataclass
class Painting:
    slug: str
    title: str
    artist: str
    content: str   # absolute folder: painting.png, regions.png, regions.json, overview.txt
    voice: str     # absolute folder: overview.wav, region_<id>.wav

    @property
    def aspect(self):
        h, w = cv2.imread(os.path.join(self.content, "painting.png"), cv2.IMREAD_GRAYSCALE).shape
        return w / h


@dataclass
class Print:
    painting: Painting
    ids: tuple            # marker IDs: top-left, top-right, bottom-right, bottom-left
    layout: MarkerLayout
    kind: str             # "pack" or "board"


class Library:
    def __init__(self, prints):
        self.prints = prints

    @classmethod
    def load(cls, board_layout, index=INDEX):
        """Read content/library.yaml. board_layout: MarkerLayout of the taped Sunset Hills board."""
        with open(index) as f:
            entries = yaml.safe_load(f)["paintings"]
        prints, used = [], set()
        for e in entries:
            content = os.path.join(REPO, e["content"])
            voice = os.path.join(REPO, e["voice"]) if e.get("voice") else os.path.join(content, "voice")
            p = Painting(e["slug"], e["title"], e["artist"], content, voice)
            for pr in e["prints"]:
                ids = tuple(int(i) for i in pr["ids"])
                if len(ids) != 4 or used & set(ids):
                    raise SystemExit(f"[library] {p.slug}: marker IDs {ids} must be 4 IDs not used by another print")
                used |= set(ids)
                layout = board_layout if pr["layout"] == "board" else pack_layout(p.aspect)
                prints.append(Print(p, ids, layout, pr["layout"]))
        return cls(prints)

    def identify(self, seen_ids, min_markers=3):
        """The print whose markers are visible: at least min_markers of its 4 IDs seen.

        3 of 4 is enough to recognize a page even with a hand over one corner. Returns the
        print with the most markers seen, or None.
        """
        best, best_n = None, min_markers - 1
        for pr in self.prints:
            n = sum(i in seen_ids for i in pr.ids)
            if n > best_n:
                best, best_n = pr, n
        return best
