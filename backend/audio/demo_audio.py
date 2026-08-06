"""Synthetic audio fixtures used only by the no-hardware development mode."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from backend.audio.wav_source import SAMPLE_RATE
from backend.inference.demo_classifier import DEMO_TONES


EVENT_FREQUENCIES = {
    "doorbell_knock": 600,
    "car_horn": 800,
    "fire_alarm": 1000,
    "siren": 1250,
    "baby_crying": 1600,
    "kitchen_timer": 2000,
    "phone_ringing": 2500,
    "vacuum_cleaner": 3150,
}

assert set(EVENT_FREQUENCIES.values()) == set(DEMO_TONES)


def generate_tone_pcm(
    event: str,
    duration_seconds: float = 1.0,
    amplitude: float = 0.35,
) -> bytes:
    if event not in EVENT_FREQUENCIES:
        choices = ", ".join(EVENT_FREQUENCIES)
        raise ValueError(f"Unknown demo event {event!r}; choose one of: {choices}")
    if not 0.0 < duration_seconds <= 30.0:
        raise ValueError("duration_seconds must be between 0 and 30")
    if not 0.0 < amplitude <= 0.95:
        raise ValueError("amplitude must be between 0 and 0.95")

    frequency = EVENT_FREQUENCIES[event]
    frame_count = round(SAMPLE_RATE * duration_seconds)
    peak = round(32767 * amplitude)
    samples = (
        round(peak * math.sin(2.0 * math.pi * frequency * index / SAMPLE_RATE))
        for index in range(frame_count)
    )
    return b"".join(struct.pack("<h", sample) for sample in samples)


def write_demo_wav(
    path: str | Path,
    event: str,
    duration_seconds: float = 1.0,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(generate_tone_pcm(event, duration_seconds))
    return output_path
