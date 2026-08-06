"""Linux-side host process for the QuietCue haptic firmware.

App Lab flashes the sketch in ``../sketch`` to the STM32 and then runs this
process. Normal startup performs a non-actuating health check and then stays
alive so the QuietCue host client can use the Bridge. Set
``QUIETCUE_HAPTICS_STARTUP_SMOKE=1`` only for an attended bench test that may
activate the motor.
"""

from __future__ import annotations

import os
import time

from arduino.app_utils import App, Bridge


def _call(method: str, *args: object) -> object:
    """Invoke one firmware RPC and log the round trip."""
    started = time.perf_counter()
    try:
        result = Bridge.call(method, *args)
        elapsed_ms = (time.perf_counter() - started) * 1_000
        print(f"[smoke] {method}{args!r} -> {result!r} ({elapsed_ms:.1f} ms)", flush=True)
        return result
    except Exception as exc:  # Log and continue so one failure doesn't hide the rest.
        elapsed_ms = (time.perf_counter() - started) * 1_000
        print(f"[smoke] {method}{args!r} FAILED after {elapsed_ms:.1f} ms: {exc}", flush=True)
        return None


def run_smoke_test() -> None:
    """Exercise every RPC once. Patterns are brief; urgent_repeat is stopped early."""
    print("[smoke] QuietCue haptic firmware smoke test starting", flush=True)
    _call("get_firmware_version")
    _call("health_check")
    _call("get_button_state")
    _call("set_status_led", True)

    _call("play_haptic", "short_pulse", 120, 1)
    time.sleep(1.0)
    _call("play_haptic", "two_short", 255, 1)
    time.sleep(1.5)
    _call("play_haptic", "long_pulse", 200, 1)
    time.sleep(1.5)
    _call("play_haptic", "urgent_repeat", 255, 0)
    time.sleep(2.0)
    _call("stop_haptic")

    _call("set_status_led", False)
    _call("health_check")
    print("[smoke] done; staying alive for Bridge RPC use", flush=True)


def run_startup_health_check() -> None:
    """Verify the Bridge without energizing the motor."""
    print("[startup] QuietCue haptic Bridge health check", flush=True)
    _call("get_firmware_version")
    _call("health_check")


if os.environ.get("QUIETCUE_HAPTICS_STARTUP_SMOKE") == "1":
    run_smoke_test()
else:
    run_startup_health_check()

App.run()
