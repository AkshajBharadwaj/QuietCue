from __future__ import annotations

import unittest
from concurrent.futures import Executor, Future

from backend.inference.speech import (
    BufferedSpeechRecognizer,
    Transcript,
    find_phrase_match,
)


class _InlineExecutor(Executor):
    def submit(self, fn, /, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:
            future.set_exception(exc)
        return future


class _FixedTranscriber:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int) -> Transcript:
        self.calls += 1
        return Transcript(self.text, 0.91)


class SpeechPipelineTest(unittest.TestCase):
    def test_phrase_matching_is_case_and_punctuation_insensitive(self) -> None:
        match = find_phrase_match(Transcript("Hey, AKSHAJ! Please look over here.", 0.42), ["Akshaj"])

        self.assertIsNotNone(match)
        self.assertEqual(match.phrase, "Akshaj")
        self.assertEqual(match.confidence, 0.75)

    def test_buffered_recognizer_returns_phrase_from_background_job(self) -> None:
        transcriber = _FixedTranscriber("Akshaj, the alarm is sounding")
        recognizer = BufferedSpeechRecognizer(
            transcriber,
            min_audio_ms=1_000,
            executor=_InlineExecutor(),
        )
        one_second_pcm = b"\x00\x01" * 16_000

        first, pending = recognizer.update(one_second_pcm, 16_000, True, ["Akshaj"])
        completed, still_pending = recognizer.update(b"\x00\x00" * 8_000, 16_000, False, ["Akshaj"])

        self.assertIsNone(first)
        self.assertTrue(pending)
        self.assertFalse(still_pending)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.phrase_match.phrase, "Akshaj")
        self.assertEqual(transcriber.calls, 1)

    def test_transcriber_failure_is_metadata_not_a_pipeline_exception(self) -> None:
        class FailingTranscriber:
            def transcribe_pcm16(self, pcm: bytes, sample_rate: int) -> Transcript:
                raise RuntimeError("model unavailable")

        recognizer = BufferedSpeechRecognizer(
            FailingTranscriber(),
            min_audio_ms=1_000,
            executor=_InlineExecutor(),
        )
        pcm = b"\x00\x01" * 16_000

        recognizer.update(pcm, 16_000, True, ["Akshaj"])
        completed, _ = recognizer.update(pcm[:16_000], 16_000, False, ["Akshaj"])

        self.assertEqual(completed.error, "model unavailable")

    def test_reset_discards_completed_result_from_previous_stream(self) -> None:
        recognizer = BufferedSpeechRecognizer(
            _FixedTranscriber("Alex"),
            min_audio_ms=1_000,
            executor=_InlineExecutor(),
        )
        pcm = b"\x00\x01" * 16_000
        recognizer.update(pcm, 16_000, True, ["Alex"])

        recognizer.reset()
        completed, pending = recognizer.update(pcm[:16_000], 16_000, False, ["Alex"])

        self.assertIsNone(completed)
        self.assertFalse(pending)


if __name__ == "__main__":
    unittest.main()
