# Build log

How Open Canvas came together at DS+X 2026 (Boston University, Oct 24–25, 2026).
Times are Eastern. Each step links to the pull request that landed it on `main`.

## Before the event (Wed Oct 21)

- Wrote the project spec and team contracts (`CLAUDE.md`): four-layer audio design,
  serial protocol, file ownership per role.
- Set up the repo, `SETUP.md`, and pinned Python 3.11 packages (`requirements.txt`).
- No app code yet; it was all written at the event.

## Saturday, Oct 24

| Time | What landed |
|---|---|
| 13:14 | One EE teammate did not show up. CE took over the motor circuit, firmware and camera mount. |
| 16:32 | **#2** audio engine, sounds and test tools (EE). **#3** vision pipeline (ArUco homography, MediaPipe fingertip), main loop, Arduino Uno firmware and motor circuit guide (CE). First full run: camera → fingertip → sound → motor. |
| 20:38 | **#4** rest-to-describe: keeping the finger still for 2.5 s speaks the region. |
| 20:41 | **#5** dropped the describe button; rest-to-describe replaces it, so the visitor needs nothing but a finger. |
| 20:53 | **#6** welcome overview for each new visitor, plus a double-click / Siri launcher. |
| 21:07 | **#7** launcher finds the Uno on its own; music 3 dB lower so the voice stays clear. |
| 21:31 | **#8** painting library (Sunset Hills, The Great Wave, The Starry Night, Mondrian), each page recognized from its own markers; print pack; Mac app. All four pages tested on paper. |
| 21:51 | **#9** README and final docs. Tagged `v1.0-demo`. |

## Sunday, Oct 25

| Time | What landed |
|---|---|
| 06:26 | **#11** explainer and demo video (release `v1.0-demo`). |
| 09:17 | **#12** submission slide deck. |
| 09:43 | **#13** license, this build log, removed the unused ESP32 folder. |
| 09:46 | **#10** Great Wave and Mondrian voices re-rendered with ElevenLabs; Sunset Hills overview re-recorded to match the button-free design. |

## Known limits

- **Testing:** blindfolded sighted testers only. We have not yet tested with blind or
  low-vision visitors, who are the people this is for.
- **Descriptions are pre-written.** The spoken descriptions are team-written text
  (`regions.json`, `overview.txt`) rendered to audio ahead of time. The live vision-AI
  describer in the spec is not in the demo build.
- **Voices:** see [`assets/sounds/CREDITS.md`](assets/sounds/CREDITS.md) for which clips are
  ElevenLabs and which are still macOS stand-ins.
- **Setup:** the demo runs on one Mac with an overhead webcam that must not move after the
  page is placed.

## Next ideas

- Test with blind and low-vision visitors, ideally with a museum access program.
- Live vision-AI descriptions for any painting, so a new page needs no hand-written text.
- "Draw mode": the visitor makes their own picture and hears it back.
