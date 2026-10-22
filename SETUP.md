# Open Canvas: Dev Environment Setup

Every teammate follows this once per laptop. It takes about 10 minutes.
If you use Claude Code, you can tell it: **"Follow SETUP.md exactly."**

The goal: a Python **3.11** virtual environment at `.venv/` inside the repo, with the exact
package versions from `requirements.txt`, passing the check in step 5.

---

## Rules (read before doing anything)

1. **Python must be 3.11.x.** Not 3.12, 3.13, 3.14 or 3.15. MediaPipe lags behind new
   Python releases, and everyone must run the same version. Do not change the system's
   default `python3`; install 3.11 *alongside* it.
2. **Always use the project venv** (`.venv/`). Never `pip install` into the system Python
   and never use `sudo pip`.
3. **Never install `opencv-python`.** Only `opencv-contrib-python` (already in
   `requirements.txt`). MediaPipe depends on the contrib build, and having both installed
   makes them overwrite each other's files in the same `cv2` folder.
4. **Don't change pinned versions** in `requirements.txt` without telling the team.
5. **Never commit `.venv/`, `.env`, or video files.** `.gitignore` already excludes them;
   don't override it with `git add -f`.

---

## 1. Accept the GitHub invite and clone

The repo is private. Accept the invite at https://github.com/notifications (or from the
email), then:

```bash
cd ~/Desktop            # or wherever you keep projects
git clone https://github.com/bee-0207/open-canvas.git
cd open-canvas
```

If the clone asks for a password or says "repository not found", the invite hasn't been
accepted yet, or you're not logged in (`gh auth login`).

## 2. Install Python 3.11 (alongside your existing Python)

First check if it's already there: `python3.11 --version` (macOS/Linux) or
`py -3.11 --version` (Windows). If it prints `Python 3.11.x`, skip to step 3.

**macOS** (Homebrew):
```bash
brew install python@3.11
python3.11 --version
```

**Windows** (PowerShell):
```powershell
winget install -e --id Python.Python.3.11
py -3.11 --version
```
If `py` isn't found, close and reopen the terminal.

**Linux** (Ubuntu/Debian):
```bash
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv libportaudio2
python3.11 --version
```
`libportaudio2` is required by `sounddevice` on Linux (macOS and Windows wheels bundle it).

## 3. Create the virtual environment

Run from the repo root (`open-canvas/`).

**macOS / Linux:**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```
If PowerShell blocks the script, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.

Your prompt should now start with `(.venv)`. Confirm: `python --version` → `Python 3.11.x`.

## 4. Install the packages

With the venv active:
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Verify

With the venv active, run this exact command (one line):

```bash
python -c "import sys, cv2, mediapipe, numpy, sounddevice, soundfile, serial, yaml; assert sys.version_info[:2]==(3,11), sys.version; assert hasattr(cv2.aruco,'ArucoDetector'); assert hasattr(mediapipe.tasks.vision,'HandLandmarker'); print('OK', sys.version.split()[0], 'cv2', cv2.__version__, 'mediapipe', mediapipe.__version__, '| audio out:', sounddevice.query_devices(kind='output')['name'])"
```

Expected output (audio device name will differ):
```
OK 3.11.x cv2 5.0.0 mediapipe 1.1.1 | audio out: <your speakers>
```

Then run both of these:
```bash
pip check                              # expected: "No broken requirements found."
pip list | grep -i opencv              # Windows: pip list | findstr /i opencv
```
The second must show **only** `opencv-contrib-python`. If `opencv-python` also appears:
```bash
pip uninstall -y opencv-python opencv-contrib-python
pip install -r requirements.txt
```

## 6. Every time you work on the project

```bash
cd open-canvas
source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
git pull
```

To leave the venv: `deactivate`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No matching distribution found for mediapipe` | The venv isn't 3.11. Delete `.venv/` and redo step 3 with `python3.11` / `py -3.11`. |
| `ModuleNotFoundError` when running code | The venv isn't active. Activate it (step 6). |
| `python3.11: command not found` after brew install | Run `brew --prefix python@3.11` and use `<that path>/bin/python3.11`. |
| `sounddevice` error: `PortAudio library not found` (Linux) | `sudo apt install libportaudio2` |
| Webcam opens but frames are black (macOS) | System Settings → Privacy & Security → Camera → enable your terminal / IDE. |
| Can't open the ESP32 serial port (Linux) | `sudo usermod -aG dialout $USER`, then log out and back in. |
| ESP32 not showing as a port (Windows) | Install the USB-serial driver for the board's chip (CP210x or CH340), then check Device Manager → Ports. |

## Notes for Claude Code

- Project context, architecture and team interface contracts are in `CLAUDE.md`. Read it
  before writing code.
- Use the venv's interpreter for everything: `.venv/bin/python` (macOS/Linux) or
  `.venv\Scripts\python.exe` (Windows).
- Don't add packages without asking the user; if one is approved, pin its exact version in
  `requirements.txt` and say so in the commit message.
- Setup is done only when every check in step 5 passes. Report the exact output.
