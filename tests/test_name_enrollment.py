from __future__ import annotations

import math
import struct
import unittest

from backend.inference.name_enrollment import (
    NameEnrollmentController,
    analyze_name_sample,
)
from backend.inference.speech import Transcript


class _ScriptedTranscriber:
    """Returns the prompted transcript first, then the unprompted one."""

    def __init__(self, prompted: str | None, unprompted: str | None) -> None:
        self.outputs = [prompted, unprompted]
        self.prompts: list[str] = []

    def transcribe_pcm16(self, pcm, sample_rate, prompt="", hotwords=None):
        self.prompts.append(prompt)
        text = self.outputs.pop(0)
        return Transcript(text, 0.8) if text else None


def _speech_like(duration_ms: int) -> bytes:
    count = 16_000 * duration_ms // 1_000
    return b"".join(
        struct.pack("<h", int(6_000 * math.sin(2 * math.pi * 180 * index / 16_000))) for index in range(count)
    )


class NameEnrollmentAnalysisTest(unittest.TestCase):
    def test_whispers_own_misspelling_becomes_a_suggested_spelling(self) -> None:
        transcriber = _ScriptedTranscriber("Hey Rowan, come here.", "Hey Rowen.")

        result = analyze_name_sample(transcriber, _speech_like(3_000), 16_000, "Rohan", (), "Rohan. Hey Rohan.", ["Rohan"])

        self.assertEqual(result["heard"], ["Rowan", "Rowen"])
        self.assertFalse(result["recognized"])
        self.assertEqual(transcriber.prompts, ["Rohan. Hey Rohan.", ""])

    def test_correct_spelling_is_reported_as_recognized_without_duplicates(self) -> None:
        transcriber = _ScriptedTranscriber("Rohan.", "Rowan.")

        result = analyze_name_sample(transcriber, _speech_like(3_000), 16_000, "Rohan", ("Rowan",), "", [])

        self.assertTrue(result["recognized"])
        self.assertEqual(result["heard"], [], "known spellings are not suggested again")

    def test_unrelated_speech_is_an_error_not_a_spelling(self) -> None:
        transcriber = _ScriptedTranscriber("The weather is nice today.", "The weather is nice today.")

        result = analyze_name_sample(transcriber, _speech_like(3_000), 16_000, "Rohan", (), "", [])

        self.assertEqual(result["heard"], [])
        self.assertIn("error", result)
        self.assertNotIn("weather", str(result), "transcripts never leave the analysis")

    def test_short_utterance_far_from_the_name_is_still_whispers_spelling(self) -> None:
        transcriber = _ScriptedTranscriber("Hey, Oxides.", "Ox eyes")

        result = analyze_name_sample(transcriber, _speech_like(3_000), 16_000, "Akshaj", (), "", [])

        self.assertEqual(result["heard"], ["Oxides", "Ox eyes"])
        self.assertFalse(result["recognized"])

    def test_silence_is_rejected_before_transcription(self) -> None:
        transcriber = _ScriptedTranscriber("Rohan", "Rohan")

        result = analyze_name_sample(transcriber, b"\x00\x00" * 48_000, 16_000, "Rohan", (), "", [])

        self.assertIn("error", result)
        self.assertEqual(transcriber.prompts, [])


class NameEnrollmentControllerTest(unittest.TestCase):
    def test_controller_collects_exactly_the_requested_window(self) -> None:
        controller = NameEnrollmentController()
        status = controller.start("Rohan", ["Rowan"], duration_ms=2_000)
        self.assertEqual(status["state"], "recording")
        self.assertEqual(status["remaining_ms"], 2_000)

        self.assertIsNone(controller.observe(b"\x00\x01" * 16_000, 16_000))
        self.assertEqual(controller.status()["remaining_ms"], 1_000)
        captured = controller.observe(b"\x00\x01" * 24_000, 16_000)

        self.assertEqual(len(captured), 2_000 * 16 * 2)
        self.assertEqual(controller.status()["state"], "processing")
        controller.complete({"heard": ["Rowan"], "recognized": False})
        self.assertEqual(controller.status()["state"], "complete")
        self.assertEqual(controller.status()["heard"], ["Rowan"])
        self.assertIsNone(controller.observe(b"\x00\x01" * 16_000, 16_000), "audio after completion is ignored")

    def test_controller_validates_inputs(self) -> None:
        controller = NameEnrollmentController()
        with self.assertRaises(ValueError):
            controller.start("", [])
        with self.assertRaises(ValueError):
            controller.start("Rohan", [], duration_ms=500)
        controller.start("Rohan", [])
        controller.observe(b"\x00\x01" * 100, 44_100)
        self.assertEqual(controller.status()["state"], "error")
        self.assertEqual(controller.cancel()["state"], "idle")


if __name__ == "__main__":
    unittest.main()
