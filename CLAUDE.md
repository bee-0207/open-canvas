# Open Canvas

An interactive system that lets blind and low-vision people explore a painting by touch.
Built for the **Art Hack** track of the **DS+X 2026 hackathon** at Boston University
(Sat Oct 24 – Sun Oct 25, 2026, 24 hours). Team of three active members: one CE, one EE, one BME (EE #1 was a no-show on Oct 24;
those responsibilities moved to the CE).

> Track prompt: "Combine creativity and technology to turn an idea into an interactive
> experience, using generative art, creative AI, or physical computing."

---

## 0. Start here (every teammate, every Claude Code session)

1. **Environment:** if `.venv/` doesn't exist in the repo root, or the check in
   `SETUP.md` step 5 hasn't passed on this machine, follow **`SETUP.md`** exactly before
   writing any code. Python **3.11** only, inside `.venv/`.
2. **Run Python through the venv:** `.venv/bin/python` (macOS/Linux) or
   `.venv\Scripts\python.exe` (Windows). Never install packages into the system Python.
3. **Dependencies:** only what's pinned in `requirements.txt`. Never install
   `opencv-python` (use `opencv-contrib-python` only; see `SETUP.md`). Ask before adding
   a package; pin its exact version if approved.
4. **Stay in your lane:** each person owns the files for their role (section 8). Don't edit
   another role's files or the interface contracts (section 7) without the team agreeing.
5. **Git:** `git pull` before starting. Work on a branch named after your role
   (e.g. `audio`, `firmware`, `content`, `vision`) and open a pull request into `main`.
   Never commit `.venv/`, `.env` (API keys), or video files.
6. **Repo status (Sat Oct 24):** the full pipeline runs live on the demo Mac. Repo:
   https://github.com/bee-0207/open-canvas (public). Where things are:

   | Need | Go to |
   |---|---|
   | Run the whole system | `python -m app.main` (settings in `app/config.yaml`; `--serial <port>` for the Uno/ESP32) |
   | **Build the motor + button circuit** (EE #2) | **`docs/hardware/README.md`** sections 1–5, schematic in `docs/hardware/schematic.svg` |
   | **Finger mount + button placement** (BME) | **`docs/hardware/README.md`** sections 6–7 |
   | Firmware | `firmware/open_canvas_uno/` (Arduino Uno R3, flashed and tested) · `firmware/open_canvas_esp32/` (ESP32 version, in progress). Same serial protocol. |
   | Test audio without a camera | `python tools/mouse_demo.py` |
   | Test camera pieces alone | `python -m tools.test_markers`, `python -m tools.test_hand` |
   | CE progress log + next steps | `PROGRESS.md` |

---

## 1. What it does

A user places their hand on a printed painting. An overhead webcam tracks their index
fingertip, and the system responds to whatever part of the painting is under it:

- **Music**: the color under the finger plays as an instrument (blue = harp, warm = strings,
  pale = choir, dark = cello). Brighter spots play higher. Sound pans left/right with the
  finger's horizontal position.
- **Object sounds**: labeled objects play a matching realistic sound over the music
  (e.g. tree → rustling leaves, field → crickets).
- **Edges are felt, not heard**: a small vibration motor worn on the finger buzzes when the
  finger crosses an outline between objects.
- **Ask about a spot**: pressing and holding an arcade button plays a chime, ducks the music,
  and a voice describes the exact spot being touched (vision AI + text-to-speech).
- **Overview first**: before exploring, a spoken description of the whole scene gives the
  listener a mental map.

**Why it matters:** art is almost always made only to be seen. WHO estimates at least
2.2 billion people have a near or distance vision impairment. Unlike a static audio guide,
Open Canvas lets the user explore on their own, in any order, at their own pace.

---

## 2. System pipeline (finger → sound)

```
 Webcam (overhead)
     │  1280x720 MJPG frames
     ▼
 ArUco detection ──► homography H (camera px → painting coords)
     │                 (reuse last good H when a marker is hidden)
 MediaPipe hand ──► landmark 8 (index fingertip), camera px
     │
     ▼
 Apply H ──► (u, v) normalized painting coords in [0,1]
     │
     ▼
 Lookup at (u, v):
   • color (HSL)            → instrument weights + register
   • region ID              → object sound, description context
   • edge flag              → motor on/off
     │
     ├──► Audio engine (laptop, headphones)
     └──► Serial to ESP32 ──► motor driver ──► fingertip motor
                     ▲
 Arcade button ──────┘  (ESP32 reports press/release over serial)
     press-and-hold → crop around fingertip → vision AI → TTS → voice (music ducks)
```

### Step details

1. **Camera**: Acer 4K webcam looking straight down. Run at **1280x720, MJPG**. Higher
   resolutions drop the frame rate over USB. **Lock autofocus and exposure**, or the camera
   will refocus every time a hand enters the frame.
2. **Hand tracking**: MediaPipe hand landmarks (21 per hand). The index fingertip is
   **landmark 8**. Prefer the MediaPipe Tasks API (`HandLandmarker`); the older
   `mp.solutions.hands` API is deprecated.
3. **Mapping**: four ArUco markers (printed square fiducials OpenCV can detect), one at each
   corner of the print. `cv2.findHomography` builds a 3x3 matrix mapping camera pixels to
   painting coordinates. The camera does not need perfect alignment, and a bumped camera
   recalibrates on its own.
4. **Lookup**: sample the painting image, region map, and edge map at (u, v).
5. **Output**: audio engine on the laptop, plus serial commands to the ESP32 for the motor.
6. **Describe**: on button hold, crop around the fingertip in painting space, send it to a
   vision-capable AI model, speak the answer with TTS.

---

## 3. Parts list

### Ordered (Amazon)

| Part | Seller | Price | Used for |
|---|---|---|---|
| Acer 4K Webcam for PC/Mac | Jinteng Technology | $56.37 | Overhead camera |
| LenTok Overhead Tripod Mount (desk-clamp arm) | SmartYlife | $19.98 | Holding the camera above the print |
| DIANN 10pcs Mini Vibration Motors (coin ERM) | GUWU | $5.99 | Fingertip haptics (spares included) |
| EG STARTS OEM 12x 30mm Push Buttons (arcade) | EG STARTS | $11.99 | "Describe this spot" button (spares included) |
| **Subtotal** | | **$94.33** | before tax/shipping |

With 6.25% MA sales tax, if it was charged: about $100.23.

### Other parts (bought locally or already on hand)

| Part | Source | Notes |
|---|---|---|
| ESP32 dev board | Micro Center Cambridge | Price TBD. Confirm the exact variant (classic ESP32, S3, C3); pin choices differ. |
| PN2222 NPN transistor | On hand | Low-side motor switch |
| 1N4148 diode | On hand | Flyback diode across the motor |
| 220–270 Ω resistor | On hand | Transistor base resistor |
| Hookup wire, connectors, heat-shrink | On hand / Amazon | Adafruit's arcade quick-connect set isn't on Amazon, so use plain wire + crimp connectors or solder |
| USB cables | On hand | Webcam to laptop, ESP32 to laptop |
| Printed painting | Print shop / campus printer | Size TBD; drives camera height |

### Hardware gotchas
- **Vibration motor specs:** the listing gives 3 V coin ERM (eccentric rotating mass) motors,
  but the rated current isn't confirmed. Measure or check before finalizing the base
  resistor. Coin motors typically draw ~60–90 mA. The thin leads break easily at the motor
  body, so add strain relief (tape or heat-shrink) where the wire meets the motor.
- **Arcade buttons:** 30 mm buttons snap into a ~30 mm hole and have a built-in
  microswitch. Check the terminal tab size (commonly 2.8 mm or 4.8 mm) before buying crimp
  connectors. Use the **COM** and **NO** (normally open) terminals.
- **Webcam field of view at 720p:** some 4K webcams **crop** the sensor at lower
  resolutions instead of scaling, which narrows the field of view. Check this before
  fixing the mount height.
- **LenTok arm:** confirm it reaches the required height (see below) and that its clamp fits
  the hackathon tables. Tighten all joints; a sagging arm causes jitter even though the
  homography corrects for slow drift.

---

## 4. Electronics

### Motor driver (low-side NPN switch)

The ESP32 GPIO can't supply motor current directly, so it switches a transistor.

```
 3V3 ──────────┬───────────┐
               │           │
             Motor     1N4148 (cathode/stripe to 3V3 side)
               │           │
               └─────┬─────┘
                     │
                  Collector
 GPIO ──[220Ω]── Base   PN2222
                  Emitter
                     │
 GND ────────────────┘
```

- **Base resistor:** with GPIO at 3.3 V and V_BE ≈ 0.7 V,
  I_B = (3.3 − 0.7) / 220 Ω ≈ **11.8 mA**. This is within the ESP32's recommended GPIO
  current (~20 mA). For a motor drawing ~80 mA, the "forced beta" (I_C / I_B) is about 7,
  well below the PN2222's actual gain, so the transistor fully saturates (turns fully on).
  With 270 Ω: I_B ≈ 9.6 mA, still fine.
- **Flyback diode:** when the motor turns off, its coil produces a voltage spike. The 1N4148
  across the motor absorbs it. **Leaving it out can kill the transistor or the ESP32.**
- **Supply:** powering one coin motor from the ESP32 board's 3V3 pin is fine (the onboard
  regulator supplies several hundred mA). Don't run more than one or two motors from it.

> **Oct 24: two boards are being tried in parallel.** The CE built an **Arduino Uno R3**
> version (motor D9, button D2, motor powered from the Uno's 3.3V pin, **470 Ω** base resistor
> because Uno pins are 5 V, plus a **10 kΩ base pull-down** so the motor doesn't twitch during
> reset). Its full build guide is `docs/hardware/README.md`. The ESP32 values below still apply
> to the ESP32 version. Whichever board passes the bench test first is used for the demo.

### ESP32 pins (defaults for a classic ESP32 DevKit; confirm for the actual board)
- **Motor:** GPIO 25 (output)
- **Button:** GPIO 27 with `INPUT_PULLUP`; the button connects the pin to GND when pressed
  (so pressed = LOW).
- **Avoid:** strapping pins GPIO 0, 2, 12, 15 (they affect boot), and GPIO 34–39 for the
  button (input-only, no internal pull-up).

---

## 5. Camera mount height

Height depends on print size and the camera's field of view (FOV). Formula: to cover a width
W with horizontal FOV θ_h, the height is

    h = (W / 2) / tan(θ_h / 2)

Do the same for the vertical direction and use the **larger** height.

**Worked example** (assumptions: A3 print in landscape, 420 x 297 mm, plus ~40 mm margin on
each side for the markers; horizontal FOV 78°, which is a guess; check the Acer spec and the
720p cropping gotcha above):
- Area to cover: 500 x 380 mm
- Vertical FOV for 16:9: 2·atan(tan(39°) · 9/16) = 2·atan(0.4555) ≈ 49.0°
- Horizontal: h = 250 / tan(39°) = 250 / 0.810 ≈ 309 mm
- Vertical: h = 190 / tan(24.5°) = 190 / 0.456 ≈ 417 mm
- **Vertical limits, so h ≈ 42 cm.** At that height, 1280 px spans ≈ 675 mm, about
  **0.5 mm per pixel**, which is plenty for fingertip tracking.

Re-derive this once the print size and real FOV are known.

---

## 6. Sound design (four layers)

Brightness-to-pitch beeps were rejected: they give blind users something basic instead of a
real experience. The current design is based on research:

- *Eyes-Free Art* (Rector et al., Microsoft Research, 2017): layered "proxemic" audio.
  11 of 13 blind/low-vision participants preferred it; object sound effects rated most
  realistic; an audio "gong" for edges confused people (so edges are haptic here).
- *EyeMusic* (sensory substitution): mapping color to instrument timbre roughly doubled the
  visual detail users could pick out.
- Crossmodal correspondence: people naturally hear lighter things as higher in pitch.

### Layer 1: spoken overview
A voice describes the whole scene before exploration starts.

### Layer 2: color as instruments
| Color class | Instrument |
|---|---|
| Blue | Harp |
| Warm (red/orange/yellow) | Strings |
| Pale / white | Choir |
| Dark | Cello |

- Each instrument is a **looping stem with a low and a high register**.
- Per-instrument gain: `gain = 0.14 + 0.86 * weight`. A quiet bed always plays so the audio
  never goes silent.
- Register mix, with `L` = HSL lightness in [0, 1]:
  `low * (1 - 0.7*L) + high * (0.15 + 0.85*L)`
- **Detect "dark" with HSL lightness, not luma.** Luma made a navy field read as half harp.
- Pan left/right with the finger's `u` coordinate.

### Layer 3: object sounds
When the finger is in a labeled region, that region's sound plays over the music.
Demo painting mapping ("Sunset Hills" stand-in):

| Region | Sound |
|---|---|
| Sky / clouds | Birds |
| Sun | Cicadas |
| Hills | Wind |
| Field | Crickets |
| Path | Water |
| Tree | Rustling leaves |

Use recorded sounds (e.g. freesound.org; **check each license**) and real instrument loops.

### Layer 4: press and hold
Chime → music ducks to about 1/3 → voice describes only that spot.

### Edges
**Felt, not heard.** Only the fingertip motor reacts to edges.

---

## 7. Interfaces between team members (agreed contracts)

These boundaries let each person build separately and plug together on Saturday. Don't change
them without telling the team.

- **Demo machine:** Demo runs on Gerson's Mac (macOS); all audio, TTS, and vision AI code
  must be tested on macOS.

- **Coordinates:** normalized `(u, v)` in [0, 1], origin at the **top-left** of the image.
- **Region map:** `content/regions.png`, same resolution as the painting, each pixel value is
  a region ID (0 = background/none). Plus `content/regions.json`:
  ```json
  {
    "1": {"name": "tree", "sound_file": "assets/sounds/leaves.wav",
          "description": "A tall oak on the left, dark green, leaning toward the path."}
  }
  ```
- **Edge map:** derived from **region-map boundaries**, not image edge detection. Canny edges
  (OpenCV's standard edge detector) on a painting pick up brushstrokes and texture, and the
  motor would buzz constantly. Dilate the boundary a few pixels so the edge is a band the
  finger can actually land in.
- **Serial protocol:** 115200 baud, one ASCII command per line (`\n`-terminated).
  - Laptop → ESP32: `M1` motor on, `M0` motor off
  - ESP32 → laptop: `B1` button pressed, `B0` button released
  - Send motor commands **only when the state changes**, not every frame.
- **Audio engine API:**
  ```python
  audio.update(u, v, hsl, region_id, finger_present)  # called once per frame
  audio.describe(crop_image)                           # on button hold
  ```

---

## 8. Team split

| Role | Owns |
|---|---|
| **CE (Gerson)** | Camera setup, ArUco + homography, MediaPipe fingertip → (u, v), lookup, `tools/make_edge_map.py`, main loop, serial link on the laptop, final integration. **Also former EE #1 work (as of Oct 24):** motor driver circuit, ESP32 firmware (motor + debounced button, `firmware/`), finger wiring and strain relief, camera mount |
| ~~EE #1~~ | No-show; all responsibilities moved to CE (Gerson) on Oct 24 |
| **EE #2** | Audio engine (stems, gain/register mixing, panning, object sounds, ducking, chime), vision AI + TTS describe feature, sourcing licensed sounds |
| **BME** | Painting choice, region map + JSON + overview + descriptions, fingertip motor mount ergonomics, blindfolded user testing, deck/reel update, demo footage |
---

## 9. Suggested repo layout

```
open-canvas/
├── CLAUDE.md
├── SETUP.md               # dev environment setup (Python 3.11 venv)
├── requirements.txt       # pinned package versions
├── app/
│   ├── main.py            # main loop: camera → track → lookup → audio + serial
│   ├── config.yaml        # camera index, serial port, marker IDs, print size, thresholds
│   ├── camera.py          # capture setup (MJPG, 720p, autofocus/exposure lock)
│   ├── markers.py         # ArUco detection + homography, cached last-good H
│   ├── hand.py            # MediaPipe fingertip tracking
│   ├── lookup.py          # (u, v) → HSL, region ID, edge flag
│   ├── serial_link.py     # pyserial wrapper for the M/B protocol
│   ├── describe.py        # crop → vision AI → text
│   └── audio/
│       └── engine.py      # layered mixer, ducking, TTS playback
├── firmware/
│   └── open_canvas_esp32/
│       └── open_canvas_esp32.ino
├── content/
│   ├── painting.png
│   ├── regions.png
│   ├── regions.json
│   └── overview.txt
├── assets/
│   └── sounds/            # stems (low/high per instrument), object sounds, chime
└── tools/
    ├── make_markers.py    # generate printable ArUco markers (IDs 0–3)
    ├── make_edge_map.py   # region boundaries → dilated edge map
    └── fake_inputs.py     # drive the audio engine without a camera
```

---

## 10. Software stack

- **Python 3.11** (tested 3.11.17). Exact package versions are pinned in `requirements.txt`;
  setup steps are in `SETUP.md`.
- `opencv-contrib-python` 5.0 (**not** `opencv-python`; mediapipe depends on the contrib
  build and the two conflict). ArUco is built in; use the newer `cv2.aruco.ArucoDetector` class.
  Many tutorials use the old `cv2.aruco.detectMarkers`, which is deprecated.
  Dictionary: `DICT_4X4_50`, IDs **0 = top-left, 1 = top-right, 2 = bottom-right,
  3 = bottom-left**.
- `mediapipe` (Tasks API `HandLandmarker`)
- `numpy`, `sounddevice` (custom numpy mixer in the audio callback, for smooth per-frame gain
  changes), `soundfile` for loading WAVs
- `pyserial`
- TTS: Kokoro (offline, free, already used for the demo video). Vision AI: any
  vision-capable model API; keep crops small to reduce cost and latency.
- ESP32 firmware: Arduino framework (C++)

---

## 11. Implementation notes and gotchas

- **Hidden markers:** a hand will often cover a corner marker. Recompute the homography only
  when all four markers are found; otherwise reuse the last good one.
- **Marker geometry:** map the markers' known physical corner positions (relative to the
  painting's edges) to painting coordinates, not just "the four corners of the image."
  Measure the offset from each marker to the painting edge after printing.
- **Fingertip offset:** the camera sees the top of the finger, and landmark 8 sits slightly
  past where the pad touches the paper. Add a small calibratable offset if lookups feel off.
- **Smoothing:** apply light smoothing (e.g. exponential moving average) to (u, v) so audio
  and the motor don't jitter, but keep it light so the response stays fast.
- **Motor chatter:** add hysteresis (require a couple of consecutive frames in or out of the
  edge band) before toggling the motor.
- **Button debounce:** debounce in firmware (~20–30 ms) and send `B1`/`B0` only on changes.
  "Hold" means held for ~300 ms; a quick tap can be ignored or repurposed.
- **No finger visible:** fade object sounds out and keep only the quiet music bed; make sure
  the motor is off.
- **Latency target:** fingertip-to-sound under ~100 ms; describe feature about 1–2 s.
- **Audio thread:** never do file I/O or network calls in the audio callback; preload all
  stems and run vision AI/TTS on a separate thread.

---

## 12. Status and open items

**Existing materials (outside this repo):**
- Pitch deck (HTML artifact "Feel the Painting Pitch"). Its concept slide still says
  "Every dot is a note" (old idea) and must be updated to the four-layer design, and its
  branding updated to **Open Canvas**.
- Promo reels (~55 s): `Feel_the_Painting_reel.mp4` and `Feel_the_Painting_reel_VHS.mp4`.
  The simulated demo at **0:38** gets replaced with real footage Saturday night. Title cards
  need the new name.
- `Sound_Design_Demo.mp4` (~59 s): old beep version, then each of the four layers.

**To do:**
- [ ] Choose painting and print size; produce region map, JSON, overview, descriptions
- [x] Vision pipeline: camera → homography → fingertip (u, v) (Oct 24, live on the Acer)
- [x] Audio engine with fake inputs, then live (Oct 24, incl. hover-to-speak)
- [x] Main loop `app/main.py` end to end, motor simulated (Oct 24)
- [ ] Motor/button circuit built and bench-tested (`docs/hardware/README.md`); Uno firmware flashed, ESP32 in progress
- [ ] Camera mount at the computed height
- [ ] Integration by Saturday noon; blindfolded user testing Saturday afternoon
- [ ] Update deck and reel to Open Canvas and four-layer design; film real demo
- [ ] Re-check the event rules at dsplusx.com before submitting
- [ ] Stretch (only after core works): "draw mode" where users create their own picture

**Milestones:** Thu interfaces agreed + painting chosen · Fri each piece works on its own ·
Sat noon integrated · Sat evening tested + filmed · Sun polish and submit.

---

## 13. How to work with the team

Written for Gerson (CE, second-year); applies to every teammate.

- Lead with the answer. Define jargon the first time it comes up.
- Show the math and state assumptions for power budgets, specs, and tolerances.
- Comment non-obvious code and explain the structure of new files.
- When fixing a bug, explain what was actually wrong, not just the corrected code.
- Flag hardware compatibility issues and gotchas without being asked.
- If an approach is wrong or there's a better one, say so early.
- Budget is tight and time is 24 hours: prefer cheap, simple, buildable solutions.
