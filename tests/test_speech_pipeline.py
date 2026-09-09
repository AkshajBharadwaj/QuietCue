from __future__ import annotations

import math
import struct
import unittest
from concurrent.futures import Executor, Future

from backend.inference.speech import (
    BufferedSpeechRecognizer,
    Transcript,
    evaluate_phrase_match,
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
    def __init__(self, text: str, confidence: float = 0.91) -> None:
        self.text = text
        self.confidence = confidence
        self.calls = 0
        self.prompt = ""
        self.hotwords: list[str] = []
        self.received: list[bytes] = []

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
        self.received.append(pcm)
        return Transcript(self.text, self.confidence)


def _tone(duration_ms: int, amplitude: int = 8_000, frequency_hz: float = 220.0) -> bytes:
    """Loud enough to count as speech-like activity in the hub's own energy gate."""
    count = 16_000 * duration_ms // 1_000
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * frequency_hz * index / 16_000)))
        for index in range(count)
    )


def _silence(duration_ms: int) -> bytes:
    return b"\x00\x00" * (16_000 * duration_ms // 1_000)


class PhraseMatchingTest(unittest.TestCase):
    def test_phrase_matching_is_case_and_punctuation_insensitive(self) -> None:
        match = find_phrase_match(Transcript("Hey, AKSHAJ! Please look over here.", 0.42), ["Akshaj"])

        self.assertIsNotNone(match)
        self.assertEqual(match.phrase, "Akshaj")
        self.assertEqual(match.confidence, 1.0, "the event confidence is the match score, not ASR confidence")
        self.assertEqual(match.asr_confidence, 0.42)

    def test_name_matching_tolerates_common_transcription_errors(self) -> None:
        for transcription in ("Hey Roan", "Hey Rowan", "Hey Ro han", "Ruhan", "Rohaan", "Ronan"):
            with self.subTest(transcription=transcription):
                match = find_phrase_match(Transcript(transcription), ["Rohan"])

                self.assertIsNotNone(match)
                self.assertEqual(match.phrase, "Rohan")
                self.assertGreaterEqual(match.confidence, 0.6)

    def test_phonetic_substitution_matches_but_unrelated_name_does_not(self) -> None:
        for transcription, phrase in (("Please call Stefan", "Stephan"), ("Maia is here", "Maya"), ("Ayesha", "Aisha")):
            with self.subTest(transcription=transcription):
                match = find_phrase_match(Transcript(transcription), [phrase])
                self.assertIsNotNone(match)
                self.assertEqual(match.confidence, 0.9)
        for transcription in ("Please call Maya", "Ryan", "Ron", "Robin", "rowing", "open"):
            with self.subTest(transcription=transcription):
                self.assertIsNone(find_phrase_match(Transcript(transcription), ["Rohan"]))

    def test_sensitivity_gates_the_match_score_only(self) -> None:
        match = find_phrase_match(Transcript("Rowan", 0.5), ["Rohan"], sensitivity=0.75)

        self.assertIsNotNone(match)
        self.assertEqual(match.confidence, 0.9)
        self.assertIsNone(find_phrase_match(Transcript("Roan"), ["Rohan"], sensitivity=0.85))

    def test_low_asr_confidence_is_only_a_floor_against_hallucination(self) -> None:
        exact_but_noisy = find_phrase_match(Transcript("Rohan", 0.45), ["Rohan"])
        self.assertIsNotNone(exact_but_noisy)
        self.assertEqual(exact_but_noisy.confidence, 1.0)

        evaluation = evaluate_phrase_match(Transcript("Rohan", 0.1), ["Rohan"])
        self.assertIsNone(evaluation.match)
        self.assertEqual(evaluation.reject_reason, "asr_confidence_floor")
        self.assertEqual(evaluation.best_score, 1.0)

    def test_evaluation_reports_rejection_reason_without_transcript(self) -> None:
        evaluation = evaluate_phrase_match(Transcript("Ryan come here"), ["Rohan"])

        self.assertIsNone(evaluation.match)
        self.assertEqual(evaluation.reject_reason, "below_sensitivity")
        self.assertEqual(evaluation.best_phrase, "Rohan")
        self.assertFalse(hasattr(evaluation, "transcript"))


class BufferedRecognizerTest(unittest.TestCase):
    def test_buffered_recognizer_returns_phrase_from_background_job(self) -> None:
        transcriber = _FixedTranscriber("Akshaj, the alarm is sounding")
        recognizer = BufferedSpeechRecognizer(
            transcriber,
            min_audio_ms=1_000,
            executor=_InlineExecutor(),
        )
        one_second_pcm = b"\x00\x01" * 16_000

        first, pending = recognizer.update(one_second_pcm, 16_000, True, ["Akshaj"])
        completed, still_pending = recognizer.update(_silence(500), 16_000, False, ["Akshaj"])

        self.assertIsNone(first)
        self.assertTrue(pending)
        self.assertFalse(still_pending)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.phrase_match.phrase, "Akshaj")
        self.assertEqual(completed.diagnostics.reject_reason, None)
        self.assertTrue(completed.diagnostics.matched)
        self.assertEqual(transcriber.calls, 1)

    def test_audio_before_the_voice_gate_opens_is_kept_as_pre_roll(self) -> None:
        """A quiet 'Ro-' the gate missed must still reach Whisper with the '-han'."""
        transcriber = _FixedTranscriber("Rohan")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())
        quiet_speech = _tone(1_000, amplitude=300)  # below the phone's -42 dBFS gate

        recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        recognizer.update(quiet_speech, 16_000, False, ["Rohan"])
        recognizer.update(_tone(1_000), 16_000, True, ["Rohan"])
        _, pending = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        completed, _ = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

        self.assertTrue(pending)
        self.assertIsNotNone(completed)
        self.assertEqual(transcriber.calls, 1)
        submitted_ms = len(transcriber.received[0]) // 2 * 1_000 // 16_000
        self.assertGreaterEqual(submitted_ms, 1_800, "window must include pre-roll overlap, not just the gated chunk")

    def test_hub_energy_gate_submits_speech_the_edge_gate_missed(self) -> None:
        transcriber = _FixedTranscriber("Rohan")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())

        for _ in range(3):
            recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        recognizer.update(_tone(1_000), 16_000, False, ["Rohan"])
        _, pending = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        completed, _ = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

        self.assertTrue(pending)
        self.assertEqual(transcriber.calls, 1)
        self.assertIsNotNone(completed)

    def test_long_utterance_is_split_at_the_maximum_window(self) -> None:
        transcriber = _FixedTranscriber("Rohan")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor(), max_audio_ms=3_000)

        for _ in range(6):
            recognizer.update(_tone(1_000), 16_000, True, ["Rohan"])

        self.assertGreaterEqual(transcriber.calls, 2)
        for window in transcriber.received:
            self.assertLessEqual(len(window) // 2 // 16, 3_000)

    def test_silence_never_reaches_the_transcriber(self) -> None:
        transcriber = _FixedTranscriber("nothing")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())

        for _ in range(10):
            recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

        self.assertEqual(transcriber.calls, 0)

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
            "Akshaj. Hey Akshaj.",
            ["Akshaj", "Maya"],
        )
        recognizer.update(pcm[:16_000], 16_000, False, ["Akshaj"])

        self.assertEqual(transcriber.prompt, "Akshaj. Hey Akshaj.")
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

    def test_pipeline_emits_name_event_and_privacy_safe_diagnostics(self) -> None:
        from backend.inference.demo_classifier import DemoToneSoundClassifier
        from backend.inference.pipeline import HubInferencePipeline

        transcriber = _FixedTranscriber("Hey Rowan", confidence=0.55)
        pipeline = HubInferencePipeline(DemoToneSoundClassifier(), transcriber)
        pipeline.speech_recognizer._executor = _InlineExecutor()
        pipeline.speech_recognizer._owns_executor = False

        pipeline.process_pcm16(_tone(1_000), 16_000, {"voice_activity": True}, ["Rohan"])
        result = pipeline.process_pcm16(_silence(1_000), 16_000, {"voice_activity": False}, ["Rohan"])

        names = [event for event in result.events if event.event == "name_called"]
        self.assertEqual(len(names), 1)
        self.assertEqual(names[0].confidence, 0.9, "confidence is the match score; ASR confidence 0.55 is not multiplied in")
        wire = result.to_wire()
        self.assertIsNone(wire["transcript"])
        self.assertEqual(wire["speech_diagnostics"]["match_score"], 0.9)
        self.assertEqual(wire["speech_diagnostics"]["asr_confidence"], 0.55)
        self.assertTrue(wire["speech_diagnostics"]["matched"])
        self.assertNotIn("Rowan", str(wire))


if __name__ == "__main__":
    unittest.main()
