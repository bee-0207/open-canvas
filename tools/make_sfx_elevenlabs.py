"""
make_sfx_elevenlabs.py: generate the Layer 3 object loops and the UI chime with
ElevenLabs Sound Effects, replacing the synthesized placeholders in assets/sounds/.

    .venv/bin/python tools/make_sfx_elevenlabs.py                  # every sound in SOUNDS
    .venv/bin/python tools/make_sfx_elevenlabs.py --only footsteps # just one

Prompts live in SOUNDS below: edit a prompt and re-run with --only to try again.
Loops are asked for as seamless loops; the engine also crossfades the loop point and
levels loudness at start-up (engine.make_seamless / normalize), so no manual editing.

Needs ELEVENLABS_API_KEY in .env at the repo root (gitignored). Standard library only;
the MP3 is converted with macOS `afconvert` to 48 kHz mono 16-bit WAV.
Record each generated file in assets/sounds/CREDITS.md.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.elevenlabs.io"

# name -> (output path under assets/sounds, seconds, loop?, prompt)
# Prompts ask for calm, even beds with no single standout event: a loop repeats for
# minutes while someone explores, and one loud bird call becomes annoying on the 10th pass.
SOUNDS = {
    "birds": ("objects/birds.wav", 20, True,
              "Songbirds chirping and singing in the open countryside on a calm evening, several small "
              "birds at a comfortable distance, gentle and pleasant, continuous, clearly audible"),
    "cicadas": ("objects/cicadas.wav", 20, True,
                "Distant cicadas on a warm summer evening, soft mellow buzzing far away, gentle and warm, "
                "not shrill, calm, even level, no other sounds"),
    "wind": ("objects/wind.wav", 20, True,
             "Soft gentle wind blowing over grassy hills, smooth airy whoosh, calm and steady, "
             "no gusts, no other sounds"),
    "crickets": ("objects/crickets.wav", 20, True,
                 "Crickets chirping in a quiet grassy field at dusk, steady soft rhythm, calm, "
                 "even level, no other sounds"),
    "leaves": ("objects/leaves.wav", 20, True,
               "Leaves of a large tree rustling softly in a light breeze, gentle continuous rustle, "
               "calm, even level, no birds, no other sounds"),
    "footsteps": ("objects/footsteps.wav", 20, True,
                  "Slow relaxed footsteps walking on a dry dirt and fine gravel path outdoors, "
                  "steady even pace, soft crunch, calm, no other sounds"),
    "chime": ("ui/chime.wav", 1.5, False,
              "A single soft gentle bell chime, warm and clear, short and pleasant, "
              "like a calm notification, quick attack and natural fade, no reverb tail"),
}


def load_key():
    path = os.path.join(REPO, ".env")
    if os.path.exists(path):
        for line in open(path):
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("ELEVENLABS_API_KEY not found in .env at the repo root")


def generate(key, prompt, seconds, loop):
    body = {"text": prompt, "duration_seconds": seconds, "prompt_influence": 0.5}
    if loop:
        body["loop"] = True
    req = urllib.request.Request(API + "/v1/sound-generation?output_format=mp3_44100_128", method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:400]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=list(SOUNDS))
    ap.add_argument("--out", default=os.path.join(REPO, "assets", "sounds"))
    a = ap.parse_args()
    key = load_key()
    for name, (rel, seconds, loop, prompt) in SOUNDS.items():
        if a.only and name != a.only:
            continue
        mp3 = generate(key, prompt, seconds, loop)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(mp3)
        out = os.path.join(a.out, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "1", f.name, out], check=True)
        os.unlink(f.name)
        print(f"  wrote assets/sounds/{rel}  ({seconds} s{', loop' if loop else ''})")


if __name__ == "__main__":
    main()
