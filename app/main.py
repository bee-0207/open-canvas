"""Open Canvas main loop: camera -> markers + fingertip -> (u, v) -> lookup -> audio + motor.

Usage (from the repo root, venv active; note the -m):
    python -m app.main                                   # settings from app/config.yaml
    python -m app.main --camera 1 --serial /dev/cu.usbserial-0001

Per camera frame (~30 Hz):
    1. markers.update(frame)    homography H, camera px -> painting (u, v); reused when hidden
    2. hand.detect(frame)       index fingertip (landmark 8) in camera px
    3. apply H, tip offset, light smoothing -> (u, v); outside the painting = finger lifted
    4. lookup.sample(u, v)      HSL color, region ID, edge flag (from content/, not the webcam)
    5. audio.update(...)        music + object sounds (EE #2's engine, agreed API)
    6. motor on/off             edge flag with hysteresis, sent to the ESP32 only on change
    7. resting the finger still ~2.5 s on a region speaks it (handled inside the audio engine)
    8. first touch after welcome_idle_s with no finger on the painting -> spoken overview,
       so a blind visitor never needs the keyboard: they just put a hand on the painting

Painting library (content/library.yaml, app/library.py): each printed page has its own 4
marker IDs. When a different page appears under the camera, main switches to that painting
and speaks its overview. Before any page is recognized it asks (aloud) for one.

Window keys:
    d   describe the spot under the finger now
    o   spoken overview of the whole painting (also plays on its own, see step 8)
    q   quit (also Esc)
"""

import argparse
import os
import subprocess
import time

import cv2
import numpy as np
import yaml

from app.audio.engine import AudioEngine
from app.hand import HAND_CONNECTIONS, FingertipTracker
from app.library import Library
from app.lookup import Lookup
from app.markers import MarkerLayout, MarkerTracker
from app.serial_link import NullLink, SerialLink

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
GREEN, ORANGE, RED, YELLOW, BLUE = (0, 200, 0), (0, 140, 255), (0, 0, 255), (0, 220, 255), (255, 140, 0)


def put_text(img, text, org, scale=0.6, color=(255, 255, 255)):
    """Text with a black outline so it stays readable on any background."""
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def load_settings():
    with open(CONFIG) as f:
        cfg = yaml.safe_load(f)
    ap = argparse.ArgumentParser(description="Open Canvas main loop")
    ap.add_argument("--camera", type=int, default=cfg["camera"]["index"])
    ap.add_argument("--serial", default=cfg["serial"]["port"], help="ESP32 port; omit for keyboard-only")
    ap.add_argument("--width-mm", type=float, default=cfg["print"]["width_mm"])
    ap.add_argument("--height-mm", type=float, default=cfg["print"]["height_mm"])
    ap.add_argument("--no-window", action="store_true", help="no debug window (quit with Ctrl+C)")
    args = ap.parse_args()
    return args, cfg


class Camera:
    """cv2.VideoCapture that reopens itself after a USB dropout instead of ending the demo."""

    def __init__(self, index, width, height):
        self.index, self.width, self.height = index, width, height
        self.cap = self._open()
        # On an app's first run macOS shows the camera permission prompt and the first open
        # fails; keep retrying while the user answers it instead of quitting.
        for _ in range(30):
            if self.cap.isOpened():
                break
            time.sleep(1.0)
            self.cap = self._open()
        if not self.cap.isOpened():
            subprocess.run(["say", "Open Canvas can't use the camera. Check that it is plugged in and allowed."])
            raise SystemExit(f"Couldn't open camera {index}. On macOS, check camera permission "
                             f"(System Settings > Privacy & Security > Camera).")
        print(f"[camera] {index}: {int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
              f"{int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        self._down_since = None

    def _open(self):
        cap = cv2.VideoCapture(self.index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return cap

    def read(self):
        """Returns a frame, or None while the camera is gone (keeps retrying, never quits)."""
        ok, frame = self.cap.read()
        if ok:
            if self._down_since is not None:
                print(f"[camera] back after {time.monotonic() - self._down_since:.1f} s")
                self._down_since = None
            return frame
        if self._down_since is None:
            self._down_since = time.monotonic()
            print("[camera] frame grab failed, reconnecting...")
        self.cap.release()
        time.sleep(0.5)
        self.cap = self._open()
        return None

    def release(self):
        self.cap.release()


class EdgeMotor:
    """Edge flag -> motor state with hysteresis: switch only after `frames` frames agree."""

    def __init__(self, link, frames):
        self.link, self.frames = link, frames
        self.on, self._count = False, 0

    def update(self, on_edge):
        if on_edge == self.on:
            self._count = 0
        else:
            self._count += 1
            if self._count >= self.frames:
                self.on, self._count = on_edge, 0
        self.link.set_motor(self.on)  # SerialLink only sends when this changes

    def off(self):
        self.on, self._count = False, 0
        self.link.set_motor(False)


def draw_debug(frame, det, markers, tip, painting, state):
    """Camera view (left) + painting with the fingertip dot (right), with a status line."""
    view = frame.copy()
    if markers.H is not None:
        outline = markers.uv_to_camera([[0, 0], [1, 0], [1, 1], [0, 1]])
        cv2.polylines(view, [outline.astype(np.int32)], True, GREEN if det.updated else ORANGE, 2)
    if tip is not None:
        pts = tip.landmarks.astype(np.int32)
        for a, b in HAND_CONNECTIONS:
            cv2.line(view, tuple(pts[a]), tuple(pts[b]), BLUE, 2)
        cv2.circle(view, (int(tip.x), int(tip.y)), 8, RED, -1)
    h_state = "live" if det.updated else ("reused" if markers.H is not None else "NONE (need all 4 markers)")
    put_text(view, f"markers {len(det.corners)}/4   H {h_state}", (10, 25))

    # Right panel: the clean painting scaled to the camera view's height
    ph = view.shape[0]
    pw = int(painting.shape[1] * ph / painting.shape[0])
    panel = cv2.resize(painting, (pw, ph))
    uv = state.get("uv")
    if uv is not None:
        cv2.circle(panel, (int(uv[0] * pw), int(uv[1] * ph)), 10, RED if state["motor"] else YELLOW, -1)
        put_text(panel, f"u={uv[0]:.2f} v={uv[1]:.2f}  {state['region']}", (10, 25))
        if state["motor"]:
            put_text(panel, "EDGE: motor on", (10, 55), color=RED)
    else:
        put_text(panel, "finger lifted / off painting", (10, 25))
    out = np.hstack([view, panel])
    put_text(out, state["status"], (10, out.shape[0] - 15))
    return cv2.resize(out, (out.shape[1] * 2 // 3, out.shape[0] * 2 // 3))


def load_print(pr, old_audio):
    """Switch to one printed painting: its lookup maps, marker tracker and audio engine.

    The audio engine is rebuilt per painting (its regions, object sounds and voice clips all
    change); building one takes well under 0.1 s, so switching is quick.
    """
    if old_audio is not None:
        old_audio.stop()
    lookup = Lookup(pr.painting.content)
    ph, pw = lookup.painting.shape[:2]
    lw, lh = pr.layout.painting_w_mm, pr.layout.painting_h_mm
    if abs((lw / lh) / (pw / ph) - 1) > 0.03:
        print(f"[warn] {pr.painting.slug}: print is {lw:.0f}x{lh:.0f} mm but painting.png is {pw}x{ph} px: "
              f"different shapes, so (u, v) will be stretched.")
    markers = MarkerTracker(pr.layout, pr.ids)
    audio = AudioEngine(content=pr.painting.content, voice=pr.painting.voice,
                        crop_fn=lookup.crop)  # crop_fn feeds the AI describer on hover
    audio.start()
    audio.play_overview()   # the overview starts by naming the painting
    print(f"[library] now showing {pr.painting.title} ({pr.kind} print, markers {list(pr.ids)})")
    return lookup, markers, audio


def main():
    args, cfg = load_settings()
    tune = cfg["tuning"]
    p = cfg["print"]

    board = MarkerLayout(args.width_mm, args.height_mm, p["marker_mm"], p["gap_mm"])
    library = Library.load(board)
    print(f"[library] {len(library.prints)} prints: " + ", ".join(
        f"{pr.painting.slug} {list(pr.ids)}" for pr in library.prints))

    hand = FingertipTracker(min_confidence=tune["min_confidence"])
    cam = Camera(args.camera, cfg["camera"]["width"], cfg["camera"]["height"])
    link = SerialLink(args.serial) if args.serial else NullLink()
    if not args.serial:
        print("[serial] no ESP32 port set: motor is simulated, press d to describe")
    motor = EdgeMotor(link, tune["edge_frames"])

    # Nothing is loaded until a painting is recognized. Until then this tracker only reports
    # which marker IDs are in view (Detection.seen); its layout doesn't matter.
    active, lookup, audio = None, None, None
    markers = MarkerTracker(library.prints[0].layout, library.prints[0].ids)
    cand, cand_frames = None, 0  # painting seen but not switched to yet (debounce)
    t_start, prompted = time.monotonic(), False

    uv = None                    # smoothed (u, v), None = finger lifted / off painting
    press_t, fired = None, False  # arcade button state
    fps, t_prev = 0.0, time.perf_counter()
    margin = tune["off_margin"]
    last_touch = None            # monotonic time the finger was last on the painting; None = never
    try:
        while True:
            frame = cam.read()
            if frame is None:
                # Camera gone: silence the object sounds and the motor until it comes back
                if audio is not None:
                    audio.update(0, 0, (0, 0, 0), 0, False)
                motor.off()
                if not args.no_window and cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
                continue

            det = markers.update(frame)
            now = time.monotonic()

            # Which painting is on the table? Switch only after switch_frames frames in a row
            # agree, so a hand sweeping over the markers can't flip paintings by accident.
            seen = library.identify(det.seen)
            if seen is not None and seen is not active:
                cand_frames = cand_frames + 1 if seen is cand else 1
                cand = seen
                if cand_frames >= tune["switch_frames"]:
                    motor.off()
                    lookup, markers, audio = load_print(seen, audio)
                    active, cand, cand_frames, uv = seen, None, 0, None
                    last_touch = now   # the overview just played; the first touch shouldn't repeat it
                    continue           # this frame's detection belonged to the old tracker
            else:
                cand, cand_frames = None, 0

            if active is None:
                # No painting recognized yet: tell a blind user what to do, once, after a few seconds
                if not prompted and now - t_start > tune["prompt_after_s"]:
                    prompted = True
                    print("[library] no painting in view yet")
                    subprocess.Popen(["say", "Open Canvas is ready. Place a painting under the camera."])
                if not args.no_window:
                    view = frame.copy()
                    put_text(view, f"looking for a painting... marker IDs in view: {sorted(det.seen) or 'none'}", (10, 25))
                    cv2.imshow("Open Canvas", cv2.resize(view, (view.shape[1] * 2 // 3, view.shape[0] * 2 // 3)))
                    if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                        break
                continue

            tip = hand.detect(frame)

            # Fingertip -> painting (u, v)
            raw = None
            if tip is not None and markers.H is not None:
                x, y = tip.x, tip.y
                if tune["tip_offset"]:
                    # Pull the point back from the nail tip (landmark 8) toward the next joint (7)
                    x7, y7 = tip.landmarks[7]
                    x += tune["tip_offset"] * (x7 - x)
                    y += tune["tip_offset"] * (y7 - y)
                u, v = markers.camera_to_uv(x, y)
                if -margin <= u <= 1 + margin and -margin <= v <= 1 + margin:
                    raw = (min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0))

            if raw is None:
                uv = None
            elif uv is None:
                uv = raw  # fresh touch: no smoothing against a stale position
            else:
                a = tune["smoothing"]
                uv = (a * raw[0] + (1 - a) * uv[0], a * raw[1] + (1 - a) * uv[1])

            # Welcome: a new visitor (first touch, or after welcome_idle_s untouched) hears the overview
            if uv is not None:
                if last_touch is None or now - last_touch >= tune["welcome_idle_s"]:
                    print("[welcome] new visitor -> overview")
                    audio.play_overview()
                last_touch = now

            # Lookup -> audio + motor
            region = ""
            if uv is not None:
                hsl, rid, on_edge = lookup.sample(*uv)
                audio.update(uv[0], uv[1], hsl, rid, True)
                motor.update(on_edge)
                region = audio.region_name(rid) or "background"
            else:
                audio.update(0, 0, (0, 0, 0), 0, False)
                motor.off()

            # Button: describe after a hold of hold_s (a quick tap is ignored)
            for ev in link.poll():
                print(f"[button] {'pressed' if ev == 'B1' else 'released'}")
                if ev == "B1":
                    press_t, fired = now, False
                else:
                    press_t = None
            if press_t is not None and not fired and now - press_t >= tune["hold_s"] and uv is not None:
                audio.describe(lookup.crop(*uv))
                fired = True

            t = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(t - t_prev, 1e-6)
            t_prev = t
            if args.no_window:
                continue
            status = (f"{fps:.0f} fps   {active.painting.slug}   motor {'ON' if motor.on else 'off'}"
                      f"   d describe  o overview  q quit")
            state = {"uv": uv, "region": region, "motor": motor.on, "status": status}
            cv2.imshow("Open Canvas", draw_debug(frame, det, markers, tip, lookup.painting, state))
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("d") and uv is not None:
                audio.describe(lookup.crop(*uv))
            elif key == ord("o"):
                audio.play_overview()
    except KeyboardInterrupt:
        pass
    finally:
        motor.off()
        link.close()
        if audio is not None:
            audio.stop()
        hand.close()
        cam.release()
        cv2.destroyAllWindows()
        if audio is not None and (audio.underruns or audio.callback_error):
            print(f"[audio] underruns {audio.underruns}, callback error {audio.callback_error}")


if __name__ == "__main__":
    main()
