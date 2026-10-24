"""
mouse_demo.py: see and hear the audio engine on the real painting, no camera or ESP32.

The mouse stands in for the fingertip: the painting is drawn in a window, and moving over
it calls audio.update() at 30 Hz exactly like the main loop will. Uses OpenCV for the
window (already a project dependency), so nothing new to install.

    .venv/bin/python tools/mouse_demo.py                 # you drive with the mouse
    .venv/bin/python tools/mouse_demo.py --tour          # watch the scripted fake_inputs path

Controls
    move over the painting    finger touching that spot (move into the gray panel = lifted)
    rest on one area 2 s      hover-to-speak: music ducks and the area is described (ring fills)
    hold left mouse button    arcade button: after 0.3 s -> description of the spot right away
    SPACE                     describe the spot under the mouse right away
    O                         spoken overview (Layer 1)
    R                         region-map overlay on/off
    ESC or Q                  quit

Headphones on: panning only works in stereo. Try it with your eyes closed.
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.audio import engine as E                       # noqa: E402
import fake_inputs as F                                 # noqa: E402  (FakeLookup, scripted path)

WIN = "Open Canvas: audio test"
HUD_H = 140
FPS = 30
HOLD_TIME = F.HOLD_TIME
# Bar colors per instrument (BGR, since OpenCV draws in BGR).
COLORS = {"harp": (240, 150, 90), "strings": (70, 140, 240), "woodwind": (90, 180, 90),
          "choir": (235, 235, 235), "cello": (210, 110, 150)}


class Mouse:
    def __init__(self):
        self.x = self.y = -1
        self.down = False

    def __call__(self, event, x, y, flags, _):
        self.x, self.y = x, y
        if event == cv2.EVENT_LBUTTONDOWN:
            self.down = True
        elif event == cv2.EVENT_LBUTTONUP:
            self.down = False


def text(img, s, org, scale=0.6, color=(235, 235, 235), thick=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", default=os.path.join(REPO, "content"))
    ap.add_argument("--sounds", default=os.path.join(REPO, "assets", "sounds"))
    ap.add_argument("--width", type=int, default=1000, help="window width in pixels")
    ap.add_argument("--tour", action="store_true", help="play the scripted path from fake_inputs.py")
    ap.add_argument("--overview", action="store_true", help="start with the spoken overview")
    a = ap.parse_args()

    lookup = F.FakeLookup(a.content)
    audio = E.AudioEngine(content=a.content, sounds=a.sounds, root=REPO, crop_fn=lookup.crop)
    if lookup.painting is None:
        sys.exit(f"no painting.png in {a.content}")

    W = a.width
    H = int(lookup.painting.shape[0] * W / lookup.painting.shape[1])
    painting = cv2.resize(lookup.painting, (W, H), interpolation=cv2.INTER_AREA)
    overlay = None
    if lookup.regions is not None:
        rng = np.random.default_rng(3)
        pal = rng.integers(40, 255, (256, 3)).astype(np.uint8)
        pal[0] = 0
        reg = cv2.resize(lookup.regions, (W, H), interpolation=cv2.INTER_NEAREST)
        overlay = cv2.addWeighted(painting, 0.55, pal[reg], 0.45, 0)
        edges = cv2.morphologyEx(reg, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        overlay[edges] = (255, 0, 255)

    mouse = Mouse()
    cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WIN, mouse)
    audio.start()
    if a.overview:
        audio.play_overview()

    show_regions, t0 = False, time.monotonic()
    btn_down_at, fired = None, False
    tour_state = {"btn_i": 0, "down_at": None, "fired": False, "last_name": None}
    rng = np.random.default_rng(1)
    try:
        while True:
            t = time.monotonic() - t0
            frame = np.full((H + HUD_H, W, 3), (26, 22, 18), np.uint8)
            frame[:H] = overlay if (show_regions and overlay is not None) else painting

            if a.tour:
                if t > F.PATH[-1][0]:
                    break
                F.drive(audio, lookup, t, tour_state, rng, dropout=0.0)
                uv = F.finger_at(t)
                btn = tour_state["down_at"] is not None
            else:
                uv = (mouse.x / W, mouse.y / H) if 0 <= mouse.x < W and 0 <= mouse.y < H else None
                if uv is not None:
                    hsl, rid = lookup.sample(*uv)
                    audio.update(uv[0], uv[1], hsl, rid, True)
                else:
                    audio.update(0.0, 0.0, None, 0, False)
                # Arcade button = left mouse; fire once per hold after HOLD_TIME, like the main loop.
                btn = mouse.down
                if btn and btn_down_at is None:
                    btn_down_at, fired = t, False
                elif not btn:
                    btn_down_at = None
                if btn_down_at is not None and not fired and t - btn_down_at >= HOLD_TIME and uv is not None:
                    fired = True
                    audio.describe(lookup.crop(*uv))

            if uv is not None:
                p = (int(uv[0] * W), int(uv[1] * H))
                cv2.circle(frame, p, 14, (255, 255, 255), 3, cv2.LINE_AA)
                cv2.circle(frame, p, 4, (60, 60, 255), -1, cv2.LINE_AA)
                if btn:
                    cv2.circle(frame, p, 22, (90, 210, 255), 2, cv2.LINE_AA)
                # Hover-to-speak progress: the ring fills over HOVER_TIME, then turns green.
                hv = audio.state.get("hover", 0.0)
                if hv > 0:
                    col = (110, 220, 110) if hv >= 1.0 else (90, 210, 255)
                    cv2.ellipse(frame, p, (28, 28), -90, 0, 360 * hv, col, 4, cv2.LINE_AA)

            # ---- HUD ----
            s, y0 = audio.state, H + 30
            name = s.get("region_name", "") if "uv" in s else "LIFTED"
            text(frame, (name or "(no region)").upper(), (14, y0), 0.9, thick=2)
            if "hsl" in s:
                h_, s_, l_ = s["hsl"]
                text(frame, f"hue {h_:.0f}  sat {s_:.2f}  light {l_:.2f}", (14, y0 + 28), 0.5, (180, 180, 190))
            status = "CHIME" if audio._chime is not None else ("VOICE" if audio._voice is not None else "")
            text(frame, status, (14, y0 + 62), 0.8, (90, 210, 255), 2)
            text(frame, f"duck {audio.sm_duck.y:.2f}   underruns {audio.underruns}"
                 + ("   TOUR" if a.tour else ""), (14, y0 + 92), 0.5, (180, 180, 190))
            if audio.callback_error:
                text(frame, f"AUDIO ERROR: {audio.callback_error}", (14, y0 + 112), 0.5, (80, 80, 255))
            x = 330
            for k in audio.stems:
                g = audio.sm_low[k].y + audio.sm_high[k].y
                bh = int(min(g / 1.2, 1.0) * 85)
                cv2.rectangle(frame, (x, y0 + 72 - bh), (x + 40, y0 + 72), COLORS.get(k, (200, 200, 200)), -1)
                text(frame, k, (x, y0 + 92), 0.45, (200, 200, 210))
                x += 125
            text(frame, "rest 2 s = describe   hold mouse = button   O overview   R regions   ESC quit",
                 (330, H + HUD_H - 10), 0.4, (140, 140, 150))

            cv2.imshow(WIN, frame)
            key = cv2.waitKey(int(1000 / FPS)) & 0xFF
            if key in (27, ord("q")) or cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("o"):
                audio.play_overview()
            elif key == ord("r"):
                show_regions = not show_regions
            elif key == ord(" ") and uv is not None:
                audio.describe(lookup.crop(*uv))
    except KeyboardInterrupt:
        pass
    finally:
        audio.stop()
        cv2.destroyAllWindows()
        print(f"[demo] underruns: {audio.underruns}, callback error: {audio.callback_error}")


if __name__ == "__main__":
    main()
