"""
engine.py: the real-time layered audio engine (CLAUDE.md sections 6, 7 and 11).

Think of it as a small mixing console that the main loop drives:

    main loop (~30 Hz camera rate): lookup.py gives (u, v), hsl, region_id
          │  audio.update(u, v, hsl, region_id, finger_present)   once per frame
          │  audio.describe(crop_image)                            on button hold
    ──────┼──────────────────────────────────────────────────────────────────────
          ▼  audio thread (48 kHz, 512-sample blocks)
    Layer 2  music stems (instrument x low/high) ──┐
    Layer 3  object sound (one per region)  ───────┼─ x duck ─ pan ─┐
                                                                    ├─ master ─ soft clip ─> headphones
    Layer 1/4  voice (overview, descriptions) ──────────────────────┤   (voice and chime centered)
    Layer 4  chime ─────────────────────────────────────────────────┘

Agreed API (CLAUDE.md section 7). Don't change it without the team:

    audio.update(u, v, hsl, region_id, finger_present)  # called once per frame
    audio.describe(crop_image)                           # on button hold

    u, v           normalized painting coords in [0, 1], origin top-left
    hsl            (hue degrees 0..360, saturation 0..1, lightness 0..1)  <- proposed, confirm with CE
    region_id      int from content/regions.png, 0 = background/none
    finger_present False when MediaPipe finds no fingertip this frame
    crop_image     square crop around the fingertip from content/painting.png (not the webcam)

Extras outside the contract: start(), stop(), play_overview(), say(audio, sr), render(seconds).
The button's hold timing lives in the main loop: the contract calls describe() "on hold".

Hover-to-speak (team request, Oct 24): if the finger rests still (within HOVER_RADIUS) on
one region for HOVER_TIME seconds, update() itself starts that region's description, with no
chime. Gliding across a region doesn't count: moving more than HOVER_RADIUS restarts the timer. The camera
already tracks the finger, so this needs nothing new from the main loop; describe() on the
button still works. Pass crop_fn=(u, v) -> crop_image to give the AI describer a crop on hover.

Design rules (CLAUDE.md section 11, "Audio thread"):
- The audio callback never blocks, never touches files or the network, and never waits on
  a lock. All assets are loaded and resampled up front. The main loop hands over a fresh,
  immutable Control object by plain attribute assignment, which is atomic in CPython.
- The vision AI + TTS call in describe() runs on a worker thread.
- Every gain change is smoothed (one-pole low-pass, ramped across each block). An
  unsmoothed gain step is a step in the waveform's envelope, which you hear as a click
  ("zipper noise").
- Edges are NOT handled here. Edges are felt (fingertip motor), never heard.
"""

import json
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

from .color_map import INSTRUMENTS, color_weights_hsl, instrument_gain, register_mix

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ----------------------------------------------------------------------------- config
SR = 48000            # sample rate (Hz)
BLOCK = 512           # frames per audio callback: 10.7 ms at 48 kHz. Raise to 1024 if you hear crackles.

# Levels (linear gain). Rough guide: 0.5 = -6 dB, 0.33 = -9.6 dB.
MASTER = 0.9
MUSIC_LEVEL = 0.7       # lowered Oct 24 (was 1.0, about -3 dB): music sat too loud under the voice and objects
OBJECT_LEVEL = 0.9
VOICE_LEVEL = 1.0
CHIME_LEVEL = 0.6
IDLE_MUSIC_LEVEL = 0.45   # music level while no finger is on the painting
DUCK = 0.33               # music + objects drop to about 1/3 under the voice (team spec)

# Time constants (seconds) for the one-pole smoothers. tau = time to reach ~63%.
TAU_INSTR = 0.08      # instrument gains follow color changes quickly
TAU_PAN = 0.06
TAU_LEVEL = 0.30      # touch/lift fade
TAU_OBJ_IN = 0.15     # new object sound fades in fast...
TAU_OBJ_OUT = 0.45    # ...the old one lingers a little (sounds more natural)
TAU_DUCK_ATTACK = 0.05
TAU_DUCK_RELEASE = 0.50

# Control-side timing (seconds)
REGION_DWELL = 0.12   # finger must stay in a new region this long before its sound switches (hysteresis)
LIFT_GRACE = 0.35     # MediaPipe drops frames; wait this long before treating "no finger" as lifted
CHIME_TO_VOICE = 0.35 # gap between chime and voice; also masks the AI round trip
AI_TIMEOUT = 8.0      # stay ducked this long waiting for an AI description, then give up
HOVER_TIME = 2.5      # finger rests still on one region this long -> its description plays
HOVER_RADIUS = 0.04   # "still" = within this (u, v) distance of where the rest began (~1 cm on Letter)
HOVER_REPEAT = 20.0   # don't repeat the same region's description sooner than this
HOVER_GAP = 0.12      # short pause so the music has ducked before the first word
USE_CHIME = False     # chime before a button describe(); the team chose speech only

PAN_WIDTH = 0.75      # 1.0 = hard left/right at the painting edges; <1 is easier on headphones

TARGET_RMS = {"music": 0.10, "object": 0.08, "voice": 0.12}


# ----------------------------------------------------------------------------- audio file helpers
def resample(x, sr_in, sr_out=SR):
    """Linear-interpolation resampler (numpy only, so no scipy dependency). Fine for
    speech and ambience. For music stems, export at 48 kHz so this never runs."""
    if sr_in == sr_out or len(x) == 0:
        return x.astype(np.float32)
    n_out = int(round(len(x) * sr_out / sr_in))
    t = np.arange(n_out) * (sr_in / sr_out)
    return np.interp(t, np.arange(len(x)), x).astype(np.float32)


def load_audio(path, sr=SR):
    """Load a WAV/FLAC/OGG as mono float32 at `sr`."""
    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    # Downmix to mono. Each source is panned as a point by the finger's u position, and a
    # mono source pans cleanly; a stereo recording would keep its own image and blur it.
    mono = data.mean(axis=1)
    if file_sr != sr:
        print(f"[audio] resampling {os.path.basename(path)} {file_sr} -> {sr} Hz "
              f"(export at {sr} Hz to skip this)")
    return resample(mono, file_sr, sr)


def normalize(x, target_rms=None, peak=0.95):
    """Auto-level a clip so swapped-in recordings sit at the same loudness."""
    if target_rms:
        rms = float(np.sqrt(np.mean(x ** 2))) + 1e-12
        x = x * (target_rms / rms)
    p = float(np.max(np.abs(x))) + 1e-12
    if p > peak:                       # never let a single clip exceed `peak`
        x = x * (peak / p)
    return x.astype(np.float32)


def make_seamless(x, fade_s, sr=SR):
    """Crossfade the tail into the head so the loop point doesn't click.
    Output is shorter by the fade length. If every music stem has the same length,
    they all shrink by the same amount and stay in sync."""
    n = int(fade_s * sr)
    if n <= 0 or len(x) < 3 * n:
        return x
    t = np.linspace(0, 1, n, dtype=np.float32)
    head, tail = x[:n], x[-n:]
    out = x[:-n].copy()
    # Equal-power crossfade, because the head and tail are uncorrelated material.
    out[:n] = head * np.sin(t * np.pi / 2) + tail * np.cos(t * np.pi / 2)
    return out


# ----------------------------------------------------------------------------- DSP building blocks
class Smoother:
    """One-pole low-pass on a control value, ramped linearly within each block.
    Per block: y += a * (target - y), with a = 1 - exp(-N / (tau * SR)).
    This is the discrete-time version of an RC filter with time constant tau.
    tau_down lets falling values use a different time constant (attack vs. release)."""

    def __init__(self, value=0.0, tau=0.1, tau_down=None):
        self.y = float(value)
        self.tau_up = tau
        self.tau_down = tau_down if tau_down is not None else tau

    def step(self, target, n):
        tau = self.tau_up if target > self.y else self.tau_down
        a = 1.0 - math.exp(-n / (tau * SR))
        y0, self.y = self.y, self.y + a * (target - self.y)
        if abs(self.y - y0) < 1e-7:
            return None, self.y              # constant across the block: caller skips the ramp
        return np.linspace(y0, self.y, n, endpoint=False, dtype=np.float32) + (self.y - y0) / n, self.y


class Loop:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def read(self, n):
        idx = (self.pos + np.arange(n)) % len(self.data)
        self.pos = (self.pos + n) % len(self.data)
        return self.data[idx]


class OneShot:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    @property
    def done(self):
        return self.pos >= len(self.data)

    def read(self, n):
        seg = self.data[self.pos:self.pos + n]
        self.pos += n
        if len(seg) < n:
            seg = np.concatenate([seg, np.zeros(n - len(seg), np.float32)])
        return seg


def gain(ramp_and_value, x):
    ramp, value = ramp_and_value
    return x * (ramp if ramp is not None else value)


def soft_clip(x, knee=0.8):
    """Linear below `knee`, then tanh-curves smoothly up to 1.0. A safety net: it keeps
    a loud moment from hard-clipping (harsh) in someone's headphones."""
    a = np.abs(x)
    over = a > knee
    if over.any():
        x = x.copy()
        x[over] = np.sign(x[over]) * (knee + (1 - knee) * np.tanh((a[over] - knee) / (1 - knee)))
    return x.astype(np.float32)


@dataclass(frozen=True)
class Control:
    """Snapshot handed from the main loop to the audio thread. Immutable on purpose."""
    g_low: dict = field(default_factory=dict)    # instrument -> target gain (low register stem)
    g_high: dict = field(default_factory=dict)   # instrument -> target gain (high register stem)
    pan: float = 0.0                             # -1 left .. +1 right
    obj_key: str = ""                            # which object loop is active ("" = none)
    music_level: float = IDLE_MUSIC_LEVEL


# ----------------------------------------------------------------------------- engine
class AudioEngine:
    def __init__(self, content=os.path.join(REPO, "content"), sounds=os.path.join(REPO, "assets", "sounds"),
                 root=REPO, describer=None, crop_fn=None, hover=True, verbose=True):
        """
        content:   folder with regions.json (contract format, CLAUDE.md section 7)
        sounds:    folder with music/<inst>_low.wav + music/<inst>_high.wav, ui/chime.wav,
                   voice/overview.wav and voice/region_<id>.wav (pre-rendered descriptions)
        root:      base for the relative `sound_file` paths in regions.json (repo root)
        describer: optional function (crop_image, region_id, region_info) -> (audio_float32, sr)
                   or None. This is the vision AI + TTS step; it runs on a worker thread, and
                   the chime and ducking cover the wait. If it is None, fails, or returns
                   None, the region's pre-rendered description is spoken instead.
        crop_fn:   optional function (u, v) -> crop_image, used to feed the describer on hover
        hover:     speak a region's description after the finger rests on it for HOVER_TIME
        """
        self.verbose = verbose
        self.describer = describer
        self.crop_fn = crop_fn
        self.hover = hover
        self.regions = self._load_regions(os.path.join(content, "regions.json"))

        # --- Layer 2: music stems ---
        self.stems = {}       # inst -> (Loop low, Loop high)
        for inst in INSTRUMENTS:
            lo = os.path.join(sounds, "music", f"{inst}_low.wav")
            hi = os.path.join(sounds, "music", f"{inst}_high.wav")
            if os.path.exists(lo) and os.path.exists(hi):
                self.stems[inst] = tuple(
                    Loop(make_seamless(normalize(load_audio(p), TARGET_RMS["music"]), 0.005))
                    for p in (lo, hi))
            else:
                self._log(f"[audio] missing stems for {inst}, it will be silent")
        self.sm_low = {k: Smoother(0.0, TAU_INSTR) for k in self.stems}
        self.sm_high = {k: Smoother(0.0, TAU_INSTR) for k in self.stems}

        # --- Layer 3: object sounds (several regions can share one file) ---
        self.objects = {}     # key (sound_file as written) -> Loop
        self.region_obj = {}  # region id -> key
        for rid, info in self.regions.items():
            rel = info.get("sound_file")
            if not rel:
                continue
            if rel not in self.objects:
                p = os.path.join(root, rel)
                if not os.path.exists(p):
                    self._log(f"[audio] missing object sound {p}")
                    continue
                x = normalize(load_audio(p), TARGET_RMS["object"])
                x *= 10 ** (info.get("gain_db", 0.0) / 20)   # optional per-sound trim in regions.json
                self.objects[rel] = Loop(make_seamless(x, 0.25))
            self.region_obj[rid] = rel
        self.sm_obj = {k: Smoother(0.0, TAU_OBJ_IN, TAU_OBJ_OUT) for k in self.objects}

        # --- Layer 4 / Layer 1: chime + voice ---
        chime_p = os.path.join(sounds, "ui", "chime.wav")
        self.chime_data = normalize(load_audio(chime_p)) if os.path.exists(chime_p) else None
        self.voice_clips = {}   # "overview" or region id -> float32 array
        for key, name in [("overview", "overview.wav")] + [(rid, f"region_{rid}.wav") for rid in self.regions]:
            p = os.path.join(sounds, "voice", name)
            if os.path.exists(p):
                self.voice_clips[key] = normalize(load_audio(p), TARGET_RMS["voice"])

        self._chime = None                 # OneShot, assigned by describe()
        self._voice = None                 # OneShot currently playing (audio thread owns it)
        self._voice_q = deque()            # pending clips (deque append/popleft are thread-safe)
        self._voice_stop = False
        self._pending_until = 0.0          # audio-clock time; stay ducked while the AI is thinking
        self._describe_gen = 0             # increments to cancel stale AI results

        # --- mix-bus smoothers ---
        self.sm_pan = Smoother(0.0, TAU_PAN)
        self.sm_level = Smoother(IDLE_MUSIC_LEVEL, TAU_LEVEL)
        # Smoother(value, tau when rising, tau when falling). Ducking FALLS fast (attack, so
        # the voice is never buried) and RISES slowly (release, so the music swells back in).
        self.sm_duck = Smoother(1.0, TAU_DUCK_RELEASE, TAU_DUCK_ATTACK)

        # --- main-loop state ---
        self.audio_time = 0.0
        self._last_seen = None
        self._present = False
        self._region = 0                   # region whose object sound is playing (after dwell)
        self._rid_now = 0                  # region directly under the finger this frame
        self._cand, self._cand_since = 0, 0.0
        self._hover_rid, self._hover_since, self._hover_fired = 0, 0.0, False
        self._hover_uv = (0.0, 0.0)        # where the current rest began
        self._last_spoken = {}             # region id -> time its description last played
        self._now = 0.0                    # time of the last update() (same clock as `now`)
        self._overview_until = 0.0         # audio-clock time the overview ends (hover waits)
        self.state = {}                    # last update, for HUDs / debugging
        self.underruns = 0
        self.callback_error = None
        self._stream = None
        self._ctl = self._lifted_control()

    def _log(self, *a):
        if self.verbose:
            print(*a)

    def _load_regions(self, path):
        """content/regions.json -> {int region id: info dict}. Missing file -> no regions."""
        if not os.path.exists(path):
            self._log(f"[audio] no {path}; object sounds and descriptions are off")
            return {}
        with open(path) as f:
            data = json.load(f)
        return {int(k): v for k, v in data.items() if str(k).isdigit()}

    def region_name(self, rid):
        return self.regions.get(rid, {}).get("name", "" if rid == 0 else f"region {rid}")

    # ========================================================================= main-loop side
    def _lifted_control(self):
        lo, hi = register_mix(0.5)
        g = instrument_gain(0.0)     # every instrument at its quiet bed
        return Control(g_low={k: g * lo for k in self.stems}, g_high={k: g * hi for k in self.stems},
                       pan=0.0, obj_key="", music_level=IDLE_MUSIC_LEVEL)

    def update(self, u, v, hsl, region_id, finger_present, now=None):
        """Call once per camera frame (contract). `now` is for offline tests only."""
        now = time.monotonic() if now is None else now
        self._now = now
        if not finger_present:
            if self._last_seen is not None and now - self._last_seen < LIFT_GRACE:
                return                # brief tracking dropout: keep the last state
            if self._present:         # transition to lifted
                self._present, self._region, self._cand, self._rid_now = False, 0, 0, 0
                self._hover_rid, self._hover_fired = 0, False
                self._ctl = self._lifted_control()
                self.state = {"lifted": True}
            return

        rid = int(region_id)
        first_touch = not self._present
        self._last_seen, self._present = now, True
        self._rid_now = rid
        h, s, l = hsl
        w = color_weights_hsl(h, s, l)

        # Region hysteresis (like a Schmitt trigger in time): only switch the object sound
        # after the finger has stayed in the new region for REGION_DWELL seconds, so a finger
        # resting on a boundary doesn't flip-flop between two sounds. A fresh touch has
        # nothing to flip-flop against, so it switches at once.
        if first_touch:
            self._region = self._cand = rid
        elif rid == self._region:
            self._cand = rid
        elif rid != self._cand:
            self._cand, self._cand_since = rid, now
        elif now - self._cand_since >= REGION_DWELL:
            self._region = rid

        lo, hi = register_mix(l)
        g = {k: instrument_gain(w[k]) for k in self.stems}
        self._ctl = Control(
            g_low={k: g[k] * lo for k in self.stems},
            g_high={k: g[k] * hi for k in self.stems},
            pan=PAN_WIDTH * (2.0 * u - 1.0),
            obj_key=self.region_obj.get(self._region, ""),
            music_level=1.0,
        )
        self.state = {"uv": (u, v), "hsl": (h, s, l), "weights": w,
                      "region": self._region, "region_name": self.region_name(self._region),
                      "hover": self._update_hover(u, v, now)}

    def _update_hover(self, u, v, now):
        """Hover-to-speak. Uses the debounced region (self._region), so jitter on a boundary
        doesn't restart the timer, and the finger must also stay within HOVER_RADIUS of where
        it stopped, so gliding through a region doesn't count. Returns hover progress 0..1
        for HUDs (1 = spoken)."""
        if not self.hover:
            return 0.0
        moved = np.hypot(u - self._hover_uv[0], v - self._hover_uv[1]) > HOVER_RADIUS
        if self._region != self._hover_rid or moved:   # new region or finger moving: restart the timer
            self._hover_rid, self._hover_since, self._hover_fired = self._region, now, False
            self._hover_uv = (u, v)
        if self._hover_rid == 0 or self._hover_fired:
            return 1.0 if self._hover_fired else 0.0
        progress = min((now - self._hover_since) / HOVER_TIME, 1.0)
        recent = now - self._last_spoken.get(self._hover_rid, -1e9) < HOVER_REPEAT
        if progress >= 1.0 and not recent and self.audio_time >= self._overview_until:
            self._hover_fired = True
            self._last_spoken[self._hover_rid] = now
            self._log(f"[audio] hover {HOVER_TIME:g} s -> describing {self.region_name(self._hover_rid)}")
            crop = self.crop_fn(u, v) if self.crop_fn is not None else None
            self._describe_region(self._hover_rid, crop, chime=False)
        return progress

    def _stop_voice(self):
        self._voice_q.clear()
        self._voice_stop = True

    def play_overview(self):
        """Layer 1: spoken overview of the whole scene. Who triggers it is an open question."""
        self._stop_voice()
        clip = self.voice_clips.get("overview")
        if clip is None:
            self._log("[audio] no voice/overview.wav")
            return
        self._voice_q.append(clip)
        self._overview_until = self.audio_time + len(clip) / SR

    def describe(self, crop_image):
        """Layer 4 (contract): duck the bed, then speak about the spot under the finger
        (with a chime first if USE_CHIME)."""
        self._last_spoken[self._rid_now] = self._now   # hover won't repeat it right away
        self._describe_region(self._rid_now, crop_image, chime=USE_CHIME)

    def _describe_region(self, rid, crop_image, chime):
        self._stop_voice()
        self._overview_until = 0.0          # a description replaces the overview
        self._describe_gen += 1
        gen = self._describe_gen
        if chime and self.chime_data is not None:
            self._chime = OneShot(self.chime_data)
        gap = np.zeros(int((CHIME_TO_VOICE if chime else HOVER_GAP) * SR), np.float32)
        info = self.regions.get(rid, {})
        fallback = self.voice_clips.get(rid)

        if self.describer is not None and crop_image is not None:
            self._pending_until = self.audio_time + AI_TIMEOUT

            def work():
                try:
                    res = self.describer(crop_image, rid, info)
                except Exception as e:            # network down, API error, ...
                    self._log(f"[audio] describer failed: {e}")
                    res = None
                if gen != self._describe_gen:     # user already asked again; drop the stale answer
                    return
                self._pending_until = 0.0
                if res is not None:
                    self.say(*res)
                elif fallback is not None:
                    self._voice_q.append(np.concatenate([gap, fallback]))
            threading.Thread(target=work, daemon=True).start()
        elif fallback is not None:
            self._voice_q.append(np.concatenate([gap, fallback]))
        else:
            self._log(f"[audio] no description for region {rid}")

    def say(self, audio, sr=SR):
        """Queue arbitrary speech (e.g. TTS of an AI answer). audio: float32 mono or stereo array."""
        x = np.asarray(audio, dtype=np.float32)
        if x.ndim > 1:
            x = x.mean(axis=1)
        self._voice_q.append(normalize(resample(x, sr), TARGET_RMS["voice"]))

    # ========================================================================= audio side
    def _process(self, n):
        """Produce n stereo frames. Called from the audio callback (or render())."""
        ctl = self._ctl                                   # one atomic read per block

        # Layer 2: music
        music = np.zeros(n, np.float32)
        for inst, (lo, hi) in self.stems.items():
            a = self.sm_low[inst].step(ctl.g_low.get(inst, 0.0), n)
            b = self.sm_high[inst].step(ctl.g_high.get(inst, 0.0), n)
            music += gain(a, lo.read(n)) + gain(b, hi.read(n))
        music = gain(self.sm_level.step(ctl.music_level, n), music) * MUSIC_LEVEL

        # Layer 3: object sounds. Only mix loops that are audible, but advance all of them so
        # a sound you return to has moved on (more natural).
        objs = np.zeros(n, np.float32)
        for key, loop in self.objects.items():
            r = self.sm_obj[key].step(1.0 if key == ctl.obj_key else 0.0, n)
            seg = loop.read(n)
            if self.sm_obj[key].y > 1e-4 or r[0] is not None:
                objs += gain(r, seg)
        bed = music + objs * OBJECT_LEVEL

        # Layer 4 + 1: voice (centered)
        if self._voice_stop:
            self._voice, self._voice_stop = None, False
        if self._voice is None and self._voice_q:
            self._voice = OneShot(self._voice_q.popleft())
        voice = np.zeros(n, np.float32)
        if self._voice is not None:
            voice = self._voice.read(n)
            if self._voice.done:
                self._voice = None
        chime = np.zeros(n, np.float32)
        ch = self._chime
        if ch is not None:
            chime = ch.read(n)
            if ch.done:
                self._chime = None

        # Ducking: stay down while the chime, voice, queued voice, or a pending AI answer exists.
        talking = (self._voice is not None or bool(self._voice_q) or self._chime is not None
                   or self.audio_time < self._pending_until)
        bed = gain(self.sm_duck.step(DUCK if talking else 1.0, n), bed)

        # Equal-power pan: theta 0..pi/2 maps to L = cos, R = sin, so L^2 + R^2 = 1 and loudness
        # stays constant across the sweep. A linear pan dips about 3 dB in the middle.
        pr, pv = self.sm_pan.step(ctl.pan, n)
        p = pr if pr is not None else pv
        theta = (np.asarray(p) + 1.0) * (np.pi / 4)
        left = bed * np.cos(theta)
        right = bed * np.sin(theta)

        center = (voice * VOICE_LEVEL + chime * CHIME_LEVEL) * 0.7071
        out = np.stack([left + center, right + center], axis=1) * MASTER

        self.audio_time += n / SR
        return soft_clip(out)

    def render(self, seconds):
        """Offline render (no sound card needed). Used by tools/fake_inputs.py and tests."""
        n_blocks = int(seconds * SR / BLOCK)
        return np.concatenate([self._process(BLOCK) for _ in range(n_blocks)])

    def start(self, device=None):
        import sounddevice as sd

        def cb(outdata, frames, time_info, status):
            if status.output_underflow:
                self.underruns += 1
            try:
                outdata[:] = self._process(frames)
            except Exception as e:              # never let the stream die silently
                self.callback_error = e
                outdata.fill(0)

        self._stream = sd.OutputStream(samplerate=SR, blocksize=BLOCK, channels=2, dtype="float32",
                                       latency="low", callback=cb, device=device)
        self._stream.start()
        self._log(f"[audio] running: {SR} Hz, block {BLOCK} "
                  f"({1000 * BLOCK / SR:.1f} ms), output latency "
                  f"{1000 * self._stream.latency:.0f} ms")

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
