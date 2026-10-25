"""
make_voices_elevenlabs.py: pre-render the spoken overview (Layer 1) and every region
description (Layer 4 fallback) with ElevenLabs, into assets/sounds/voice/.

    .venv/bin/python tools/make_voices_elevenlabs.py --list            # voices matching --voice, and models
    .venv/bin/python tools/make_voices_elevenlabs.py                   # all clips: overview + every region
    .venv/bin/python tools/make_voices_elevenlabs.py --only region_3   # one clip after a text edit
    .venv/bin/python tools/make_voices_elevenlabs.py --content content/library/mondrian
    .venv/bin/python tools/make_voices_elevenlabs.py --all             # main painting + every library painting

Text comes from content/overview.txt and the "description" fields in content/regions.json.
Output is voice/overview.wav and voice/region_<id>.wav, which the engine loads at start-up:
assets/sounds/voice/ for the main painting (content/), <content>/voice/ for a library painting.

Why pre-render: speech is ready the instant the button is held, it works with no internet,
and every line can be checked before the demo. The live vision AI answer goes through
audio.describe(); these clips are its fallback.

Needs ELEVENLABS_API_KEY in .env at the repo root (.env is gitignored; never commit it).
Cost is about 1 credit per character. Standard library only (no new packages); the MP3 the
API returns is converted with macOS `afconvert` to 48 kHz mono 16-bit WAV, the engine's rate.
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
# Calm narration: slightly slow, steady, no exaggerated emotion.
SETTINGS = {"stability": 0.65, "similarity_boost": 0.75, "style": 0.0,
            "use_speaker_boost": True, "speed": 0.9}


def load_key():
    path = os.path.join(REPO, ".env")
    if os.path.exists(path):
        for line in open(path):
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("ELEVENLABS_API_KEY not found in .env at the repo root")


def call(key, method, path, body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} on {path.split('?')[0]}: {e.read().decode(errors='replace')[:400]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", default=os.path.join(REPO, "content"))
    ap.add_argument("--out", help="output folder (default: assets/sounds/voice for content/, else <content>/voice)")
    ap.add_argument("--all", action="store_true", help="content/ plus every folder in content/library/")
    ap.add_argument("--voice", default="George - Warm", help="voice name prefix in your ElevenLabs library")
    ap.add_argument("--model", default="eleven_v4")
    ap.add_argument("--only", help="one clip: overview or region_<id>")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    key = load_key()

    voices = json.loads(call(key, "GET", "/v1/voices"))["voices"]
    match = [v for v in voices if v["name"].lower().startswith(a.voice.lower())]
    if a.list:
        for v in match:
            print(f"voice  {v['name']!r:45s} {v['voice_id']}")
        for m in json.loads(call(key, "GET", "/v1/models")):
            if m.get("can_do_text_to_speech"):
                print(f"model  {m['model_id']}")
        return
    if not match:
        sys.exit(f"no voice starting with {a.voice!r}; try --list --voice ''")
    vid = match[0]["voice_id"]

    main_content = os.path.join(REPO, "content")
    if a.all:
        lib = os.path.join(main_content, "library")
        folders = [main_content] + [os.path.join(lib, d) for d in sorted(os.listdir(lib))
                                    if os.path.exists(os.path.join(lib, d, "regions.json"))]
    else:
        folders = [os.path.abspath(a.content)]

    batches = []
    for content in folders:
        if a.out and not a.all:
            out = os.path.abspath(a.out)
        elif os.path.samefile(content, main_content):
            out = os.path.join(REPO, "assets", "sounds", "voice")
        else:
            out = os.path.join(content, "voice")
        jobs = [("overview", open(os.path.join(content, "overview.txt")).read().strip())]
        regions = json.load(open(os.path.join(content, "regions.json")))
        jobs += [(f"region_{rid}", r["description"]) for rid, r in regions.items() if r.get("description")]
        if a.only:
            jobs = [j for j in jobs if j[0] == a.only]
        batches.append((content, out, jobs))
    n = sum(len(j) for _, _, j in batches)
    print(f"voice {match[0]['name']!r}, model {a.model}, {n} clips, "
          f"~{sum(len(t) for _, _, j in batches for _, t in j)} credits")

    for content, out_dir, jobs in batches:
        os.makedirs(out_dir, exist_ok=True)
        for name, text in jobs:
            mp3 = call(key, "POST", f"/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                       {"text": text, "model_id": a.model, "voice_settings": SETTINGS})
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(mp3)
            out = os.path.join(out_dir, f"{name}.wav")
            subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "1", f.name, out], check=True)
            os.unlink(f.name)
            print(f"  wrote {os.path.relpath(out, REPO)}")


if __name__ == "__main__":
    main()
