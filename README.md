# Open Canvas

**Explore a painting by touch.** Open Canvas lets blind and low-vision people feel and hear
a printed painting. Put a hand on the print: an overhead camera follows the index fingertip,
and the part of the painting under it comes alive.

- **Color becomes music.** Each color plays its own instrument (blue = harp, warm = strings,
  pale = choir, dark = cello), higher for brighter spots, panned left and right with the finger.
- **Objects make their own sounds.** Wind in the sky, water in the wave, crickets in the village.
- **Edges are felt.** A small vibration motor on the fingertip buzzes when the finger crosses
  an outline between two objects.
- **Rest to hear more.** Keep the finger still on a spot for 2.5 seconds and a voice describes it.
- **Overview first.** Placing a painting (or the first touch from a new visitor) plays a spoken
  overview that names the painting and gives a mental map of the scene.

No screen, menu or keyboard is needed by the visitor. Swap the printed page and Open Canvas
recognizes the new painting from its corner markers.

Built in 24 hours for the **Art Hack** track of **DS+X 2026** at Boston University
(Oct 24–25, 2026).

## Paintings

| Painting | Artist | What you can touch |
|---|---|---|
| Sunset Hills | the Open Canvas team | sky, clouds, sun, hills, field, path, tree |
| The Great Wave off Kanagawa (c. 1831) | Katsushika Hokusai | sky, the wave, Mount Fuji, three boats, title panel |
| The Starry Night (1889) | Vincent van Gogh | swirling sky, eleven stars, moon, cypress, hills, village |
| Composition with Red, Blue and Yellow (1930) | Piet Mondrian | red, blue, yellow and white blocks, black lines |

Print them from [`assets/print_pack.pdf`](assets/print_pack.pdf): one Letter page per
painting, markers included. Print at Actual size, or "Fit to page" on 11x17 for a bigger
painting. Cut off the dashed top-left corner so the page's orientation can be felt.

## How it works

```
 overhead webcam ──► ArUco markers ──► which painting + homography (camera px → painting u, v)
                └──► MediaPipe hand ──► index fingertip ──► (u, v)
 (u, v) ──► color, region, edge flag ──► layered audio (headphones) + motor (Arduino Uno over USB)
```

- **Markers:** each printed page has four ArUco markers with its own IDs
  (`content/library.yaml`), so they both identify the painting and map the camera image onto it.
  A hand covering one marker is fine; the last good mapping is reused.
- **Lookup:** colors and regions come from the clean digital painting (`content/`), not the
  webcam, so lighting and the hand don't change what is heard.
- **Audio:** a custom numpy mixer with four layers: overview, color instruments, object sounds,
  and spoken descriptions (the music ducks under the voice).
- **Haptics:** region boundaries widened into a ~5 mm band; the laptop sends `M1`/`M0` to the
  Uno, which drives a coin motor through an NPN transistor (`docs/hardware/`).

## Run it (macOS)

Setup is in [`SETUP.md`](SETUP.md) (Python 3.11 venv, pinned packages). Then:

```bash
python tools/make_mac_app.py          # builds ~/Applications/Open Canvas.app (once)
open -a "Open Canvas"                 # or double-click it, or Spotlight, or Siri
```

Or from a terminal with the debug window: `python -m app.main --serial /dev/cu.usbmodem1101`
(settings in `app/config.yaml`; keys: `d` describe, `o` overview, `q` quit).

**Siri:** a Shortcut named "Start Open Canvas" with one Run Shell Script action,
`open -a "Open Canvas"`, lets anyone start it by voice ("Hey Siri, start Open Canvas").
Enable Shortcuts → Settings → Advanced → Allow Running Scripts.

## Repo map

| Path | What |
|---|---|
| `app/main.py` | main loop: camera → markers + fingertip → lookup → audio + motor |
| `app/library.py`, `content/library.yaml` | painting library and page recognition |
| `app/markers.py`, `app/hand.py`, `app/lookup.py` | homography, fingertip tracking, (u, v) lookup |
| `app/audio/` | audio engine and color → instrument mapping |
| `firmware/open_canvas_uno/` | Arduino Uno motor firmware |
| `docs/hardware/` | motor circuit build guide and schematic |
| `tools/` | print pack, markers, edge maps, voice rendering, Mac app builder, test tools |
| `CLAUDE.md` | full project spec, team contracts and design notes |

## Credits

- **Team:** CE (vision, integration, hardware), EE (audio engine, describe feature),
  BME (painting content, user testing). One EE teammate did not attend.
- **Paintings:** The Great Wave, The Starry Night and Mondrian's 1930 Composition are public
  domain; images from Wikimedia Commons. Sunset Hills is team-made.
- **Sounds and voices:** see [`assets/sounds/CREDITS.md`](assets/sounds/CREDITS.md)
  (sound effects and Sunset Hills voice by ElevenLabs).
- **Research the design builds on:** *Eyes-Free Art* (Rector et al., Microsoft Research, 2017)
  for layered proxemic audio; *EyeMusic* for color as instrument timbre.
