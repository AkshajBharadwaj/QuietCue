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


class _VadTranscriber(_FixedTranscriber):
    """Fixed transcript plus a Silero-style speech-presence answer."""

    def __init__(self, text: str, speech_ms: int | None) -> None:
        super().__init__(text)
        self.speech_ms = speech_ms

    def detect_speech_ms(self, pcm: bytes, sample_rate: int) -> int | None:
        return self.speech_ms

    def transcribe_pcm16(self, pcm, sample_rate, prompt="", hotwords=None):
        transcript = super().transcribe_pcm16(pcm, sample_rate, prompt, hotwords)
        return Transcript(transcript.text, transcript.confidence, no_speech_probability=0.12)


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
        exact_but_noisy = find_phrase_match(Transcript("Rohan come over here please", 0.45), ["Rohan"])
        self.assertIsNotNone(exact_but_noisy)
        self.assertEqual(exact_but_noisy.confidence, 1.0)

        evaluation = evaluate_phrase_match(Transcript("Rohan come over here please", 0.1), ["Rohan"])
        self.assertIsNone(evaluation.match)
        self.assertEqual(evaluation.reject_reason, "asr_confidence_floor")
        self.assertEqual(evaluation.best_score, 1.0)

    def test_prompt_echo_on_silence_is_rejected(self) -> None:
        """Whisper produced "I'm Rohan Rohan." at 0.38 for a sentence tail plus silence."""
        for text in ("I'm Rohan Rohan.", "Rohan.", "Hey Rohan"):
            with self.subTest(text=text):
                evaluation = evaluate_phrase_match(Transcript(text, 0.38), ["Rohan"])
                self.assertIsNone(evaluation.match)
                self.assertEqual(evaluation.reject_reason, "likely_prompt_echo")
        # The same shapes at the confidence real speech measured still match.
        self.assertIsNotNone(find_phrase_match(Transcript("Rohan.", 0.64), ["Rohan"]))
        # A name inside a longer sentence only needs the low floor.
        self.assertIsNotNone(find_phrase_match(Transcript("Rohan can you come over here", 0.38), ["Rohan"]))

    def test_high_no_speech_probability_rejects_a_name_on_noise(self) -> None:
        # Measured shape of a quiet-room hallucination: confident text, but
        # Whisper itself thinks the window was probably not speech.
        noise = Transcript("Rohan Rohan.", confidence=0.85, no_speech_probability=0.81)
        evaluation = evaluate_phrase_match(noise, ["Rohan"])
        self.assertIsNone(evaluation.match)
        self.assertEqual(evaluation.reject_reason, "no_speech_probability")

        spoken = Transcript("Rohan, dinner is ready.", confidence=0.6, no_speech_probability=0.3)
        self.assertIsNotNone(evaluate_phrase_match(spoken, ["Rohan"]).match)

        unknown = Transcript("Rohan, dinner is ready.", confidence=0.6)
        self.assertIsNotNone(evaluate_phrase_match(unknown, ["Rohan"]).match, "transcribers without the signal still match")

    def test_repetitive_transcript_is_rejected_as_a_hallucination_loop(self) -> None:
        loop = Transcript("Hi Rohan. " * 29, confidence=0.92, no_speech_probability=0.2)
        evaluation = evaluate_phrase_match(loop, ["Rohan"])
        self.assertIsNone(evaluation.match)
        self.assertEqual(evaluation.reject_reason, "hallucination_loop")

        triple = Transcript("Rohan Rohan Rohan.", confidence=0.9, no_speech_probability=0.2)
        self.assertEqual(evaluate_phrase_match(triple, ["Rohan"]).reject_reason, "hallucination_loop")

        double = Transcript("Rohan! Rohan, come here.", confidence=0.9, no_speech_probability=0.1)
        self.assertIsNotNone(evaluate_phrase_match(double, ["Rohan"]).match, "calling twice is normal speech")

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

        self.assertIsNone(first, "speech is still going; nothing to decode yet")
        self.assertFalse(pending)
        self.assertIsNotNone(completed, "a fast decode is delivered in the same chunk cycle it was submitted")
        self.assertFalse(still_pending)
        self.assertEqual(completed.phrase_match.phrase, "Akshaj")
        self.assertEqual(completed.diagnostics.reject_reason, None)
        self.assertTrue(completed.diagnostics.matched)
        self.assertEqual(transcriber.calls, 1)

    def test_slow_decode_is_collected_on_a_later_update(self) -> None:
        import threading
        from concurrent.futures import ThreadPoolExecutor

        release = threading.Event()

        class SlowTranscriber(_FixedTranscriber):
            def transcribe_pcm16(self, pcm, sample_rate, prompt="", hotwords=None):
                release.wait(timeout=5)
                return super().transcribe_pcm16(pcm, sample_rate, prompt, hotwords)

        transcriber = SlowTranscriber("Akshaj")
        executor = ThreadPoolExecutor(max_workers=1)
        recognizer = BufferedSpeechRecognizer(transcriber, result_wait_ms=50, executor=executor)
        try:
            recognizer.update(_tone(1_000), 16_000, True, ["Akshaj"])
            first, pending = recognizer.update(_silence(1_000), 16_000, False, ["Akshaj"])
            self.assertIsNone(first)
            self.assertTrue(pending, "the worker is still busy after the short wait")
            release.set()
            import time

            for _ in range(50):
                completed, _ = recognizer.update(_silence(1_000), 16_000, False, ["Akshaj"])
                if completed is not None:
                    break
                time.sleep(0.02)
            self.assertIsNotNone(completed)
            self.assertEqual(completed.phrase_match.phrase, "Akshaj")
        finally:
            executor.shutdown(wait=False)

    def test_audio_before_the_voice_gate_opens_is_kept_as_pre_roll(self) -> None:
        """A quiet 'Ro-' the gate missed must still reach Whisper with the '-han'."""
        transcriber = _FixedTranscriber("Rohan")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())
        quiet_speech = _tone(1_000, amplitude=300)  # below the phone's -42 dBFS gate

        recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        recognizer.update(quiet_speech, 16_000, False, ["Rohan"])
        recognizer.update(_tone(1_000), 16_000, True, ["Rohan"])
        completed, _ = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

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
        completed, _ = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

        self.assertEqual(transcriber.calls, 1)
        self.assertIsNotNone(completed)

    def test_long_utterance_is_split_at_the_maximum_window(self) -> None:
        transcriber = _FixedTranscriber("Rohan")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())

        for _ in range(6):
            recognizer.update(_tone(1_000), 16_000, True, ["Rohan"])

        self.assertGreaterEqual(transcriber.calls, 2, "continuous talking is windowed, not held until it stops")
        for window in transcriber.received:
            self.assertLessEqual(len(window) // 2 // 16, 2_500)

    def test_name_at_the_start_of_a_long_sentence_is_not_cut_off(self) -> None:
        """Queued audio beyond one window is sent oldest-first, not dropped."""
        transcriber = _FixedTranscriber("Rohan")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())

        for _ in range(3):
            recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        for _ in range(3):
            recognizer.update(_tone(1_000), 16_000, True, ["Rohan"])
        recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

        covered = sum(len(window) for window in transcriber.received) // 2 // 16
        self.assertGreaterEqual(covered, 3_000, "the three seconds of speech must all be transcribed")
        self.assertGreaterEqual(transcriber.calls, 2)

    def test_trailing_silence_is_trimmed_from_the_window(self) -> None:
        transcriber = _FixedTranscriber("Rohan")
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())

        for _ in range(3):
            recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        recognizer.update(_tone(500) + _silence(500), 16_000, True, ["Rohan"])
        recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

        self.assertEqual(transcriber.calls, 1)
        window_ms = len(transcriber.received[0]) // 2 // 16
        self.assertLessEqual(window_ms, 1_800, "the second of pure silence must not be handed to Whisper")
        self.assertGreaterEqual(window_ms, 1_000)

    def test_windows_without_vad_speech_skip_the_decoder(self) -> None:
        transcriber = _VadTranscriber("Rohan", speech_ms=0)
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())

        recognizer.update(_tone(1_000), 16_000, True, ["Rohan"])
        result, _ = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])

        self.assertEqual(transcriber.calls, 0, "no decode when Silero hears no speech")
        self.assertIsNotNone(result)
        self.assertIsNone(result.phrase_match)
        self.assertEqual(result.diagnostics.reject_reason, "vad_no_speech")
        self.assertEqual(result.diagnostics.speech_ms, 0)
        self.assertFalse(result.diagnostics.transcribed)

        transcriber = _VadTranscriber("Rohan", speech_ms=640)
        recognizer = BufferedSpeechRecognizer(transcriber, executor=_InlineExecutor())
        recognizer.update(_tone(1_000), 16_000, True, ["Rohan"])
        result, _ = recognizer.update(_silence(1_000), 16_000, False, ["Rohan"])
        self.assertEqual(transcriber.calls, 1)
        self.assertIsNotNone(result.phrase_match)
        self.assertEqual(result.diagnostics.speech_ms, 640)
        self.assertEqual(result.diagnostics.no_speech_probability, 0.12)
        self.assertNotIn("Rohan", str(result.diagnostics.to_wire()))

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
        recognizer.update(_silence(500), 16_000, False, ["Akshaj"], "Akshaj. Hey Akshaj.", ["Akshaj", "Maya"])

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
        completed, _ = recognizer.update(_silence(500), 16_000, False, ["Akshaj"])

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
