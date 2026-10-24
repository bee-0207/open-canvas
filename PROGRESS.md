# Gerson's progress log (CE: vision pipeline + integration + former EE #1 hardware)

> **Sat Oct 24 update:** EE #1 was a no-show. I now also own the motor driver circuit,
> ESP32 firmware (`M1`/`M0`, debounced `B1`/`B0`), finger wiring + strain relief, and the
> camera mount. See CLAUDE.md section 8.

Last updated: **Thu Oct 22, 2026 (night)**. Hackathon: Sat Oct 24 – Sun Oct 25.

---

## Where I stopped

Steps 2 and 3 of my plan are **written and tested in software**, but **not yet tested on a
real camera**. The markers are printed and cut out. I paused because I didn't have
something flat and stiff to tape the stand-in painting to.

**First thing tomorrow:** do the live marker test (section "Resume here" below).

---

## Resume here (copy-paste)

```bash
cd ~/Desktop/open-canvas
source .venv/bin/activate          # prompt should show (.venv)
git pull                           # get teammates' changes
python -m tools.test_markers       # defaults: Letter landscape 279.4 x 215.9 mm, 10 mm gap
```

Press **q** to quit the test.

### 1. Build the stand-in painting
- Any printed **Letter sheet** with a picture on it.
- No cardboard? Use a **hardcover book, clipboard, door, wall or window**. Or tape it flat on
  the desk and point the laptop camera down at it (tilt the screen back, or use an iPhone as
  the camera via Continuity Camera; then try `--camera 1`).
- Tape each 7 x 7 cm tile **outside** its corner, the tile's inner corner touching the sheet's
  corner, with edges parallel. Marker rotation doesn't matter.

```
 ┌─────┐                         ┌─────┐
 │ ID0 │                         │ ID1 │
 └─────┼─────────────────────────┼─────┘
       │       picture           │
 ┌─────┼─────────────────────────┼─────┐
 │ ID3 │                         │ ID2 │
 └─────┘                         └─────┘
```

- Different sheet size? `python -m tools.test_markers --width-mm W --height-mm H`
- macOS will ask for camera permission for Terminal the first time. If frames are black:
  System Settings → Privacy & Security → Camera → enable Terminal, then restart Terminal.

### 2. What to check (pass = all of these)

| Test | Expected |
|---|---|
| All 4 markers in view | Green outlines + IDs 0–3; **green** outline hugs the picture; "flattened" window shows a straight-on picture |
| Tilt / move the board | Flattened view stays straight-on |
| Cover one marker with a hand | Outline turns **orange** ("H: reused"); flattened view keeps working |
| Hover mouse over the picture | `u, v` ≈ 0,0 at top-left, ≈ 1,1 at bottom-right; red dot follows in flattened view |
| FPS (bottom-left) | **Write the number down here:** ______ fps (baseline before hand tracking) |

If the outline doesn't hug the picture: wrong `--width-mm/--height-mm`, or tiles not touching
the corners. If a marker won't detect: glare, a crease, or white border trimmed too thin.

### 3. When the test passes
Commit and push the four untracked files (see "Repo state"), then start **step 4 (hand.py)**.

---

## Done today

### Setup
- Repo created: https://github.com/bee-0207/open-canvas (private), at `~/Desktop/open-canvas`.
- Python **3.11.17** via Homebrew (`/opt/homebrew/bin/python3.11`); system `python3` stays 3.14.
- Project venv at `.venv/` with pinned packages (`requirements.txt`): opencv-contrib-python
  5.0.0.93, mediapipe 1.1.1, numpy, sounddevice, soundfile, pyserial, pyyaml.
  **Only `opencv-contrib-python`**, never `opencv-python` (they overwrite each other).
- `SETUP.md`: step-by-step setup for teammates (macOS/Windows/Linux) with a verification check.
- `CLAUDE.md` section 0 "Start here" tells every teammate's Claude Code to follow SETUP.md,
  use the venv, stay in their role's files, and use role branches + PRs.

### Team decisions (recorded in CLAUDE.md)
- Demo runs on **my Mac**; all audio/TTS/vision AI code must be tested on macOS (section 7).
- I own `tools/make_edge_map.py` (section 8).
- EE #2 (**maui-i**) owns vision AI + TTS; it's no longer moving to me.
- Crop for `audio.describe(crop_image)` comes from the clean `content/painting.png` at the
  fingertip's (u, v), **not** the webcam (the finger would cover the spot being described).

### Team status
- Collaborators: **maui-i** accepted. **BAMTO** and **ryouikitennkai** invites still
  **pending** (they must accept at github.com/notifications; invites expire after 7 days).
- **Issue #1** (assigned to maui-i): macOS audio/describe notes: Kokoro + espeak-ng, API key in
  `.env`, threading, crop source, ask before adding packages. Still open.
- Waiting on maui-i: which packages Kokoro needs, so I can pin them in `requirements.txt`.

### Code (uncommitted, see below)
- `tools/make_markers.py` → `assets/markers.pdf`: four 5 cm ArUco markers (DICT_4X4_50, IDs 0–3),
  10 mm white border, cut lines, 10 cm check ruler. Verified: rendered at 300 DPI, all IDs
  decode, sides measure 49.9 mm. **Printed and cut.**
- `app/markers.py`: `MarkerLayout` (marker positions in mm) → `MarkerTracker.update(frame)`
  per frame → homography H (camera px → (u, v)). Uses each marker's diagonal-crossing center
  (rotation-proof). Keeps last good H when a marker is hidden; rejects markers taped in the
  wrong corners. Helpers: `camera_to_uv`, `uv_to_camera`, `flatten`.
  Verified on a synthetic tilted view: < 0.4 mm error; hidden marker → H reused; swapped
  markers → rejected.
- `tools/test_markers.py`: live camera window + flattened window (the test above).

---

## Repo state

- Pushed to GitHub (`main`): 3 commits, latest `17bac2e` "Assign edge map to CE and set demo machine".
- **Not committed yet** (commit after the live test passes):
  ```
  app/markers.py
  assets/markers.pdf
  tools/make_markers.py
  tools/test_markers.py
  PROGRESS.md
  ```
- Commits are authored by me only (no Claude co-author line).

---

## Next steps (my plan)

**Thursday (in progress)**
- [x] 2. `tools/make_markers.py` (printed + cut)
- [ ] 3. `app/markers.py`: **live camera test** ← resume here
- [ ] 4. `app/hand.py`: MediaPipe `HandLandmarker`, landmark 8 = index fingertip.
  Download the model file `hand_landmarker.task` and keep it in the repo (e.g. `assets/models/`).
  Use VIDEO running mode. **Measure FPS early** (target: fingertip → sound < 100 ms).
- [ ] 1. Still open with the team: nothing blocking, but confirm everyone has run SETUP.md.

**Friday**
- [ ] 5. `app/lookup.py` + `tools/make_edge_map.py` (fake painting + hand-drawn region map until BME delivers)
- [ ] 6. `app/serial_link.py` (`M1`/`M0` out, `B1`/`B0` in, skip ESP32 boot messages; keyboard fake for the button)
- [ ] 7. `app/main.py` with a debug window (fingertip dot, (u, v), region, edge state)
- [ ] 8. Acer webcam: **test focus/exposure lock on macOS first** (try `uvc-util` if OpenCV can't);
  measure real FOV at 720p

**Saturday morning:** integrate my ESP32 + motor (ex-EE #1 work, now mine), EE #2 (audio), BME (painting + region map).

**Added Sat (ex-EE #1):**
- [ ] Motor driver circuit (transistor/driver + flyback diode, 47–100 µF cap across 3V3/GND)
- [ ] `firmware/open_canvas_esp32/open_canvas_esp32.ino`: 115200 baud, `M1`/`M0` in, button debounced 20–30 ms, `B1`/`B0` out on change
- [ ] Finger wiring + strain relief
- [ ] Camera mount at the computed height (~48 cm for A3, see risks)

---

## Open risks / things to remember

- **Camera height must be re-derived.** The spec (section 5) assumed 40 mm margins; each marker
  tile adds 70 mm per side. For an A3 print: 560 x 437 mm → camera height ≈ **48 cm**
  (218.5 / tan 24.5°), not 42 cm. Check the LenTok arm reaches it, or use 4 cm markers.
- **macOS camera controls:** OpenCV may ignore autofocus/exposure/MJPG settings on macOS.
  Biggest risk; test as soon as the Acer webcam arrives.
- **Hidden markers:** fine as long as camera and painting don't move. Tape the painting and
  markers to the table; tighten the camera arm. Possible upgrade if needed: use all 4 corners
  of each marker so 3 visible markers are enough (small change in `MarkerTracker._solve`).
- **ESP32 variant:** GPIO 25/27 only exist on the classic ESP32 (not C3; on S3, 27 is flash).
  S3/C3 with native USB: enable "USB CDC On Boot". Opening the serial port resets the board.
- **Motor:** add a 47–100 µF capacitor across 3V3/GND near the motor to avoid brownout resets.
- **Print:** matte paper for the painting (glare breaks color lookup and marker detection).
