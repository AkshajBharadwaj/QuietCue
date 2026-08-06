"""Persistent Arduino App Lab Bridge transport for the Uno Q Linux client.

``arduino.app_utils`` is available inside App Lab, not in the Uno Q host
Python installation. This adapter starts one long-lived ``docker exec`` worker
inside the running QuietCue App Lab container and exchanges newline-delimited
JSON with it. The one-time container startup cost happens before streaming;
normal Bridge calls then retain their native millisecond-scale latency.
"""

from __future__ import annotations

import atexit
import json
import os
import select
import subprocess
from collections.abc import Callable
from typing import Any, TextIO


DEFAULT_CONTAINER_NAME = "quietcue-haptics-main-1"
DEFAULT_BRIDGE_TIMEOUT_SECONDS = 8

_BRIDGE_WORKER_SCRIPT = r"""
import json
import sys

from arduino.app_utils import Bridge

for line in sys.stdin:
    try:
        request = json.loads(line)
        result = Bridge.call(
            request["method"],
            *request.get("args", []),
            timeout=request.get("timeout", 8),
        )
        response = {"ok": True, "result": result}
    except Exception as exc:
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(response, separators=(",", ":")), flush=True)
"""


class AppLabBridgeError(RuntimeError):
    """Raised when the App Lab container or STM32 Bridge call is unavailable."""


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
ProcessFactory = Callable[..., subprocess.Popen[str]]


class AppLabBridgeHapticTransport:
    """Call STM32 RPC handlers through one persistent App Lab worker."""

    def __init__(
        self,
        container_name: str | None = None,
        *,
        docker_executable: str = "docker",
        bridge_timeout_seconds: int = DEFAULT_BRIDGE_TIMEOUT_SECONDS,
        command_runner: RunCommand = subprocess.run,
        process_factory: ProcessFactory = subprocess.Popen,
    ) -> None:
        configured = container_name or os.environ.get("QUIETCUE_HAPTICS_CONTAINER")
        self._container_name = configured.strip() if configured else None
        self._docker = docker_executable
        self._bridge_timeout = bridge_timeout_seconds
        self._run = command_runner
        self._process_factory = process_factory
        self._worker: subprocess.Popen[str] | None = None
        atexit.register(self.close)

    def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> bool:
        return bool(self._call("play_haptic", pattern, intensity, repeat_count))

    def stop_haptic(self) -> bool:
        return bool(self._call("stop_haptic"))

    def get_button_state(self) -> bool:
        return bool(self._call("get_button_state"))

    def set_status_led(self, state: bool) -> bool:
        return bool(self._call("set_status_led", state))

    def health_check(self) -> bool:
        result = self._call("health_check")
        if isinstance(result, bool):
            return result
        if isinstance(result, str):
            try:
                document = json.loads(result)
            except json.JSONDecodeError as exc:
                raise AppLabBridgeError(f"Invalid firmware health response: {result!r}") from exc
            return bool(document.get("ok", False)) if isinstance(document, dict) else False
        return False

    def firmware_version(self) -> str:
        return str(self._call("get_firmware_version"))

    def close(self) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        if worker.stdin is not None:
            try:
                worker.stdin.close()
            except OSError:
                pass
        try:
            worker.wait(timeout=2)
        except subprocess.TimeoutExpired:
            worker.terminate()
            try:
                worker.wait(timeout=2)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=2)
        if worker.stdout is not None:
            worker.stdout.close()

    def _call(self, method: str, *args: object) -> Any:
        request = json.dumps(
            {"method": method, "args": args, "timeout": self._bridge_timeout},
            separators=(",", ":"),
        )
        last_error = "Bridge worker did not respond"
        for attempt in range(2):
            worker = self._ensure_worker(refresh=attempt > 0)
            stdin, stdout = worker.stdin, worker.stdout
            if stdin is None or stdout is None:
                self.close()
                last_error = "Bridge worker has no input/output pipes"
                continue
            try:
                stdin.write(request + "\n")
                stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.close()
                last_error = f"{type(exc).__name__}: {exc}"
                continue

            response = self._read_response(stdout)
            if response is None:
                self.close()
                last_error = "Bridge worker exited or timed out"
                continue
            if response.get("ok") is True:
                return response.get("result")
            # Do not automatically replay a call after the worker received it;
            # a timed-out motor command may still have reached the STM32.
            raise AppLabBridgeError(
                f"{method} failed: {response.get('error') or 'unknown Bridge error'}"
            )

        raise AppLabBridgeError(f"{method} failed: {last_error}")

    def _read_response(self, stdout: TextIO) -> dict[str, Any] | None:
        ready, _, _ = select.select([stdout], [], [], self._bridge_timeout + 4)
        if not ready:
            return None
        line = stdout.readline()
        if not line:
            return None
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AppLabBridgeError(f"Invalid Bridge worker response: {line!r}") from exc
        if not isinstance(value, dict):
            raise AppLabBridgeError(f"Invalid Bridge worker response: {value!r}")
        return value

    def _ensure_worker(self, *, refresh: bool) -> subprocess.Popen[str]:
        if self._worker is not None and self._worker.poll() is None and not refresh:
            return self._worker
        self.close()
        container = self._resolve_container(refresh=refresh)
        try:
            self._worker = self._process_factory(
                [
                    self._docker,
                    "exec",
                    "-i",
                    container,
                    "python",
                    "-u",
                    "-c",
                    _BRIDGE_WORKER_SCRIPT,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise AppLabBridgeError(f"Cannot start App Lab Bridge worker: {exc}") from exc
        return self._worker

    def _resolve_container(self, *, refresh: bool) -> str:
        if self._container_name and not refresh:
            return self._container_name

        try:
            completed = self._run(
                [self._docker, "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AppLabBridgeError(f"Cannot list App Lab containers: {exc}") from exc
        if completed.returncode != 0:
            raise AppLabBridgeError(completed.stderr.strip() or "Cannot list App Lab containers")

        names = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if DEFAULT_CONTAINER_NAME in names:
            self._container_name = DEFAULT_CONTAINER_NAME
            return DEFAULT_CONTAINER_NAME
        matches = [
            name
            for name in names
            if "quietcue" in name.lower() and "haptics" in name.lower() and "main" in name.lower()
        ]
        if len(matches) == 1:
            self._container_name = matches[0]
            return matches[0]
        if not matches:
            raise AppLabBridgeError(
                "QuietCue Haptics App Lab container is not running; start the app and retry"
            )
        raise AppLabBridgeError(
            "Multiple QuietCue haptics containers are running; set QUIETCUE_HAPTICS_CONTAINER"
        )
