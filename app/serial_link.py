"""Laptop side of the ESP32 serial protocol (CLAUDE.md section 7).

    115200 baud, one ASCII command per line ("\\n"-terminated)
    laptop -> ESP32:  M1 motor on, M0 motor off   (sent only when the state changes)
    ESP32 -> laptop:  B1 button pressed, B0 button released

Contents:
    SerialLink   set_motor(on) and poll() -> list of "B1"/"B0" events; never blocks
    NullLink     same interface, does nothing; used when no ESP32 is connected

Gotchas:
- Opening the port resets most ESP32 dev boards (the USB chip toggles EN), so the first
  second or so is boot-log noise. Anything that isn't exactly B1/B0 is ignored.
- If the board is unplugged mid-run, the link logs it once and turns into a no-op instead
  of crashing the demo.
"""

import serial


class NullLink:
    def set_motor(self, on):
        pass

    def poll(self):
        return []

    def close(self):
        pass


class SerialLink:
    def __init__(self, port, baud=115200):
        # timeout=0 makes reads non-blocking: the main loop must never wait on the ESP32
        self._ser = serial.Serial(port, baud, timeout=0)
        self._buf = b""
        self._motor = None   # unknown until the first command, so the first set_motor() always sends
        print(f"[serial] opened {port} at {baud}")

    def set_motor(self, on):
        if self._ser is None or on == self._motor:
            return
        self._motor = on
        self._write(b"M1\n" if on else b"M0\n")

    def poll(self):
        """Return button events received since the last call, oldest first."""
        if self._ser is None:
            return []
        try:
            self._buf += self._ser.read(self._ser.in_waiting or 1)
        except serial.SerialException as e:
            self._lost(e)
            return []
        events = []
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if line in (b"B1", b"B0"):
                events.append(line.decode())
        return events

    def _write(self, data):
        try:
            self._ser.write(data)
        except serial.SerialException as e:
            self._lost(e)

    def _lost(self, e):
        print(f"[serial] lost the ESP32 ({e}); motor and button are off from now on")
        try:
            self._ser.close()
        except Exception:
            pass
        self._ser = None

    def close(self):
        if self._ser is not None:
            self.set_motor(False)
            self._ser.close()
            self._ser = None
