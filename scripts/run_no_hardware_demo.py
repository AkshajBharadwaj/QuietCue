#!/usr/bin/env python3
"""Run one complete WAV-to-alert QuietCue loop with no external dependencies."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.audio.demo_audio import EVENT_FREQUENCIES, write_demo_wav  # noqa: E402
from backend.profiles.defaults import all_profiles  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", choices=tuple(EVENT_FREQUENCIES), default="fire_alarm")
    parser.add_argument("--profile", choices=tuple(all_profiles()), default="home")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="quietcue-demo-") as temporary_directory:
        wav_path = write_demo_wav(
            Path(temporary_directory) / f"{args.event}.wav",
            args.event,
            duration_seconds=1.0,
        )
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "backend.app.hub_server",
                "--classifier",
                "demo",
                "--profile",
                args.profile,
            ],
            cwd=REPOSITORY_ROOT,
        )
        try:
            _wait_until_ready()
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "uno_q.linux.transport.hub_client",
                    str(wav_path),
                    "--pc",
                    "127.0.0.1:8765",
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
            )
            with urllib.request.urlopen("http://127.0.0.1:8787/api/state", timeout=2) as response:
                state = json.load(response)
            latest = state.get("latest_alert")
            if latest is None:
                print(f"No alert emitted: {args.event} was suppressed by profile {args.profile}.")
            else:
                print(
                    "Completed no-hardware loop: "
                    f"{latest['event']} -> {latest['pattern']} "
                    f"({latest['total_after_capture_ms']} ms after replay capture)"
                )
        finally:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=3)


def _wait_until_ready() -> None:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8787/health", timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("QuietCue demo hub did not start within five seconds")


if __name__ == "__main__":
    main()
