#!/bin/zsh
# Start Open Canvas with no typing: double-click this file, or say "Hey Siri, Open Canvas"
# (a Shortcut that runs: open ~/Desktop/open-canvas/start_open_canvas.command).
# Opens in Terminal, which already has camera permission. Finds the Uno/ESP32 port itself.

cd "${0:A:h}"
source .venv/bin/activate

# (N) = no error if a pattern matches nothing (zsh aborts the line otherwise)
ports=(/dev/cu.usbmodem*(N) /dev/cu.usbserial*(N))
port=${ports[1]}
if [[ -n "$port" ]]; then
  echo "[start] motor board on $port"
  python -m app.main --serial "$port"
else
  echo "[start] no motor board found: running without the motor"
  say "Motor not connected. Starting without it."
  python -m app.main
fi
