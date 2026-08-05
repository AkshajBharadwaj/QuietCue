"""Cheap first-pass audio analysis for the Uno Q Linux side.

This analyzer deliberately emits candidates, never safety decisions. A connected
hub confirms the exact environmental event and optionally transcribes speech.
"""

from __future__ import annotations

import math
import sys
from array import array
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EdgeCandidate:
    kind: str
    confidence: float


@dataclass(frozen=True)
class EdgeAnalysis:
    rms_dbfs: float
    peak_dbfs: float
    voice_activity: bool
    voice_probability: float
    dominant_tone_hz: int | None
    tone_margin_db: float | None
    candidates: tuple[EdgeCandidate, ...]

    def to_wire(self) -> dict[str, object]:
        result = asdict(self)
        result["candidates"] = [asdict(candidate) for candidate in self.candidates]
        return result


class EdgeAudioAnalyzer:
    """Dependency-free VAD, loudness, and tonal-alarm candidate generator."""

    _TONE_FREQUENCIES = (600, 800, 1000, 1250, 1600, 2000, 2500, 3150)

    def __init__(self, sample_rate: int = 16_000) -> None:
        if sample_rate < 8_000:
            raise ValueError("sample_rate must be at least 8000 Hz")
        self.sample_rate = sample_rate

    def analyze_pcm16(self, pcm: bytes) -> EdgeAnalysis:
        """Analyze little-endian mono PCM16 audio."""
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM16 payload must contain complete samples")
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        return self.analyze_samples(samples)

    def analyze_samples(self, samples: array) -> EdgeAnalysis:
        if not samples:
            raise ValueError("Cannot analyze empty audio")

        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768.0
        peak = max(abs(sample) for sample in samples) / 32768.0
        rms_dbfs = _to_dbfs(rms)
        peak_dbfs = _to_dbfs(peak)

        dominant_frequency, tone_dbfs = self._dominant_tone(samples)
        tone_margin = tone_dbfs - rms_dbfs if dominant_frequency is not None else None
        voice_probability = self._voice_probability(samples, rms_dbfs)
        voice_activity = (
            voice_probability >= 0.30
            and rms_dbfs >= -42.0
            and (tone_margin is None or tone_margin < 0.5)
        )

        candidates: list[EdgeCandidate] = []
        if voice_activity:
            candidates.append(
                EdgeCandidate(
                    kind="speech_candidate",
                    confidence=_clamp(0.45 + voice_probability * 0.45),
                )
            )
        if dominant_frequency is not None and tone_margin is not None and tone_margin >= -1.0:
            candidates.append(
                EdgeCandidate(
                    kind="tonal_alarm_candidate",
                    confidence=_clamp(0.50 + (tone_margin + 1.0) / 8.0),
                )
            )
        if rms_dbfs >= -25.0 or peak_dbfs >= -10.0:
            loudness_confidence = max((rms_dbfs + 35.0) / 25.0, (peak_dbfs + 20.0) / 20.0)
            candidates.append(
                EdgeCandidate(kind="loud_sound_candidate", confidence=_clamp(loudness_confidence))
            )

        return EdgeAnalysis(
            rms_dbfs=round(rms_dbfs, 2),
            peak_dbfs=round(peak_dbfs, 2),
            voice_activity=voice_activity,
            voice_probability=round(voice_probability, 3),
            dominant_tone_hz=dominant_frequency,
            tone_margin_db=round(tone_margin, 2) if tone_margin is not None else None,
            candidates=tuple(candidates),
        )

    def _voice_probability(self, samples: array, overall_dbfs: float) -> float:
        frame_size = max(1, self.sample_rate // 50)  # 20 ms
        frame_count = 0
        speech_like_frames = 0
        minimum_frame_dbfs = max(-45.0, overall_dbfs - 15.0)
        for start in range(0, len(samples) - frame_size + 1, frame_size):
            frame = samples[start : start + frame_size]
            frame_count += 1
            frame_rms = math.sqrt(sum(sample * sample for sample in frame) / len(frame)) / 32768.0
            frame_dbfs = _to_dbfs(frame_rms)
            crossings = sum(
                1 for left, right in zip(frame, frame[1:]) if (left < 0 <= right) or (left >= 0 > right)
            )
            crossing_rate = crossings / max(1, len(frame) - 1)
            if frame_dbfs >= minimum_frame_dbfs and 0.015 <= crossing_rate <= 0.35:
                speech_like_frames += 1
        return speech_like_frames / frame_count if frame_count else 0.0

    def _dominant_tone(self, samples: array) -> tuple[int | None, float]:
        best_frequency: int | None = None
        best_amplitude = 0.0
        for frequency in self._TONE_FREQUENCIES:
            amplitude = _goertzel_amplitude(samples, self.sample_rate, frequency)
            if amplitude > best_amplitude:
                best_frequency = frequency
                best_amplitude = amplitude
        tone_dbfs = _to_dbfs(best_amplitude / 32768.0)
        if tone_dbfs < -50.0:
            return None, tone_dbfs
        return best_frequency, tone_dbfs


def _goertzel_amplitude(samples: array, sample_rate: int, target_frequency: int) -> float:
    coefficient = 2.0 * math.cos(2.0 * math.pi * target_frequency / sample_rate)
    previous = 0.0
    previous_previous = 0.0
    for sample in samples:
        current = sample + coefficient * previous - previous_previous
        previous_previous = previous
        previous = current
    power = previous_previous**2 + previous**2 - coefficient * previous * previous_previous
    return 2.0 * math.sqrt(max(0.0, power)) / len(samples)


def _to_dbfs(amplitude: float) -> float:
    return 20.0 * math.log10(max(amplitude, 1e-9))


def _clamp(value: float) -> float:
    return round(max(0.0, min(0.99, value)), 3)
