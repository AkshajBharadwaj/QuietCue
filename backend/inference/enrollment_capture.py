"""One-tap custom-sound enrollment from the live Uno Q microphone stream."""

from __future__ import annotations

import math
import sys
import uuid
from array import array
from typing import Any

from backend.inference.custom_sound_matcher import (
    SAMPLE_RATE,
    SPEECH_REJECTION_CONFIDENCE,
    cosine_similarity,
    fingerprint_pcm16,
)


MIN_DURATION_MS = 4_000
MAX_DURATION_MS = 15_000
DEFAULT_DURATION_MS = 10_000
FRAME_MS = 25
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1_000
MIN_EVENT_FRAMES = 5
MAX_EVENT_FRAMES = 100
MAX_GAP_FRAMES = 5
EVENT_PADDING_FRAMES = 2
MAX_EVENTS = 12
BACKGROUND_FRAMES = 20
MIN_REPEAT_SIMILARITY = 0.86
MIN_CONSISTENT_REPEATS = 3


class EnrollmentCaptureController:
    """Collect a bounded live session and retain fingerprints, never raw audio."""

    def __init__(self) -> None:
        self._state = "idle"
        self._session_id = ""
        self._target_samples = 0
        self._samples = array("h")
        self._speech_ranges: list[tuple[int, int]] = []
        self._result: dict[str, Any] = {}

    def start(self, duration_ms: int = DEFAULT_DURATION_MS) -> dict[str, Any]:
        if not MIN_DURATION_MS <= duration_ms <= MAX_DURATION_MS:
            raise ValueError(
                f"Enrollment duration must be between {MIN_DURATION_MS} and {MAX_DURATION_MS} ms"
            )
        self._state = "recording"
        self._session_id = uuid.uuid4().hex
        self._target_samples = SAMPLE_RATE * duration_ms // 1_000
        self._samples = array("h")
        self._speech_ranges = []
        self._result = {}
        return self.status()

    def cancel(self) -> dict[str, Any]:
        self._state = "idle"
        self._samples = array("h")
        self._speech_ranges = []
        self._result = {}
        return self.status()

    def observe(self, pcm: bytes, sample_rate: int, *, speech_confidence: float = 0.0) -> None:
        if self._state != "recording":
            return
        if sample_rate != SAMPLE_RATE:
            self._fail("Enrollment requires 16 kHz audio from the Uno Q")
            return
        if not pcm or len(pcm) % 2:
            self._fail("Enrollment received malformed PCM audio")
            return

        incoming = array("h")
        incoming.frombytes(pcm)
        if sys.byteorder != "little":
            incoming.byteswap()
        remaining = self._target_samples - len(self._samples)
        if remaining <= 0:
            return
        accepted = incoming[:remaining]
        start = len(self._samples)
        self._samples.extend(accepted)
        if speech_confidence >= SPEECH_REJECTION_CONFIDENCE:
            self._speech_ranges.append((start, len(self._samples)))
        if len(self._samples) >= self._target_samples:
            self._finish()

    def status(self) -> dict[str, Any]:
        captured_samples = len(self._samples) if self._state == "recording" else self._target_samples
        remaining_samples = max(0, self._target_samples - captured_samples)
        document: dict[str, Any] = {
            "state": self._state,
            "session_id": self._session_id,
            "remaining_ms": round(remaining_samples * 1_000 / SAMPLE_RATE),
        }
        document.update(self._result)
        return document

    def _finish(self) -> None:
        try:
            positives, background = extract_enrollment_fingerprints(
                self._samples,
                blocked_ranges=self._speech_ranges,
            )
            rejected_samples = sum(end - start for start, end in self._speech_ranges)
            self._result = {
                "positives": positives,
                "background": background,
                "speech_rejected_ms": round(rejected_samples * 1_000 / SAMPLE_RATE),
            }
            self._state = "complete"
        except ValueError as error:
            self._fail(str(error))
        finally:
            self._samples = array("h")
            self._speech_ranges = []

    def _fail(self, message: str) -> None:
        self._state = "error"
        self._result = {"error": message}
        self._samples = array("h")
        self._speech_ranges = []


def extract_enrollment_fingerprints(
    samples: array,
    *,
    blocked_ranges: list[tuple[int, int]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(samples) < SAMPLE_RATE:
        raise ValueError("Enrollment session is too short")
    blocked_ranges = blocked_ranges or []
    frame_count = len(samples) // FRAME_SAMPLES
    levels = [
        _rms_dbfs(samples[index * FRAME_SAMPLES : (index + 1) * FRAME_SAMPLES])
        for index in range(frame_count)
    ]
    blocked = [
        any(
            start < (index + 1) * FRAME_SAMPLES and end > index * FRAME_SAMPLES
            for start, end in blocked_ranges
        )
        for index in range(frame_count)
    ]
    usable_levels = [level for index, level in enumerate(levels) if not blocked[index]]
    if not usable_levels:
        raise ValueError("The session contained only speech; try again without talking")
    sorted_levels = sorted(usable_levels)
    noise_floor = sorted_levels[max(0, len(sorted_levels) // 5 - 1)]
    activity_threshold = max(-45.0, noise_floor + 8.0)
    active = [not blocked[index] and level >= activity_threshold for index, level in enumerate(levels)]
    segments = _active_segments(active)

    positives: list[dict[str, Any]] = []
    for start_frame, end_frame in segments[:MAX_EVENTS]:
        start_frame = max(0, start_frame - EVENT_PADDING_FRAMES)
        end_frame = min(frame_count, end_frame + EVENT_PADDING_FRAMES)
        if end_frame - start_frame > MAX_EVENT_FRAMES:
            peak = max(range(start_frame, end_frame), key=levels.__getitem__)
            start_frame = max(start_frame, peak - MAX_EVENT_FRAMES // 2)
            end_frame = min(end_frame, start_frame + MAX_EVENT_FRAMES)
            start_frame = max(0, end_frame - MAX_EVENT_FRAMES)
        event_samples = samples[start_frame * FRAME_SAMPLES : end_frame * FRAME_SAMPLES]
        features, rms_dbfs = fingerprint_pcm16(_pcm_bytes(event_samples), SAMPLE_RATE)
        positives.append(
            {
                "features": [round(value, 7) for value in features],
                "rms_dbfs": round(rms_dbfs, 2),
            }
        )

    positives = _most_consistent_repeats(positives)

    background_start = _quietest_background_start(levels, blocked)
    background_samples = samples[
        background_start * FRAME_SAMPLES : (background_start + BACKGROUND_FRAMES) * FRAME_SAMPLES
    ]
    background_features, background_rms = fingerprint_pcm16(
        _pcm_bytes(background_samples), SAMPLE_RATE
    )
    background = {
        "features": [round(value, 7) for value in background_features],
        "rms_dbfs": round(background_rms, 2),
        "noise_floor_dbfs": round(noise_floor, 2),
    }
    return positives, background


def _most_consistent_repeats(positives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the largest coherent family and discard incidental room sounds."""
    if len(positives) < MIN_CONSISTENT_REPEATS:
        raise ValueError(
            "Play the sound at least three times with a short quiet pause between repeats"
        )

    feature_vectors = [tuple(float(value) for value in item["features"]) for item in positives]
    candidates: list[tuple[int, float, list[int]]] = []
    for seed_index, seed in enumerate(feature_vectors):
        group = [
            index
            for index, candidate in enumerate(feature_vectors)
            if cosine_similarity(seed, candidate) >= MIN_REPEAT_SIMILARITY
        ]
        cohesion = sum(
            cosine_similarity(feature_vectors[left], feature_vectors[right])
            for position, left in enumerate(group)
            for right in group[position + 1 :]
        )
        pair_count = len(group) * (len(group) - 1) // 2
        candidates.append((len(group), cohesion / max(pair_count, 1), group))

    _, _, best_group = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    if len(best_group) < MIN_CONSISTENT_REPEATS:
        raise ValueError(
            "The captured sounds were too different. Play the same sound at least three times"
        )
    return [positive for index, positive in enumerate(positives) if index in set(best_group)]


def _active_segments(active: list[bool]) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    start: int | None = None
    last_active = -1
    for index, is_active in enumerate(active):
        if is_active:
            if start is None:
                start = index
            last_active = index
        elif start is not None and index - last_active > MAX_GAP_FRAMES:
            if last_active - start + 1 >= MIN_EVENT_FRAMES:
                segments.append((start, last_active + 1))
            start = None
    if start is not None and last_active - start + 1 >= MIN_EVENT_FRAMES:
        segments.append((start, last_active + 1))
    return segments


def _quietest_background_start(levels: list[float], blocked: list[bool]) -> int:
    if len(levels) <= BACKGROUND_FRAMES:
        return 0
    candidates: list[tuple[float, int]] = []
    for start in range(len(levels) - BACKGROUND_FRAMES + 1):
        if any(blocked[start : start + BACKGROUND_FRAMES]):
            continue
        candidates.append((sum(levels[start : start + BACKGROUND_FRAMES]), start))
    if not candidates:
        return 0
    return min(candidates)[1]


def _rms_dbfs(samples: array) -> float:
    if not samples:
        return -180.0
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768.0
    return 20.0 * math.log10(max(rms, 1e-9))


def _pcm_bytes(samples: array) -> bytes:
    copied = array("h", samples)
    if sys.byteorder != "little":
        copied.byteswap()
    return copied.tobytes()
