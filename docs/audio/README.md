# Audio guide: what you hear (EE #2)

Everything about the sound side of Open Canvas: how the color, object and voice layers are
built, how to run and test them without a camera, and how to add or re-voice a painting.

- **Owner:** EE #2 (Mauricio Barrientos): audio engine, color-to-instrument mapping, object
  sounds, voice clips, describe/TTS hook (CLAUDE.md section 8)
- **Code:** `app/audio/engine.py`, `app/audio/color_map.py`
- **Tools:** `tools/fake_inputs.py`, `tools/mouse_demo.py`, `tools/make_voices_elevenlabs.py`,
  `tools/make_voices_say.py`, `tools/make_sfx_elevenlabs.py`
- **Sounds:** `assets/sounds/` (sources and licenses in `assets/sounds/CREDITS.md`)

---

## 1. What it does

A blind or low-vision visitor wears headphones and moves a finger over the printed painting.
The camera side (Gerson) turns the fingertip into painting coordinates; the audio engine turns
that into four layers of sound (CLAUDE.md section 6):

| Layer | What you hear | When |
|---|---|---|
| 1. Overview | A voice names the painting and gives a mental map of the scene | A painting is placed, or a new visitor first touches it |
| 2. Color as music | Each color plays its own instrument, higher for brighter spots, panned left/right with the finger | Always, while touching |
| 3. Object sounds | The thing under the finger makes its sound (birds in the sky, wind on the hills, crickets in the field) | Finger inside a labeled region |
| 4. Description | Music ducks to about 1/3 and a voice describes just that spot | Finger rests still on a region for 2.5 s |

**Edges are felt, not heard.** The audio engine never reacts to outlines; the fingertip motor
does (`docs/hardware/`). Research behind this: an audio "gong" for edges confused blind users
in *Eyes-Free Art* (Rector et al., 2017).

---

## 2. Signal flow

```
 main loop (~30 Hz camera rate): lookup gives (u, v), hsl, region_id
       │  audio.update(u, v, hsl, region_id, finger_present)   once per frame
       │  audio.describe(crop_image)                            "d" key; hover calls it internally
 ──────┼───────────────────────────────────────────────────────────────────────
       ▼  audio thread (48 kHz, 512-sample blocks = 10.7 ms)
 Layer 2  music stems (instrument x low/high) ──┐
 Layer 3  object sound (one per region)  ───────┼─ x duck ─ pan ─┐
                                                                 ├─ master ─ soft clip ─► headphones
 Layer 1/4  voice (overview, descriptions) ──────────────────────┘   (voice centered)
```

**Agreed API** (CLAUDE.md section 7; don't change it without the team):

```python
audio.update(u, v, hsl, region_id, finger_present)  # once per camera frame
audio.describe(crop_image)                           # describe the spot under the finger now
```

| Argument | Meaning |
|---|---|
| `u, v` | painting coordinates in [0, 1], origin top-left |
| `hsl` | (hue 0–360°, saturation 0–1, lightness 0–1) of the clean digital painting at (u, v) |
| `region_id` | pixel value of `regions.png` at (u, v); 0 = background |
| `finger_present` | False when MediaPipe finds no fingertip this frame |
| `crop_image` | square crop of the digital painting around the fingertip (for an AI describer) |

Extras: `start()`, `stop()`, `play_overview()`, `say(audio, sr)`, `render(seconds)` (offline,
no sound card), `region_name(rid)`, and `state` (last update, for HUDs).

`app/main.py` builds one `AudioEngine` per painting when its page is recognized, then calls
`play_overview()` (`load_print()`).

---

## 3. Layer 2: color as instruments

`app/audio/color_map.py` turns the color under the finger into instrument weights that sum to 1.

| Color | Instrument | Notes |
|---|---|---|
| Blue | Harp | hue lobe centered at 220° |
| Warm (red / orange / yellow) | Strings | centered at 25° |
| Green | Woodwind | centered at 115°; **added beyond the team's 4-instrument spec** (EyeMusic gives green a reed timbre). Delete it from `HUE_CENTERS` and `INSTRUMENTS` to go back to 4 |
| Pale / white | Choir | HSL lightness above 0.75–0.92 |
| Dark | Cello | HSL lightness below 0.10–0.25 |

Rules that make it sound smooth:
- **Soft membership, not if/else.** Hue uses Gaussian lobes (45° wide); lightness and
  saturation use smoothstep ramps. A hard threshold flips the sound back and forth when the
  finger sits on a color boundary; soft weights crossfade instead.
- **Dark uses HSL lightness, not luma.** Luma counts blue at only 11%, so navy read as black.
- **Quiet bed:** `gain = 0.14 + 0.86 * weight`, so every instrument always plays a little and
  the mix never goes silent.
- **Register (low/high stem mix):** `low * (1 - 0.7L) + high * (0.15 + 0.85L)`. Lighter spots
  sound higher, following the crossmodal correspondence that people hear light as high.
- **Pan** follows `u`: `pan = 0.75 * (2u - 1)` (0.75 so the edges aren't hard-left/right in headphones).

Check the mapping without any audio: `.venv/bin/python -m app.audio.color_map` prints a table
of test colors and their weights.

The music stems in `assets/sounds/music/` (`<instrument>_low.wav`, `<instrument>_high.wav`)
are **synthesized placeholders**. Real instrument loops can be dropped in with the same names;
export them at 48 kHz, the same length, so they loop in sync.

---

## 4. Layer 3: object sounds

Each region in `regions.json` can name a looping sound. Several regions can share one file.

```json
"6": {"name": "path", "sound_file": "assets/sounds/objects/footsteps.wav",
      "description": "...", "gain_db": 0}
```

`gain_db` (optional, outside the contract) trims one sound up or down; the sun's cicadas are
at -6 dB. All clips are auto-leveled to the same loudness on load, so a new recording drops in
at the right level.

| Painting | Region → sound |
|---|---|
| Sunset Hills | sky, clouds → birds · sun → cicadas · hills → wind · field → crickets · path → footsteps · tree → leaves |
| The Great Wave | sky → wind · the wave → water · Fuji, boats, title → none |
| The Starry Night | sky → wind · hills, village → crickets · cypress → leaves · moon, star → none |
| Mondrian | none (color music only) |

Birds, cicadas, wind, crickets, leaves, footsteps and the chime come from **ElevenLabs Sound
Effects** (`tools/make_sfx_elevenlabs.py`, 20 s seamless loops). `water.wav` is a synthesized
placeholder.

---

## 5. Layers 1 and 4: voice

**Pre-rendered clips.** Every painting has `overview.wav` plus `region_<id>.wav` per region:

| Painting | Voice folder | Voice |
|---|---|---|
| Sunset Hills | `assets/sounds/voice/` | ElevenLabs George |
| The Great Wave | `content/library/great_wave/voice/` | ElevenLabs George |
| Mondrian | `content/library/mondrian/voice/` | ElevenLabs George |
| The Starry Night | `content/library/starry_night/voice/` | macOS "Samantha" stand-in (being re-rendered in George) |

Why pre-rendered: speech starts the instant it's needed, works with no internet at the venue,
and every line can be checked before the demo.

**Voice settings** (in `tools/make_voices_elevenlabs.py`): voice "George - Warm, Captivating
Storyteller", model `eleven_v4`, stability 0.65, similarity 0.75, style 0, speed 0.9 (calm,
slightly slow narration). Keep these the same so every painting sounds like one narrator.

**Hover-to-speak** (replaces the dropped describe button, Oct 24). Inside `update()`:
- The finger must stay within `HOVER_RADIUS` = 0.04 (about 1 cm on Letter) of where it stopped,
  on one region, for `HOVER_TIME` = 2.5 s. Gliding across a region doesn't count.
- It waits until the overview has finished, and won't repeat the same region within
  `HOVER_REPEAT` = 20 s.
- Music and object sounds duck to `DUCK` = 0.33 (fast attack 50 ms, slow 0.5 s release), and
  the voice plays centered.
- `state["hover"]` is the 0..1 progress (the mouse demo draws it as a ring).

**AI describer hook (not yet wired).** `AudioEngine(describer=fn)` accepts
`fn(crop_image, region_id, region_info) -> (audio_float32, sample_rate)`. It runs on a worker
thread; the music stays ducked up to `AI_TIMEOUT` = 8 s while it thinks, and if it fails or
returns None, the pre-rendered clip plays instead. Main currently passes no describer, so the
pre-rendered clips are what visitors hear.

---

## 6. Real-time design rules

- The audio callback **never blocks**: no file access, no network, no locks. All audio is
  loaded, leveled and resampled to 48 kHz up front. The main loop hands the audio thread a new
  immutable `Control` snapshot by plain assignment (atomic in Python).
- **Every gain change is smoothed** (one-pole low-pass, ramped across each block, like an RC
  filter). An instant gain step is a step in the waveform's envelope, which you hear as a click.
- **Region hysteresis:** the object sound only switches after the finger has been in a new
  region for 0.12 s, so a finger on a boundary doesn't flip-flop between two sounds.
- **Lift grace:** MediaPipe drops frames; "no finger" only counts as lifted after 0.35 s.
- Loops are crossfaded end-to-start so the loop point doesn't click; a soft clipper on the
  master keeps loud moments from hard-clipping.

**Measured on the M3 Max:** about 0.09 ms of CPU per 10.7 ms block, 0 underruns, 13 ms output
latency; the areas sit within 2 dB of each other; the voice is about 11 dB above the ducked bed.

---

## 7. Run and test it (no camera or Arduino needed)

Setup is in `SETUP.md` (Python 3.11 `.venv`, pinned `numpy`, `sounddevice`, `soundfile`).
Use **wired headphones**: panning needs stereo, and Bluetooth adds about 200 ms of delay.

```bash
# See and hear it: the mouse is the finger
.venv/bin/python tools/mouse_demo.py
.venv/bin/python tools/mouse_demo.py --content content/library/great_wave
.venv/bin/python tools/mouse_demo.py --tour        # watch a scripted finger path

# Scripted finger path with jitter and dropouts, like the real camera
.venv/bin/python tools/fake_inputs.py --live
.venv/bin/python tools/fake_inputs.py --render preview.wav     # offline, no sound card
```

Mouse demo controls: move over the painting = touching (move onto the gray panel = lifted),
rest 2.5 s = description, SPACE = describe now, O = overview, R = region overlay, ESC or Q = quit.

Full system with the camera: see the main README.

---

## 8. Add or re-voice a painting

1. The BME writes `overview.txt` and the `description` fields in `regions.json`
   (`content/library/<name>/`).
2. Free stand-in voice while drafting (macOS, offline):
   `.venv/bin/python tools/make_voices_say.py --content content/library/<name>`
3. Final voice (ElevenLabs George, about 1 credit per character):
   ```bash
   .venv/bin/python tools/make_voices_elevenlabs.py --content content/library/<name>
   .venv/bin/python tools/make_voices_elevenlabs.py --content content/library/<name> --only region_3   # one clip after a text edit
   ```
   `--all` re-renders every painting. **Avoid `--all` on the free plan**: it re-renders
   clips whose text didn't change (about 5,700 credits for all four paintings; the free
   plan has 10,000 a month).
4. Listen with the mouse demo, then commit only the WAVs.

**API key:** `ELEVENLABS_API_KEY=...` in `.env` at the repo root. `.env` is gitignored: never
commit it or paste the key into chat. A restricted key needs Text to Speech (and Voices: Read
for the voice lookup; Sound Effects for `make_sfx_elevenlabs.py`). Each teammate can use their
own free account; George is a built-in voice on every account.

---

## 9. Credits for the submission

- Voices: "Voice by ElevenLabs" (George, free plan)
- Sound effects: "Sound effects by ElevenLabs"
- Full list: `assets/sounds/CREDITS.md`

---

## 10. Open items

- [ ] Starry Night voice in George (Gerson, own ElevenLabs key)
- [ ] Real instrument stems instead of synthesized placeholders
- [ ] Tune `color_map.py` so the field, sun and path (all mostly strings) sound more different
- [ ] Team decisions: keep woodwind for green? Path = footsteps (CLAUDE.md said water)?
- [ ] Optional: wire an AI describer + live TTS into the `describer` hook (needs a model,
      key and voice choice from the team)
- [ ] Output-device option, and a headphone splitter for two listeners
