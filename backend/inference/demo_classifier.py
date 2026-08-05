"""Deterministic tone classifier for exercising QuietCue without ML hardware.

This is deliberately a simulator, not a safety classifier. Each generated demo
tone maps to one AudioSet-like label so transport, profiles, alerts, and the app
can be tested before a microphone or model runtime is available.
"""

from __future__ import annotations

import math
import sys
from array import array

from backend.inference.models import SoundPrediction


DEMO_TONES: dict[int, str] = {
    600: "Doorbell",
    800: "Vehicle horn, car horn, honking",
    1000: "Fire alarm",
    1250: "Siren",
    1600: "Baby cry, infant cry",
    2000: "Alarm clock",
    2500: "Telephone bell ringing",
}


class DemoToneSoundClassifier:
    """Recognize the synthetic tones emitted by ``generate_demo_audio.py``."""

    def classify_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        top_k: int = 10,
    ) -> list[SoundPrediction]:
        if sample_rate != 16_000:
            raise ValueError("Demo classifier requires 16 kHz audio")
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM16 payload must contain complete samples")

        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()

        amplitudes = {
            frequency: _goertzel_amplitude(samples, sample_rate, frequency)
            for frequency in DEMO_TONES
        }
        frequency, amplitude = max(amplitudes.items(), key=lambda item: item[1])
        normalized = amplitude / 32768.0
        if normalized < 0.03:
            return [SoundPrediction("Silence", 0.99)]

        runner_up = max(value for key, value in amplitudes.items() if key != frequency)
        separation = amplitude / max(runner_up, 1.0)
        confidence = min(0.99, 0.78 + min(separation, 8.0) * 0.025)
        predictions = [SoundPrediction(DEMO_TONES[frequency], confidence)]
        if top_k > 1:
            predictions.append(SoundPrediction("Synthetic test tone", 0.08))
        return predictions[:top_k]


def _goertzel_amplitude(samples: array[int], sample_rate: int, frequency: int) -> float:
    coefficient = 2.0 * math.cos(2.0 * math.pi * frequency / sample_rate)
    previous = 0.0
    previous_previous = 0.0
    for sample in samples:
        current = sample + coefficient * previous - previous_previous
        previous_previous = previous
        previous = current
    power = previous_previous**2 + previous**2 - coefficient * previous * previous_previous
    return 2.0 * math.sqrt(max(0.0, power)) / len(samples)
