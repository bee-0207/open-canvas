"""
make_voices_say.py: pre-render a painting's spoken overview and region descriptions with the
built-in macOS voice (`say`). Free and offline; a stand-in until the clips are re-rendered
with tools/make_voices_elevenlabs.py (same --content / --out options).

    .venv/bin/python tools/make_voices_say.py --content content/library/great_wave
    .venv/bin/python tools/make_voices_say.py --all          # every painting in content/library/

Text comes from <content>/overview.txt and the "description" fields in <content>/regions.json.
Output: <out>/overview.wav and <out>/region_<id>.wav (default out: <content>/voice), converted
with macOS `afconvert` to 48 kHz mono 16-bit WAV, the engine's rate.
"""

import argparse
import json
import os
import subprocess
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render(text, wav, voice, rate):
    with tempfile.TemporaryDirectory() as tmp:
        aiff = os.path.join(tmp, "clip.aiff")
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", aiff, text], check=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "1", aiff, wav], check=True)


def make(content, out, voice, rate):
    os.makedirs(out, exist_ok=True)
    jobs = [("overview", open(os.path.join(content, "overview.txt")).read().strip())]
    for rid, info in json.load(open(os.path.join(content, "regions.json"))).items():
        if info.get("description"):
            jobs.append((f"region_{rid}", info["description"]))
    for name, text in jobs:
        render(text, os.path.join(out, name + ".wav"), voice, rate)
    print(f"{os.path.relpath(content, REPO)}: {len(jobs)} clips -> {os.path.relpath(out, REPO)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--content", help="painting folder (overview.txt + regions.json)")
    ap.add_argument("--out", help="output folder (default: <content>/voice)")
    ap.add_argument("--all", action="store_true", help="every folder in content/library/")
    ap.add_argument("--voice", default="Samantha")
    ap.add_argument("--rate", type=int, default=165, help="words per minute (macOS default ~175)")
    a = ap.parse_args()
    if a.all:
        lib = os.path.join(REPO, "content", "library")
        for slug in sorted(os.listdir(lib)):
            if os.path.exists(os.path.join(lib, slug, "regions.json")):
                make(os.path.join(lib, slug), os.path.join(lib, slug, "voice"), a.voice, a.rate)
    elif a.content:
        content = os.path.abspath(a.content)
        make(content, os.path.abspath(a.out) if a.out else os.path.join(content, "voice"), a.voice, a.rate)
    else:
        ap.error("give --content <folder> or --all")


if __name__ == "__main__":
    main()
