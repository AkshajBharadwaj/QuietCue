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
        self.prompt = ""
        self.hotwords: list[str] = []

    def transcribe_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        prompt: str = "",
        hotwords: list[str] | None = None,
    ) -> Transcript:
        self.calls += 1
        self.prompt = prompt
        self.hotwords = hotwords or []
        return Transcript(self.text, 0.91)


class SpeechPipelineTest(unittest.TestCase):
    def test_phrase_matching_is_case_and_punctuation_insensitive(self) -> None:
        match = find_phrase_match(Transcript("Hey, AKSHAJ! Please look over here.", 0.42), ["Akshaj"])

        self.assertIsNotNone(match)
        self.assertEqual(match.phrase, "Akshaj")
        self.assertEqual(match.confidence, 0.42)

    def test_name_matching_tolerates_common_transcription_errors(self) -> None:
        for transcription in ("Hey Roan", "Hey Rowan", "Hey Ro han"):
            with self.subTest(transcription=transcription):
                match = find_phrase_match(Transcript(transcription), ["Rohan"])

                self.assertIsNotNone(match)
                self.assertEqual(match.phrase, "Rohan")
                self.assertGreaterEqual(match.confidence, 0.6)

    def test_phonetic_substitution_matches_but_unrelated_name_does_not(self) -> None:
        match = find_phrase_match(Transcript("Please call Stefan"), ["Stephan"])

        self.assertIsNotNone(match)
        self.assertEqual(match.confidence, 0.9)
        self.assertIsNone(find_phrase_match(Transcript("Please call Maya"), ["Rohan"]))

    def test_sensitivity_is_applied_before_asr_confidence_weighting(self) -> None:
        match = find_phrase_match(Transcript("Rowan", 0.5), ["Rohan"], sensitivity=0.75)

        self.assertIsNotNone(match)
        self.assertEqual(match.confidence, 0.4)
        self.assertIsNone(find_phrase_match(Transcript("Rowan"), ["Rohan"], sensitivity=0.85))

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

    def test_context_prompt_and_hotwords_reach_transcriber(self) -> None:
        transcriber = _FixedTranscriber("Hey Akshaj")
        recognizer = BufferedSpeechRecognizer(
            transcriber,
            min_audio_ms=1_000,
            executor=_InlineExecutor(),
        )
        pcm = b"\x00\x01" * 16_000

        recognizer.update(
            pcm,
            16_000,
            True,
            ["Akshaj"],
            "The user's name is Akshaj.",
            ["Akshaj", "Maya"],
        )
        recognizer.update(pcm[:16_000], 16_000, False, ["Akshaj"])

        self.assertEqual(transcriber.prompt, "The user's name is Akshaj.")
        self.assertEqual(transcriber.hotwords, ["Akshaj", "Maya"])

    def test_transcriber_failure_is_metadata_not_a_pipeline_exception(self) -> None:
        class FailingTranscriber:
            def transcribe_pcm16(
                self,
                pcm: bytes,
                sample_rate: int,
                prompt: str = "",
                hotwords: list[str] | None = None,
            ) -> Transcript:
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

    def test_disabled_pipeline_never_invokes_transcriber(self) -> None:
        from backend.inference.demo_classifier import DemoToneSoundClassifier
        from backend.inference.pipeline import HubInferencePipeline

        transcriber = _FixedTranscriber("Hey Alex")
        pipeline = HubInferencePipeline(DemoToneSoundClassifier(), transcriber)
        pcm = b"\x00\x01" * 16_000

        first = pipeline.process_pcm16(
            pcm,
            16_000,
            {"voice_activity": True},
            ["Alex"],
            speech_enabled=False,
        )

        self.assertFalse(first.speech_pending)
        self.assertEqual(transcriber.calls, 0)


if __name__ == "__main__":
    unittest.main()
