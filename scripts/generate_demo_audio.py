#!/usr/bin/env python3
"""Generate a labeled synthetic WAV for QuietCue's no-hardware mode."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.audio.demo_audio import EVENT_FREQUENCIES, write_demo_wav  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", choices=tuple(EVENT_FREQUENCIES))
    parser.add_argument("output", type=Path)
    parser.add_argument("--duration", type=float, default=1.5)
    args = parser.parse_args()
    output = write_demo_wav(args.output, args.event, args.duration)
    print(f"Created {args.event} fixture at {output}")


if __name__ == "__main__":
    main()
