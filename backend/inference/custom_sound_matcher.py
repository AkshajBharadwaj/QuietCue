"""Experimental local acoustic fingerprints for user-enrolled sounds.

The matcher mirrors the Android enrollment feature extractor. It is an MVP seam
for validating enrollment and profile behavior, not a safety-grade embedding
model. A measured learned embedding can replace it without changing sound IDs or
profile rules.
"""

from __future__ import annotations

import math
import sys
from array import array

from backend.inference.pipeline import ConfirmedEvent
from backend.profiles.engine import CustomSoundPrototype


SAMPLE_RATE = 16_000
FREQUENCIES = (250, 375, 500, 750, 1_000, 1_500, 2_000, 3_000)


class CustomSoundMatcher:
    def __init__(self, prototypes: tuple[CustomSoundPrototype, ...] = ()) -> None:
        self._prototypes = prototypes

    def set_prototypes(self, prototypes: tuple[CustomSoundPrototype, ...]) -> None:
        self._prototypes = prototypes

    def match_pcm16(self, pcm: bytes, sample_rate: int) -> tuple[ConfirmedEvent, ...]:
        prototypes = self._prototypes
        if not prototypes:
            return ()
        features, rms_dbfs = fingerprint_pcm16(pcm, sample_rate)
        if rms_dbfs < -48.0:
            return ()
        matches: list[ConfirmedEvent] = []
        for enrolled in prototypes:
            reference_prototypes = enrolled.prototypes or (enrolled.prototype,)
            similarity = max(cosine_similarity(features, prototype) for prototype in reference_prototypes)
            if similarity < enrolled.similarity_threshold:
                continue
            matches.append(
                ConfirmedEvent(
                    event=enrolled.event,
                    confidence=round(similarity, 4),
                    source_label=f"enrolled: {enrolled.label}",
                    category="attention",
                    pattern="long_pulse",
                    requires_ack=False,
                )
            )
        return tuple(sorted(matches, key=lambda event: event.confidence, reverse=True)[:3])


def fingerprint_pcm16(pcm: bytes, sample_rate: int) -> tuple[tuple[float, ...], float]:
    if sample_rate != SAMPLE_RATE:
        raise ValueError("Custom sound matcher requires 16 kHz audio")
    if len(pcm) < 2 or len(pcm) % 2:
        raise ValueError("PCM16 payload must contain complete samples")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768.0
    rms_dbfs = 20.0 * math.log10(max(rms, 1e-9))
    amplitudes = tuple(_goertzel_amplitude(samples, frequency) for frequency in FREQUENCIES)
    norm = math.sqrt(sum(value * value for value in amplitudes)) or 1e-12
    return tuple(value / norm for value in amplitudes), rms_dbfs


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(FREQUENCIES) or len(right) != len(FREQUENCIES):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return max(0.0, min(1.0, dot / max(left_norm * right_norm, 1e-12)))


def _goertzel_amplitude(samples: array, frequency: int) -> float:
    coefficient = 2.0 * math.cos(2.0 * math.pi * frequency / SAMPLE_RATE)
    previous = 0.0
    previous_previous = 0.0
    for sample in samples:
        current = sample + coefficient * previous - previous_previous
        previous_previous = previous
        previous = current
    power = previous_previous**2 + previous**2 - coefficient * previous * previous_previous
    return 2.0 * math.sqrt(max(0.0, power)) / len(samples)
