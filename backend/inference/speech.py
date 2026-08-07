"""Speech gating and configured phrase matching."""

from __future__ import annotations

import re
import math
import logging
import threading
import time
import unicodedata
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol


LOGGER = logging.getLogger("quietcue.speech")


class SpeechTranscriber(Protocol):
    """Interface for a local Whisper/ASR implementation on a capable hub."""

    def transcribe_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        prompt: str = "",
        hotwords: list[str] | None = None,
    ) -> "Transcript | None": ...


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class PhraseMatch:
    phrase: str
    transcript: str
    confidence: float


class DisabledTranscriber:
    """Explicit placeholder until a local ASR runtime is selected and measured."""

    def transcribe_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        prompt: str = "",
        hotwords: list[str] | None = None,
    ) -> Transcript | None:
        return None


class FasterWhisperTranscriber:
    """Lazy, local Faster-Whisper adapter for mono 16 kHz PCM16 audio."""

    def __init__(
        self,
        model_name: str = "tiny.en",
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str | None = "en",
    ) -> None:
        if not model_name.strip():
            raise ValueError("Speech model name cannot be blank")
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model: object | None = None
        self._model_lock = threading.Lock()

    def transcribe_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        prompt: str = "",
        hotwords: list[str] | None = None,
    ) -> Transcript | None:
        if sample_rate != 16_000:
            raise ValueError("Faster-Whisper input must be 16 kHz")
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM16 payload must contain complete samples")
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "Speech dependencies are missing; install backend/requirements-speech.txt"
            ) from exc

        model = self._load_model()
        waveform = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        segments, _ = model.transcribe(
            waveform,
            language=self.language,
            beam_size=1,
            condition_on_previous_text=False,
            vad_filter=False,
            initial_prompt=prompt or None,
            hotwords=", ".join(hotwords or []) or None,
        )
        completed = list(segments)
        text = " ".join(segment.text.strip() for segment in completed if segment.text.strip()).strip()
        if not text:
            return None
        mean_log_probability = sum(float(segment.avg_logprob) for segment in completed) / len(completed)
        confidence = max(0.0, min(1.0, math.exp(min(0.0, mean_log_probability))))
        return Transcript(text=text, confidence=round(confidence, 4))

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Speech dependencies are missing; install backend/requirements-speech.txt"
                ) from exc
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            return self._model


def find_phrase_match(
    transcript: Transcript,
    phrases: list[str],
    sensitivity: float = 0.6,
) -> PhraseMatch | None:
    """Fuzzily match bounded token windows without exposing transcript text."""
    if not 0.0 <= sensitivity <= 1.0:
        raise ValueError("Speech sensitivity must be between zero and one")
    normalized_transcript = _normalize(transcript.text)
    transcript_tokens = normalized_transcript.split()
    candidates = sorted(
        ((_normalize(phrase), phrase.strip()) for phrase in phrases if phrase.strip()),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    best: tuple[float, int, str] | None = None
    for normalized_phrase, original_phrase in candidates:
        if not normalized_phrase:
            continue
        phrase_tokens = normalized_phrase.split()
        for window_size in range(max(1, len(phrase_tokens) - 1), len(phrase_tokens) + 2):
            for start in range(0, len(transcript_tokens) - window_size + 1):
                window = " ".join(transcript_tokens[start : start + window_size])
                score = _phrase_similarity(normalized_phrase, window)
                candidate = (score, len(normalized_phrase), original_phrase)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
    if best is None or best[0] < sensitivity:
        if best is not None and best[0] >= max(0.0, sensitivity - 0.15):
            LOGGER.debug("Rejected near-match for configured phrase %r at %.3f", best[2], best[0])
        return None
    asr_confidence = transcript.confidence if transcript.confidence is not None else 1.0
    confidence = max(0.0, min(1.0, best[0] * asr_confidence))
    return PhraseMatch(
        phrase=best[2],
        transcript=transcript.text,
        confidence=round(confidence, 4),
    )


@dataclass(frozen=True)
class SpeechRecognition:
    transcript: Transcript | None
    phrase_match: PhraseMatch | None
    inference_ms: float
    error: str | None = None


class BufferedSpeechRecognizer:
    """Buffer speech and transcribe it on one background worker.

    ``update`` never waits for the model. Environmental inference can therefore
    continue while the previous speech window is being transcribed.
    """

    def __init__(
        self,
        transcriber: SpeechTranscriber,
        *,
        min_audio_ms: int = 1_000,
        end_of_utterance_ms: int = 500,
        max_audio_ms: int = 4_000,
        overlap_ms: int = 250,
        executor: Executor | None = None,
    ) -> None:
        if not 200 <= end_of_utterance_ms <= min_audio_ms <= max_audio_ms:
            raise ValueError("Speech buffer durations are inconsistent")
        if not 0 <= overlap_ms < min_audio_ms:
            raise ValueError("Speech overlap must be shorter than the minimum window")
        self.transcriber = transcriber
        self.min_audio_ms = min_audio_ms
        self.end_of_utterance_ms = end_of_utterance_ms
        self.max_audio_ms = max_audio_ms
        self.overlap_ms = overlap_ms
        self._buffer = bytearray()
        self._future: Future[SpeechRecognition] | None = None
        self._was_voice = False
        self._owns_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="quietcue-speech",
        )

    def update(
        self,
        pcm: bytes,
        sample_rate: int,
        voice_detected: bool,
        phrase_triggers: list[str],
        prompt: str = "",
        hotwords: list[str] | None = None,
        sensitivity: float = 0.6,
    ) -> tuple[SpeechRecognition | None, bool]:
        if sample_rate != 16_000:
            raise ValueError("Speech buffering currently requires 16 kHz audio")
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM16 payload must contain complete samples")

        completed = self._take_completed()
        if voice_detected:
            self._buffer.extend(pcm)
            self._trim(sample_rate)

        duration_ms = _pcm_duration_ms(self._buffer, sample_rate)
        utterance_ended = self._was_voice and not voice_detected
        should_submit = duration_ms >= self.min_audio_ms or (
            utterance_ended and duration_ms >= self.end_of_utterance_ms
        )
        if self._future is None and should_submit and phrase_triggers:
            self._submit(sample_rate, phrase_triggers, prompt, hotwords or [], sensitivity)
        elif utterance_ended and duration_ms < self.end_of_utterance_ms:
            self._buffer.clear()
        self._was_voice = voice_detected
        return completed, self._future is not None

    def close(self) -> None:
        self.reset()
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def reset(self) -> None:
        """Discard buffered/pending results when an audio-stream session changes."""
        self._buffer.clear()
        if self._future is not None:
            self._future.cancel()
            self._future = None
        self._was_voice = False

    def _submit(
        self,
        sample_rate: int,
        phrase_triggers: list[str],
        prompt: str,
        hotwords: list[str],
        sensitivity: float,
    ) -> None:
        audio = bytes(self._buffer)
        overlap_bytes = _bytes_for_ms(sample_rate, self.overlap_ms)
        self._buffer = bytearray(self._buffer[-overlap_bytes:]) if overlap_bytes else bytearray()
        self._future = self._executor.submit(
            _recognize,
            self.transcriber,
            audio,
            sample_rate,
            list(phrase_triggers),
            prompt,
            list(hotwords),
            sensitivity,
        )

    def _take_completed(self) -> SpeechRecognition | None:
        future = self._future
        if future is None or not future.done():
            return None
        self._future = None
        try:
            return future.result()
        except Exception as exc:  # Model/runtime errors must not stop environmental inference.
            return SpeechRecognition(None, None, 0.0, error=str(exc))

    def _trim(self, sample_rate: int) -> None:
        maximum_bytes = _bytes_for_ms(sample_rate, self.max_audio_ms)
        if len(self._buffer) > maximum_bytes:
            del self._buffer[:-maximum_bytes]


def _recognize(
    transcriber: SpeechTranscriber,
    pcm: bytes,
    sample_rate: int,
    phrase_triggers: list[str],
    prompt: str,
    hotwords: list[str],
    sensitivity: float,
) -> SpeechRecognition:
    started = time.perf_counter()
    transcript = transcriber.transcribe_pcm16(pcm, sample_rate, prompt, hotwords)
    inference_ms = (time.perf_counter() - started) * 1_000
    phrase_match = (
        find_phrase_match(transcript, phrase_triggers, sensitivity) if transcript is not None else None
    )
    return SpeechRecognition(
        transcript=transcript,
        phrase_match=phrase_match,
        inference_ms=round(inference_ms, 2),
    )


def _bytes_for_ms(sample_rate: int, duration_ms: int) -> int:
    return round(sample_rate * duration_ms / 1_000) * 2


def _pcm_duration_ms(pcm: bytes | bytearray, sample_rate: int) -> int:
    return round((len(pcm) // 2) * 1_000 / sample_rate)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    words_only = re.sub(r"[^a-z0-9]+", " ", without_marks)
    return " ".join(words_only.split())


def _phrase_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    left_phonetic = "".join(_phonetic_key(token) for token in left.split())
    right_phonetic = "".join(_phonetic_key(token) for token in right.split())
    if left_phonetic and left_phonetic == right_phonetic:
        return 0.9
    return _edit_similarity(left, right)


def _phonetic_key(token: str) -> str:
    value = token.replace("ph", "f").replace("ck", "k")
    collapsed: list[str] = []
    for character in value:
        if collapsed and collapsed[-1] == character:
            continue
        collapsed.append(character)
    if not collapsed:
        return ""
    return collapsed[0] + "".join(
        character for character in collapsed[1:] if character not in "aeiou"
    )


def _edit_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return 1.0 - previous[-1] / max(len(left), len(right))
