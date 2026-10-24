// Open Canvas firmware for the Arduino Uno R3: fingertip motor + "describe" arcade button.
// (A teammate is building the same thing on an ESP32 in firmware/open_canvas_esp32/;
// both speak the same protocol, so the laptop works with either.)
//
// Serial protocol (CLAUDE.md section 7), 115200 baud, one ASCII command per line:
//   laptop -> Uno:  M1 = motor on, M0 = motor off
//   Uno -> laptop:  B1 = button pressed, B0 = button released (only on a change)
// Anything else received is ignored. The laptop side (app/serial_link.py) ignores every
// line that isn't exactly B1/B0, so the READY line below is harmless.
//
// Wiring:
//   D9 -> 470 ohm -> PN2222 base. Emitter -> GND. Collector -> motor (-).
//   Motor (+) -> 3.3V pin (the coin motor is rated 3 V; 5 V would overdrive it).
//   1N4148 across the motor, stripe (cathode) on the 3.3V side.
//   47-100 uF capacitor across 3.3V/GND near the motor.
//   Button: COM -> GND, NO -> D2. Internal pull-up, so pressed = LOW.
//
// Why 470 ohm and not the ESP32's 220: Uno pins are 5 V, so
//   I_B = (5 - 0.7) / 470 = 9.1 mA   (220 ohm would be 19.5 mA, at the 20 mA per-pin limit).
// With a ~80 mA motor that's a forced beta of ~9, far below the PN2222's gain, so the
// transistor is still fully on.
//
// Pins avoided: D0/D1 are the USB serial lines; D13 blinks during boot (bootloader),
// which would twitch the motor.
//
// The onboard "L" LED (D13) mirrors the motor after boot, so M1/M0 can be checked before
// the motor is wired. Bench test: Arduino Serial Monitor at 115200, "Newline" line ending,
// type M1 / M0, press the button to see B1 / B0.

const int MOTOR_PIN = 9;
const int BUTTON_PIN = 2;
const int LED_PIN = LED_BUILTIN;  // D13

const unsigned long DEBOUNCE_MS = 25;  // spec: 20-30 ms

// Button debounce state: report a new level only after it has been stable for DEBOUNCE_MS.
// Switch contacts bounce (flicker open/closed) for a few ms on every press and release;
// without this, one press could send B1 B0 B1 B0 ...
int stableLevel = HIGH;  // HIGH = released (pull-up)
int lastReading = HIGH;
unsigned long lastChangeMs = 0;

// Incoming command line buffer
char line[16];
byte lineLen = 0;

void setMotor(bool on) {
  digitalWrite(MOTOR_PIN, on ? HIGH : LOW);
  digitalWrite(LED_PIN, on ? HIGH : LOW);
}

void handleLine(const char *cmd) {
  if (strcmp(cmd, "M1") == 0) {
    setMotor(true);
  } else if (strcmp(cmd, "M0") == 0) {
    setMotor(false);
  }
}

void readSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      line[lineLen] = '\0';
      handleLine(line);
      lineLen = 0;
    } else if (c == '\r') {
      // Serial monitors may send \r\n; ignore the \r
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    } else {
      lineLen = 0;  // garbage longer than any command: drop it
    }
  }
}

void readButton() {
  int reading = digitalRead(BUTTON_PIN);
  unsigned long now = millis();
  if (reading != lastReading) {
    lastReading = reading;
    lastChangeMs = now;  // still bouncing: restart the timer
  }
  if (reading != stableLevel && now - lastChangeMs >= DEBOUNCE_MS) {
    stableLevel = reading;
    Serial.println(stableLevel == LOW ? "B1" : "B0");
  }
}

void setup() {
  pinMode(MOTOR_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  setMotor(false);  // motor off from the first moment
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  Serial.begin(115200);
  Serial.println("OPEN_CANVAS READY UNO motor=D9 button=D2");
}

void loop() {
  readSerial();
  readButton();
}
