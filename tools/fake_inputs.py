"""
fake_inputs.py: drive the audio engine without a camera, ESP32, or vision code.

A scripted finger path is sampled at 30 Hz with a little positional jitter and the odd
tracking dropout, like a real webcam + MediaPipe would deliver. It calls the engine
through the agreed API (CLAUDE.md section 7):

    audio.update(u, v, hsl, region_id, finger_present)   every frame
    audio.describe(crop_image)                           once the button has been held ~300 ms

The lookup here (painting.png -> HSL, regions.png -> region id) is a test stand-in for
the CE's app/lookup.py, so the audio side can be built and tuned on its own.

    # render to a WAV (no sound card needed); listen with headphones, panning is stereo
    .venv/bin/python tools/fake_inputs.py --render preview.wav

    # play live through the default output device
    .venv/bin/python tools/fake_inputs.py --live

    # point at test content / sounds kept outside the repo
    .venv/bin/python tools/fake_inputs.py --content ~/feel_sound/content --sounds ~/feel_sound/assets --live

The default path was written for the team painting in content/ (sky on top, sun
right of center behind the big hill, field, sandy path, tree on the left). With another
painting the path still runs; it just crosses different regions.
"""

import argparse
import os
import sys
import time

import cv2
import numpy as np
import soundfile as sf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from app.audio import engine as E                       # noqa: E402
from app.audio.color_map import rgb_to_hsl              # noqa: E402

FPS = 30
JITTER = 0.002        # ~2 px on a 1000 px wide painting, about MediaPipe's fingertip jitter
HOLD_TIME = 0.30      # CLAUDE.md section 11: "hold" means held ~300 ms
CROP_FRAC = 0.12      # crop side as a fraction of the painting width

# (time s, (u, v) or None): the finger script. None = hand lifted.
PATH = [
    (0.0, None), (1.5, None),
    (1.5, (0.45, 0.04)), (3.5, (0.45, 0.04)),      # top of sky: deep blue -> harp, low register
    (9.0, (0.45, 0.45)), (10.0, (0.45, 0.45)),     # slow drag down: blue -> peach glow (harp -> strings)
    (11.5, (0.66, 0.37)), (14.0, (0.66, 0.37)),    # the sun: orange -> strings, high register, cicadas
    (16.0, (0.80, 0.09)), (18.0, (0.80, 0.09)),    # right cloud: white -> choir, birds
    (20.0, (0.85, 0.52)), (22.5, (0.85, 0.52)),    # big hill: blue-green -> harp + woodwind, wind
    (23.5, (0.85, 0.85)), (25.5, (0.85, 0.85)),    # field, far right: yellow-green -> strings, listen to the pan
    (27.0, (0.50, 0.95)), (29.5, (0.50, 0.95)),    # path: sandy tan -> strings (placeholder: crickets)
    (31.0, (0.30, 0.85)), (32.5, (0.30, 0.85)),    # field, left of the path
    (35.0, (0.15, 0.30)), (46.5, (0.15, 0.30)),    # tree crown: dark green -> woodwind + cello, leaves
    (46.5, None), (49.0, None),
]
BUTTON = [(37.0, True), (37.7, False)]             # press-and-hold on the tree -> chime + description


def finger_at(t):
    for (t0, a), (t1, b) in zip(PATH, PATH[1:]):
        if t0 <= t < t1:
            if a is None or b is None:
                return a
            s = (t - t0) / (t1 - t0)
            s = s * s * (3 - 2 * s)                 # ease in/out like a real hand
            return (a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s)
    return PATH[-1][1]


class FakeLookup:
    """Stand-in for app/lookup.py: (u, v) -> (hsl, region_id), plus the describe crop."""

    def __init__(self, content):
        self.painting = cv2.imread(os.path.join(content, "painting.png"), cv2.IMREAD_COLOR)
        self.regions = cv2.imread(os.path.join(content, "regions.png"), cv2.IMREAD_UNCHANGED)
        if self.painting is None:
            print(f"[fake] no {content}/painting.png; using a synthetic color field")
        if self.regions is not None and self.regions.ndim == 3:
            self.regions = self.regions[:, :, 0]

    def sample(self, u, v):
        u, v = min(max(u, 0.0), 1.0), min(max(v, 0.0), 1.0)
        if self.painting is None:
            # Synthetic field: hue sweeps left to right, lighter toward the top.
            hsl = (360.0 * u, 0.6, 0.85 - 0.7 * v)
        else:
            h, w = self.painting.shape[:2]
            b, g, r = self.painting[int(v * (h - 1)), int(u * (w - 1))]
            hsl = rgb_to_hsl((int(r), int(g), int(b)))
        rid = 0
        if self.regions is not None:
            h, w = self.regions.shape[:2]
            rid = int(self.regions[int(v * (h - 1)), int(u * (w - 1))])
        return hsl, rid

    def crop(self, u, v):
        """Square crop around (u, v) from the clean painting, as the CE will pass it."""
        if self.painting is None:
            return None
        h, w = self.painting.shape[:2]
        half = max(8, int(CROP_FRAC * w / 2))
        x, y = int(u * (w - 1)), int(v * (h - 1))
        return self.painting[max(0, y - half):y + half, max(0, x - half):x + half].copy()


def drive(audio, lookup, t, state, rng, dropout):
    """One camera frame at time t: what the CE's main loop will do."""
    uv = finger_at(t)
    present = uv is not None and rng.random() >= dropout
    if present:
        u = uv[0] + rng.normal(0, JITTER)
        v = uv[1] + rng.normal(0, JITTER)
        hsl, rid = lookup.sample(u, v)
        audio.update(u, v, hsl, rid, True, now=t)
        state["uv"] = (u, v)
    else:
        audio.update(0.0, 0.0, None, 0, False, now=t)

    # Button: B1/B0 edges from the ESP32; the main loop fires describe() once per hold.
    while state["btn_i"] < len(BUTTON) and BUTTON[state["btn_i"]][0] <= t:
        down = BUTTON[state["btn_i"]][1]
        state["down_at"] = t if down else None
        state["fired"] = False
        state["btn_i"] += 1
    if state["down_at"] is not None and not state["fired"] and t - state["down_at"] >= HOLD_TIME:
        state["fired"] = True
        u, v = state.get("uv", (0.5, 0.5))
        print(f"  {t:5.2f}s  HOLD -> describe() at region {audio._rid_now} "
              f"({audio.region_name(audio._rid_now) or 'none'})")
        audio.describe(lookup.crop(u, v))

    name = audio.state.get("region_name", "") if audio._present else "(lifted)"
    if name != state["last_name"]:
        print(f"  {t:5.2f}s  {name or '(background)'}")
        state["last_name"] = name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", default=os.path.join(REPO, "content"),
                    help="folder with painting.png, regions.png, regions.json")
    ap.add_argument("--sounds", default=os.path.join(REPO, "assets", "sounds"),
                    help="folder with music/, ui/, voice/")
    ap.add_argument("--root", default=REPO, help="base for sound_file paths in regions.json")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--render", metavar="OUT.wav", help="render offline to a WAV file")
    mode.add_argument("--live", action="store_true", help="play through the default output device")
    ap.add_argument("--overview", action="store_true", help="play the spoken overview first")
    ap.add_argument("--dropout", type=float, default=0.03, help="chance a frame loses the finger")
    args = ap.parse_args()

    content, sounds = os.path.expanduser(args.content), os.path.expanduser(args.sounds)
    audio = E.AudioEngine(content=content, sounds=sounds, root=os.path.expanduser(args.root))
    lookup = FakeLookup(content)
    rng = np.random.default_rng(1)
    state = {"btn_i": 0, "down_at": None, "fired": False, "last_name": None}
    total = PATH[-1][0]
    print(f"[fake] {len(audio.stems)} instruments, {len(audio.objects)} object sounds, "
          f"{len(audio.voice_clips)} voice clips")

    if args.overview:
        audio.play_overview()

    if args.render:
        blocks, frame_idx, cpu = [], -1, []
        for _ in range(int(total * E.SR / E.BLOCK)):
            t = audio.audio_time
            if int(t * FPS) != frame_idx:          # new "camera frame"
                frame_idx = int(t * FPS)
                drive(audio, lookup, t, state, rng, args.dropout)
            t0 = time.perf_counter()
            blocks.append(audio._process(E.BLOCK))
            cpu.append(time.perf_counter() - t0)
        out = np.concatenate(blocks)
        sf.write(args.render, out, E.SR)
        budget = E.BLOCK / E.SR
        print(f"[fake] wrote {args.render}: {len(out) / E.SR:.1f} s, peak {np.max(np.abs(out)):.2f}, "
              f"CPU {1000 * np.mean(cpu):.2f} ms/block avg, {1000 * np.max(cpu):.2f} ms max "
              f"(budget {1000 * budget:.1f} ms)")
    else:
        audio.start()
        t_start = time.monotonic()
        try:
            while (t := time.monotonic() - t_start) < total:
                drive(audio, lookup, t, state, rng, args.dropout)
                time.sleep(1.0 / FPS)
        except KeyboardInterrupt:
            pass
        finally:
            audio.stop()
        print(f"[fake] done; underruns: {audio.underruns}, callback error: {audio.callback_error}")


if __name__ == "__main__":
    main()
