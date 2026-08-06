"""Linux-side host process for the QuietCue haptic firmware.

App Lab flashes the sketch in ``../sketch`` to the STM32 and then runs this
process. On startup it exercises every firmware RPC once and logs the round
trips, so ``arduino-app-cli app logs`` doubles as a hardware smoke test. It
then stays alive so the Bridge remains available; the QuietCue hub client can
later reuse this process as its haptic transport.
"""

from __future__ import annotations

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


run_smoke_test()

App.run()
