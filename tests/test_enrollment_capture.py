from __future__ import annotations

import math
import struct
import unittest

from backend.inference.enrollment_capture import EnrollmentCaptureController


class EnrollmentCaptureControllerTest(unittest.TestCase):
    def test_guided_session_extracts_repeated_events_and_background(self) -> None:
        controller = EnrollmentCaptureController()
        controller.start(4_000)

        pcm = _session_pcm16(event_starts=(0.7, 1.7, 2.7))
        controller.observe(pcm, 16_000)
        status = controller.status()

        self.assertEqual("complete", status["state"])
        self.assertEqual(3, len(status["positives"]))
        self.assertEqual(8, len(status["positives"][0]["features"]))
        self.assertLess(status["background"]["rms_dbfs"], -45.0)

    def test_speech_dominated_audio_is_not_enrolled(self) -> None:
        controller = EnrollmentCaptureController()
        controller.start(4_000)

        controller.observe(
            _session_pcm16(event_starts=(0.7, 1.7, 2.7)),
            16_000,
            speech_confidence=0.2,
        )
        status = controller.status()

        self.assertEqual("error", status["state"])
        self.assertIn("only speech", status["error"])

    def test_incidental_different_sound_is_removed_from_repeats(self) -> None:
        controller = EnrollmentCaptureController()
        controller.start(4_000)

        controller.observe(
            _session_pcm16(
                event_starts=(0.5, 1.3, 2.1, 2.9),
                frequencies=(1_000, 1_000, 3_000, 1_000),
            ),
            16_000,
        )

        status = controller.status()
        self.assertEqual("complete", status["state"])
        self.assertEqual(3, len(status["positives"]))

    def test_unrelated_repeats_are_rejected(self) -> None:
        controller = EnrollmentCaptureController()
        controller.start(4_000)

        controller.observe(
            _session_pcm16(
                event_starts=(0.7, 1.7, 2.7),
                frequencies=(250, 1_000, 3_000),
            ),
            16_000,
        )

        status = controller.status()
        self.assertEqual("error", status["state"])
        self.assertIn("same sound", status["error"])

    def test_duration_is_bounded(self) -> None:
        controller = EnrollmentCaptureController()
        with self.assertRaisesRegex(ValueError, "between"):
            controller.start(2_000)


def _session_pcm16(
    event_starts: tuple[float, ...],
    seconds: float = 4.0,
    frequencies: tuple[int, ...] | None = None,
) -> bytes:
    sample_rate = 16_000
    samples = [40] * round(sample_rate * seconds)
    event_frequencies = frequencies or (1_000,) * len(event_starts)
    for start_seconds, frequency in zip(event_starts, event_frequencies, strict=True):
        start = round(start_seconds * sample_rate)
        duration = round(0.3 * sample_rate)
        for offset in range(duration):
            samples[start + offset] = round(
                12_000 * math.sin(2 * math.pi * frequency * offset / sample_rate)
            )
    return b"".join(struct.pack("<h", sample) for sample in samples)
