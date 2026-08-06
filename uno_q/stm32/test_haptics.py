"""Manual smoke test for the QuietCue haptic firmware.

This script runs ON the Arduino Uno Q Linux side, not on a development PC.
It talks to the STM32 sketch in ``uno_q/stm32/haptics`` through the App Lab
Bridge RPC, so the sketch must already be flashed and the App Lab runtime
(router) must be running.

Examples, from the deployed repository root on the board:

    python3 uno_q/stm32/test_haptics.py status
    python3 uno_q/stm32/test_haptics.py two_short
    python3 uno_q/stm32/test_haptics.py urgent_repeat   # press the button to ack
    python3 uno_q/stm32/test_haptics.py all
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

try:
    from arduino.app_utils import Bridge  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - the bridge only exists on the board.
    Bridge: Any | None = None


PATTERNS = ("short_pulse", "two_short", "long_pulse", "urgent_repeat")
# Worst-case audible duration per pattern so `all` waits long enough between
# patterns: urgent_repeat is capped by the firmware's 30 s timeout, but the
# smoke test acknowledges it early via stop_haptic.
PATTERN_SETTLE_SECONDS = {
    "short_pulse": 1.0,
    "two_short": 2.0,
    "long_pulse": 2.0,
    "urgent_repeat": 6.0,
}


def call(method: str, *args: object) -> object:
    """Invoke one firmware RPC and report the round trip."""
    if Bridge is None:
        raise RuntimeError("Arduino App Lab Bridge is unavailable")
    started = time.perf_counter()
    result = Bridge.call(method, *args)
    elapsed_ms = (time.perf_counter() - started) * 1_000
    print(f"{method}{args!r} -> {result!r} ({elapsed_ms:.1f} ms)")
    return result


def show_status() -> None:
    call("get_firmware_version")
    call("health_check")
    call("get_button_state")


def play(pattern: str, intensity: int, repeat: int) -> None:
    accepted = call("play_haptic", pattern, intensity, repeat)
    if not accepted:
        print(
            f"Firmware refused pattern {pattern!r}. An emergency pattern may be "
            "active; acknowledge it with the button or run stop first.",
            file=sys.stderr,
        )


def run_all(intensity: int, repeat: int) -> None:
    for pattern in PATTERNS:
        print(f"--- {pattern} ---")
        play(pattern, intensity, repeat)
        time.sleep(PATTERN_SETTLE_SECONDS[pattern])
        if pattern == "urgent_repeat":
            call("stop_haptic")
    show_status()


def main() -> None:
    if Bridge is None:
        print(
            "The Arduino App Lab bridge module is not available. Run this script on "
            "the Uno Q Linux side inside an App Lab environment (the same Python "
            "that App Lab apps use), not on a development PC.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command",
        choices=(*PATTERNS, "stop", "status", "led-on", "led-off", "all"),
        help="Pattern to play, or a utility command",
    )
    parser.add_argument(
        "--intensity",
        type=int,
        default=255,
        help="Motor PWM intensity 1-255 (0 or omitted means full power)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Sequence repeat count; 0 with urgent_repeat means until ack or timeout",
    )
    args = parser.parse_args()

    if args.command == "status":
        show_status()
    elif args.command == "stop":
        call("stop_haptic")
    elif args.command == "led-on":
        call("set_status_led", True)
    elif args.command == "led-off":
        call("set_status_led", False)
    elif args.command == "all":
        run_all(args.intensity, args.repeat)
    else:
        play(args.command, args.intensity, args.repeat)


if __name__ == "__main__":
    main()
