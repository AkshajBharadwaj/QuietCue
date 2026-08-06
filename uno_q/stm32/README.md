# QuietCue STM32 haptic firmware

The STM32U585 side of the Arduino UNO Q owns deterministic motor timing. The
Linux side sends semantic commands such as `urgent_repeat` over the App Lab
Bridge RPC; this firmware turns them into exact vibration patterns and keeps a
critical pattern running even if the Linux process briefly stalls.

Sketch: [`haptics/sketch/sketch.ino`](haptics/sketch/sketch.ino)
Smoke test (runs on the board): [`test_haptics.py`](test_haptics.py)

## RPC contract

All handlers are registered on the sketch with `Bridge.provide_safe` and called
from Linux with `Bridge.call(name, ...)`.

| Method | Arguments | Returns | Notes |
| --- | --- | --- | --- |
| `play_haptic` | `pattern: str, intensity: int, repeat_count: int` | `bool` | `False` for unknown patterns or when refused by priority. |
| `stop_haptic` | — | `bool` | Always stops the motor. |
| `get_button_state` | — | `bool` | Debounced; `True` while the acknowledge button is held. |
| `set_status_led` | `state: bool` | `bool` | Manual LED control; overridden by the emergency blink. |
| `get_motor_pin` | — | `bool` | Reads back the physical motor-pin level (real pad sample) for bench debugging. |
| `get_firmware_version` | — | `str` | `quietcue-haptics/0.2.0` |
| `health_check` | — | `str` | Compact JSON: active pattern, button, uptime, counters. |

The firmware also emits a fire-and-forget event to the Linux side when an
emergency pattern is acknowledged: `haptic_ack(uptime_ms)`. Handling it is
optional; polling `get_button_state` works too.

### Patterns

Four small patterns cover the haptic language in `AGENTS.md`:

| Pattern | Category | Behavior |
| --- | --- | --- |
| `short_pulse` | informational | One quick 140 ms pulse. |
| `two_short` | informational | Two 100 ms pulses. |
| `long_pulse` | attention | One 600 ms pulse. |
| `urgent_repeat` | emergency | Repeating triple bursts until the acknowledge button is pressed or a 30 s timeout expires. |

Rules:

- `intensity` is PWM 1–255; values below 60 are raised to 60 so a coin motor
  does not stall; `0` means full power.
- `repeat_count` is clamped to 1–10. For `urgent_repeat`, `0` (the normal case)
  means "until acknowledged or timed out".
- Priority: while `urgent_repeat` is active, `play_haptic` refuses `two_short`
  and `long_pulse` (returns `False`). A new `urgent_repeat` restarts the
  emergency pattern. `stop_haptic` always wins.
- All timing is a `millis()`-based state machine in `loop()`; the RPC path
  never blocks and never calls `delay()`.

## Wiring

Never drive the vibration motor directly from a GPIO pin. The motor draws far
more current than a pin can source and its inductive kickback can damage the
microcontroller.

```
3V3 motor supply ----+
                     |
                 [ motor ]--+--|<|-- flyback diode (e.g. 1N4148/1N5819),
                     |      |        cathode toward supply, in parallel
                     +------+        with the motor
                     |
                 [ MOSFET drain ]
D6  --[ ~100R ]--[ MOSFET gate  ]   logic-level N-channel (e.g. AO3400, 2N7000)
                 [ MOSFET source]---- GND (shared with the board)
D2  ---- acknowledge button ---- GND   (pin uses INPUT_PULLUP)
D4  --[ 220R ]--[ status LED ]-- GND
```

The sketch also mirrors the motor state on the board's built-in LED: on the
UNO Q this is the **red channel of the RGB status LED (PH10), wired
active-low**. Red flashing in step with the motor is normal; the factory
firmware's blue idle animation disappears once this sketch is flashed.

Pin assignments are constants at the top of the sketch (`PIN_MOTOR = 6`,
`PIN_BUTTON = 2`, `PIN_STATUS_LED = 4`) and MUST match the actual breadboard.
If you rewire, change them there in one place. If an NPN transistor is used
instead of a MOSFET, drive the base through about 1 kOhm.

## Flash and deploy with App Lab

1. Open Arduino App Lab on the UNO Q (or connect from a PC per the App Lab
   docs) and create/open an app for the wearable.
2. Copy `haptics/sketch/sketch.ino` into the app's `sketch/` folder. The
   `Arduino_RouterBridge` library ships with the UNO Q core; add it via the
   library manager if the build cannot find `Arduino_RouterBridge.h`.
3. Run the app. App Lab compiles the sketch, flashes the STM32, and starts the
   Bridge router.

## Smoke test from the Linux side

With the sketch flashed and the App Lab runtime active, the executable
`buzz.sh` helper is the simplest test path. It finds the running App Lab
container and makes the Bridge call inside it. On the board:

```bash
cd ~/projects/QuietCue/uno_q/stm32
./buzz.sh                 # status only; does not activate the motor
./buzz.sh short_pulse     # bounded one-pulse test
./buzz.sh two_short       # bounded two-pulse test
./buzz.sh long_pulse
./buzz.sh urgent          # press the button, run stop, or wait for 30 s timeout
./buzz.sh stop
```

Run `./buzz.sh help` for the full command list. The raw `on` bench diagnostic
has no automatic timeout and should not be used for normal pattern testing.

The Python CLI exposes the same RPCs when run from an environment where the
App Lab Bridge module is directly importable:

```bash
python3 uno_q/stm32/test_haptics.py status
python3 uno_q/stm32/test_haptics.py short_pulse
python3 uno_q/stm32/test_haptics.py two_short
python3 uno_q/stm32/test_haptics.py long_pulse
python3 uno_q/stm32/test_haptics.py urgent_repeat   # press the button to ack
python3 uno_q/stm32/test_haptics.py all
```

Expected behavior: `short_pulse` buzzes once briefly, `two_short` buzzes twice,
`long_pulse` buzzes once for over half a second, and `urgent_repeat` keeps bursting (status LED
blinking) until the button is pressed or 30 seconds pass. `health_check`
should report the active pattern while one is running.

## Assumptions to verify on real hardware

These followed the published `Arduino_RouterBridge` and App Lab examples and
were mostly confirmed on real hardware on 2026-08-06:

1. **Verified.** `Bridge.provide_safe` exists on core 0.90.0 and all handler
   signatures (`String`, `bool`, `int`) dispatch correctly; RPC round trips
   measure 6–15 ms.
2. **Verified.** `from arduino.app_utils import Bridge` plus
   `Bridge.call("play_haptic", "two_short", 255, 1)` work as written.
3. Still unverified: `Bridge.notify("haptic_ack", ...)` has not been observed
   end-to-end yet (needs a wired button press during `urgent_repeat`).
4. **Verified.** D6 maps to PB1 with TIM3_CH4 PWM on the UNO Q overlay.
   Caveat discovered on hardware: `analogWrite()` on this core hands the pin
   to the timer via dynamic pinctrl and a later `digitalWrite()` alone cannot
   reclaim it — the sketch must call `pinMode(pin, OUTPUT)` before every
   digital write that follows an `analogWrite` (fixed in firmware 0.1.1).
