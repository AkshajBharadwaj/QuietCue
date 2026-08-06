/*
  QuietCue haptic firmware for the Arduino UNO Q (STM32U585 side).

  The Linux side sends semantic alert commands over the App Lab Bridge RPC
  (Arduino_RouterBridge). This sketch owns exact motor timing, so a critical
  pattern keeps running even if the Linux process briefly stalls.

  RPC surface (full contract in uno_q/stm32/README.md):
    play_haptic(pattern, intensity, repeat_count) -> bool
    stop_haptic()                                 -> bool
    get_button_state()                            -> bool
    set_status_led(state)                         -> bool
    get_firmware_version()                        -> String
    health_check()                                -> String

  The pattern engine is a millis()-based state machine driven from loop().
  Nothing in the RPC path blocks or calls delay().
*/

#include <Arduino_RouterBridge.h>

// ---------------------------------------------------------------------------
// Board wiring. These constants must match the physical breadboard; change
// them here in one place if the wiring changes.
//
// The vibration motor must NEVER be driven directly from a GPIO pin. PIN_MOTOR
// drives the gate of a logic-level N-channel MOSFET (or an NPN base through
// about 1 kOhm) that switches the 3 V motor supply, with a flyback diode
// across the motor terminals and a shared ground. Circuit in README.md.
// ---------------------------------------------------------------------------
static const uint8_t PIN_MOTOR = 6;       // PWM-capable output to the MOSFET gate.
static const uint8_t PIN_BUTTON = 2;      // Acknowledge button to GND, uses INPUT_PULLUP.
static const uint8_t PIN_STATUS_LED = 4;  // Status LED through a ~220 ohm resistor.

static const char FIRMWARE_VERSION[] = "quietcue-haptics/0.2.0";

// A pattern is a fixed sequence of motor on/off steps; the whole sequence may
// repeat. The final off time of a sequence doubles as the gap before the next
// repeat cycle.
struct HapticStep {
  uint16_t on_ms;
  uint16_t off_ms;
};

// Informational alternatives: one quick pulse or two distinct quick pulses.
static const HapticStep SHORT_PULSE_STEPS[] = {{140, 300}};
static const HapticStep TWO_SHORT_STEPS[] = {{100, 100}, {100, 350}};
// Attention: one longer pulse.
static const HapticStep LONG_PULSE_STEPS[] = {{600, 400}};
// Emergency: urgent triple burst, repeated until acknowledged or timed out.
static const HapticStep URGENT_STEPS[] = {{250, 100}, {250, 100}, {250, 400}};

static const uint32_t URGENT_TIMEOUT_MS = 30000;
static const int MAX_REPEAT_COUNT = 10;
static const uint8_t MIN_INTENSITY = 60;  // Below this PWM level a coin motor may stall.
static const uint32_t BUTTON_DEBOUNCE_MS = 30;
static const uint16_t URGENT_LED_BLINK_MS = 150;

enum HapticPattern : uint8_t {
  PATTERN_NONE = 0,
  PATTERN_SHORT_PULSE,
  PATTERN_TWO_SHORT,
  PATTERN_LONG_PULSE,
  PATTERN_URGENT_REPEAT,
};

// Pattern engine state. All RPC handlers are registered with provide_safe so
// they are dispatched on the sketch thread; this state is therefore only ever
// touched from loop context and needs no locking.
struct HapticState {
  HapticPattern pattern = PATTERN_NONE;
  const HapticStep *steps = nullptr;
  uint8_t step_count = 0;
  uint8_t step_index = 0;
  bool motor_on = false;
  uint32_t phase_deadline_ms = 0;
  int cycles_remaining = 0;          // Negative means run until ack or timeout.
  uint32_t pattern_deadline_ms = 0;  // Zero means no overall timeout.
  uint8_t intensity = 255;
};

static HapticState haptic;
static bool manual_led_state = false;
static bool button_pressed = false;  // Debounced state, true while held.
static bool button_raw_last = false;
static uint32_t button_change_ms = 0;
static uint32_t patterns_played = 0;
static uint32_t last_ack_ms = 0;

static void motorWrite(bool on) {
  // Full intensity uses a plain digital write so the pattern engine works even
  // if PWM is unavailable on this pin; partial intensity still tries PWM.
  // On this core analogWrite() hands the pin to a hardware timer and a later
  // digitalWrite() alone cannot take it back, so every digital branch must
  // reclaim the pin with pinMode() first.
  if (!on) {
    analogWrite(PIN_MOTOR, 0);
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, LOW);
  } else if (haptic.intensity >= 250) {
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, HIGH);
  } else {
    analogWrite(PIN_MOTOR, haptic.intensity);
  }
#ifdef LED_BUILTIN
  // Mirror the motor state on the built-in LED for wiring-free bench checks.
  // On the UNO Q, LED_BUILTIN is the red channel of the RGB status LED and is
  // wired active-low: LOW lights it.
  digitalWrite(LED_BUILTIN, on ? LOW : HIGH);
#endif
  haptic.motor_on = on;
}

static void stopPattern() {
  haptic.pattern = PATTERN_NONE;
  haptic.steps = nullptr;
  haptic.step_count = 0;
  haptic.step_index = 0;
  haptic.pattern_deadline_ms = 0;
  motorWrite(false);
}

static int clampRepeat(int repeat_count) {
  if (repeat_count < 1) {
    return 1;
  }
  return repeat_count > MAX_REPEAT_COUNT ? MAX_REPEAT_COUNT : repeat_count;
}

static bool startPattern(HapticPattern pattern, int intensity, int repeat_count) {
  const uint32_t now = millis();
  const HapticStep *steps;
  uint8_t step_count;
  int cycles;
  uint32_t deadline = 0;

  switch (pattern) {
    case PATTERN_SHORT_PULSE:
      steps = SHORT_PULSE_STEPS;
      step_count = 1;
      cycles = clampRepeat(repeat_count);
      break;
    case PATTERN_TWO_SHORT:
      steps = TWO_SHORT_STEPS;
      step_count = 2;
      cycles = clampRepeat(repeat_count);
      break;
    case PATTERN_LONG_PULSE:
      steps = LONG_PULSE_STEPS;
      step_count = 1;
      cycles = clampRepeat(repeat_count);
      break;
    case PATTERN_URGENT_REPEAT:
      steps = URGENT_STEPS;
      step_count = 3;
      // repeat_count <= 0 means run until acknowledged or timed out.
      cycles = repeat_count > 0 ? clampRepeat(repeat_count) : -1;
      deadline = now + URGENT_TIMEOUT_MS;
      break;
    default:
      return false;
  }

  haptic.pattern = pattern;
  haptic.steps = steps;
  haptic.step_count = step_count;
  haptic.step_index = 0;
  haptic.cycles_remaining = cycles;
  haptic.pattern_deadline_ms = deadline;
  if (intensity <= 0) {
    haptic.intensity = 255;
  } else {
    haptic.intensity = intensity < MIN_INTENSITY ? MIN_INTENSITY
                       : (intensity > 255 ? 255 : intensity);
  }
  motorWrite(true);
  haptic.phase_deadline_ms = now + steps[0].on_ms;
  patterns_played++;
  return true;
}

static void updatePattern(uint32_t now) {
  if (haptic.pattern == PATTERN_NONE) {
    return;
  }
  if (haptic.pattern_deadline_ms != 0 &&
      (int32_t)(now - haptic.pattern_deadline_ms) >= 0) {
    stopPattern();
    return;
  }
  if ((int32_t)(now - haptic.phase_deadline_ms) < 0) {
    return;
  }

  if (haptic.motor_on) {
    motorWrite(false);
    haptic.phase_deadline_ms = now + haptic.steps[haptic.step_index].off_ms;
    return;
  }

  haptic.step_index++;
  if (haptic.step_index >= haptic.step_count) {
    haptic.step_index = 0;
    if (haptic.cycles_remaining > 0) {
      haptic.cycles_remaining--;
      if (haptic.cycles_remaining == 0) {
        stopPattern();
        return;
      }
    }
  }
  motorWrite(true);
  haptic.phase_deadline_ms = now + haptic.steps[haptic.step_index].on_ms;
}

static void updateButton(uint32_t now) {
  const bool raw = digitalRead(PIN_BUTTON) == LOW;  // Pressed pulls the pin to GND.
  if (raw != button_raw_last) {
    button_raw_last = raw;
    button_change_ms = now;
  }
  if ((now - button_change_ms) >= BUTTON_DEBOUNCE_MS && raw != button_pressed) {
    button_pressed = raw;
    if (button_pressed && haptic.pattern == PATTERN_URGENT_REPEAT) {
      last_ack_ms = now;
      stopPattern();
      // Fire-and-forget event so the Linux side can clear the alert promptly.
      // This is safe here because notify runs from loop context, never from
      // inside an RPC callback. The Linux side may also just poll
      // get_button_state() and ignore this event.
      Bridge.notify("haptic_ack", (int)now);
    }
  }
}

static void updateStatusLed(uint32_t now) {
  // Finite patterns illuminate the LED only while their state is active, so
  // the LED always turns off when the motor sequence completes.
  bool led = manual_led_state || haptic.pattern != PATTERN_NONE;
  if (haptic.pattern == PATTERN_URGENT_REPEAT) {
    led = (now / URGENT_LED_BLINK_MS) % 2 == 0;
  }
  digitalWrite(PIN_STATUS_LED, led ? HIGH : LOW);
}

static const char *patternName(HapticPattern pattern) {
  switch (pattern) {
    case PATTERN_SHORT_PULSE:
      return "short_pulse";
    case PATTERN_TWO_SHORT:
      return "two_short";
    case PATTERN_LONG_PULSE:
      return "long_pulse";
    case PATTERN_URGENT_REPEAT:
      return "urgent_repeat";
    default:
      return "none";
  }
}

// ---------------------------------------------------------------------------
// RPC handlers. Keep every handler fast and non-blocking; the pattern engine
// in loop() owns all timing.
// ---------------------------------------------------------------------------

bool play_haptic(String pattern, int intensity, int repeat_count) {
  HapticPattern requested;
  if (pattern == "short_pulse") {
    requested = PATTERN_SHORT_PULSE;
  } else if (pattern == "two_short") {
    requested = PATTERN_TWO_SHORT;
  } else if (pattern == "long_pulse") {
    requested = PATTERN_LONG_PULSE;
  } else if (pattern == "urgent_repeat") {
    requested = PATTERN_URGENT_REPEAT;
  } else {
    return false;
  }
  // An active emergency pattern is only replaced by another emergency; lower
  // priority requests are refused until it is acknowledged or times out.
  if (haptic.pattern == PATTERN_URGENT_REPEAT && requested != PATTERN_URGENT_REPEAT) {
    return false;
  }
  return startPattern(requested, intensity, repeat_count);
}

bool stop_haptic() {
  stopPattern();
  return true;
}

// Bench diagnostic only: drive the motor pin steady high or low with a plain
// digital write, bypassing the pattern engine and PWM entirely.
bool set_motor_raw(bool on) {
  stopPattern();
  digitalWrite(PIN_MOTOR, on ? HIGH : LOW);
#ifdef LED_BUILTIN
  digitalWrite(LED_BUILTIN, on ? LOW : HIGH);
#endif
  return true;
}

// Bench diagnostic: read back the physical level on the motor pin. The STM32
// samples the real pad, so this confirms whether the header pin actually moved.
bool get_motor_pin() {
  return digitalRead(PIN_MOTOR) == HIGH;
}

bool get_button_state() {
  return button_pressed;
}

bool set_status_led(bool state) {
  manual_led_state = state;
  return true;
}

String get_firmware_version() {
  return String(FIRMWARE_VERSION);
}

String health_check() {
  String report = "{\"ok\":true,\"pattern\":\"";
  report += patternName(haptic.pattern);
  report += "\",\"button\":";
  report += button_pressed ? "true" : "false";
  report += ",\"uptime_ms\":";
  report += millis();
  report += ",\"patterns_played\":";
  report += patterns_played;
  report += ",\"last_ack_ms\":";
  report += last_ack_ms;
  report += "}";
  return report;
}

void setup() {
  pinMode(PIN_MOTOR, OUTPUT);
  digitalWrite(PIN_MOTOR, LOW);
#ifdef LED_BUILTIN
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);  // Active-low on the UNO Q: HIGH is off.
#endif
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, LOW);

  Bridge.begin();
  // provide_safe dispatches the callbacks on the sketch thread so they can
  // touch the pattern engine state without locking.
  Bridge.provide_safe("play_haptic", play_haptic);
  Bridge.provide_safe("stop_haptic", stop_haptic);
  Bridge.provide_safe("set_motor_raw", set_motor_raw);
  Bridge.provide_safe("get_motor_pin", get_motor_pin);
  Bridge.provide_safe("get_button_state", get_button_state);
  Bridge.provide_safe("set_status_led", set_status_led);
  Bridge.provide_safe("get_firmware_version", get_firmware_version);
  Bridge.provide_safe("health_check", health_check);
}

void loop() {
  const uint32_t now = millis();
  updateButton(now);
  updatePattern(now);
  updateStatusLed(now);
}
