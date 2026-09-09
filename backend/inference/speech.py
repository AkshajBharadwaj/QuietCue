"""Speech gating and configured phrase matching.

Design notes (September 2026 overhaul):

* Audio is never discarded before transcription. A rolling buffer keeps the
  last few seconds; the voice gate only decides *when* a window is sent to
  Whisper, so quiet or distant speech and names that straddle a chunk
  boundary still reach the model.
* The event confidence is the phrase-match score alone. Whisper's sentence
  log-probability is a poor proxy for "the name was said", so it is only used
  as a coarse floor against hallucinated text (word-level when available).
* Diagnostics carry the match score, ASR confidence, window length, and the
  rejection reason, never the transcript.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
import unicodedata
from array import array
from collections import deque
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Protocol


LOGGER = logging.getLogger("quietcue.speech")

WHISPER_MODEL_NAMES = {
    "tiny_en": "tiny.en",
    "base_en": "base.en",
    "small_en": "small.en",
}
DEFAULT_WHISPER_MODEL = "base.en"


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
class TranscriptWord:
    text: str
    probability: float


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float | None = None
    words: tuple[TranscriptWord, ...] = ()


@dataclass(frozen=True)
class PhraseMatch:
    phrase: str
    transcript: str
    confidence: float
    asr_confidence: float = 1.0


@dataclass(frozen=True)
class PhraseEvaluation:
    """Privacy-safe outcome of matching one transcript against the triggers."""

    match: PhraseMatch | None
    best_phrase: str | None
    best_score: float
    asr_confidence: float
    reject_reason: str | None


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
    """Lazy, local Faster-Whisper adapter for mono 16 kHz PCM16 audio.

    The model can be swapped at runtime (the phone's Tiny/Base/Small choice);
    the next transcription loads the new weights.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_WHISPER_MODEL,
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

    def set_model(self, model_name: str) -> bool:
        """Select a different Whisper model; returns True when it changed."""
        if not model_name.strip():
            raise ValueError("Speech model name cannot be blank")
        with self._model_lock:
            if model_name == self.model_name:
                return False
            self.model_name = model_name
            self._model = None
            return True

    def preload(self) -> None:
        self._load_model()

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
            # Short windows hallucinate at high fallback temperatures; stop early.
            temperature=[0.0, 0.2, 0.4],
            condition_on_previous_text=False,
            vad_filter=False,
            # word_timestamps=True was measured at 4-6 s per window on tiny/base
            # and made the decoder repeat prompt names; keep it off.
            word_timestamps=False,
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
            LOGGER.info("Loading Faster-Whisper model %s (%s, %s)", self.model_name, self.device, self.compute_type)
            self._model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            return self._model


# --------------------------------------------------------------------------- matching


ASR_CONFIDENCE_FLOOR = 0.20


def evaluate_phrase_match(
    transcript: Transcript,
    phrases: list[str],
    sensitivity: float = 0.6,
    asr_floor: float = ASR_CONFIDENCE_FLOOR,
) -> PhraseEvaluation:
    """Fuzzily match bounded token windows without exposing transcript text.

    The returned confidence is the match score. ASR confidence (word-level when
    the transcriber provides it) is only a floor against hallucinated text.
    """
    if not 0.0 <= sensitivity <= 1.0:
        raise ValueError("Speech sensitivity must be between zero and one")
    tokens, token_confidences = _tokens_with_confidence(transcript)
    candidates = sorted(
        ((_normalize(phrase), phrase.strip()) for phrase in phrases if phrase.strip()),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    best: tuple[float, int, str, float] | None = None
    for normalized_phrase, original_phrase in candidates:
        if not normalized_phrase:
            continue
        phrase_tokens = normalized_phrase.split()
        for window_size in range(max(1, len(phrase_tokens) - 1), len(phrase_tokens) + 2):
            for start in range(0, len(tokens) - window_size + 1):
                window = " ".join(tokens[start : start + window_size])
                score = _phrase_similarity(normalized_phrase, window)
                window_confidence = sum(token_confidences[start : start + window_size]) / window_size
                candidate = (score, len(normalized_phrase), original_phrase, window_confidence)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
    transcript_confidence = transcript.confidence if transcript.confidence is not None else 1.0
    if best is None:
        return PhraseEvaluation(None, None, 0.0, transcript_confidence, "no_tokens")
    score, _, phrase, asr_confidence = best
    if score < sensitivity:
        if score >= max(0.0, sensitivity - 0.15):
            LOGGER.debug("Rejected near-match for configured phrase %r at %.3f", phrase, score)
        return PhraseEvaluation(None, phrase, round(score, 4), round(asr_confidence, 4), "below_sensitivity")
    if asr_confidence < asr_floor:
        LOGGER.debug("Rejected %r: ASR confidence %.3f below floor", phrase, asr_confidence)
        return PhraseEvaluation(None, phrase, round(score, 4), round(asr_confidence, 4), "asr_confidence_floor")
    match = PhraseMatch(
        phrase=phrase,
        transcript=transcript.text,
        confidence=round(score, 4),
        asr_confidence=round(asr_confidence, 4),
    )
    return PhraseEvaluation(match, phrase, round(score, 4), round(asr_confidence, 4), None)


def find_phrase_match(
    transcript: Transcript,
    phrases: list[str],
    sensitivity: float = 0.6,
) -> PhraseMatch | None:
    return evaluate_phrase_match(transcript, phrases, sensitivity).match


def _tokens_with_confidence(transcript: Transcript) -> tuple[list[str], list[float]]:
    if transcript.words:
        tokens: list[str] = []
        confidences: list[float] = []
        for word in transcript.words:
            for token in _normalize(word.text).split():
                tokens.append(token)
                confidences.append(max(0.0, min(1.0, float(word.probability))))
        if tokens:
            return tokens, confidences
    tokens = _normalize(transcript.text).split()
    fallback = transcript.confidence if transcript.confidence is not None else 1.0
    return tokens, [fallback] * len(tokens)


# --------------------------------------------------------------------------- buffering


@dataclass(frozen=True)
class SpeechDiagnostics:
    """Metadata about one transcription window; never contains text."""

    window_ms: int
    asr_confidence: float | None
    match_score: float | None
    matched: bool
    reject_reason: str | None
    transcribed: bool

    def to_wire(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SpeechRecognition:
    transcript: Transcript | None
    phrase_match: PhraseMatch | None
    inference_ms: float
    error: str | None = None
    diagnostics: SpeechDiagnostics | None = None


class BufferedSpeechRecognizer:
    """Keep a rolling audio buffer and transcribe utterance windows in the background.

    ``update`` never waits for the model. Environmental inference can therefore
    continue while the previous speech window is being transcribed.

    Every chunk is buffered regardless of the voice gate. The gate (edge VAD,
    YAMNet speech labels, or hub-side energy activity) plus a short trailing
    silence decide when the unsent audio, with pre-roll overlap, is submitted.
    """

    FRAME_MS = 20
    ACTIVITY_MARGIN_DB = 15.0
    SILENCE_MARGIN_DB = 6.0
    MIN_ACTIVITY_MS = 200
    MIN_NOISE_FLOOR_DBFS = -75.0

    def __init__(
        self,
        transcriber: SpeechTranscriber,
        *,
        min_audio_ms: int = 1_000,
        end_of_utterance_ms: int = 450,
        max_audio_ms: int = 4_000,
        overlap_ms: int = 800,
        buffer_ms: int = 6_000,
        executor: Executor | None = None,
    ) -> None:
        if not 200 <= end_of_utterance_ms <= min_audio_ms <= max_audio_ms <= buffer_ms:
            raise ValueError("Speech buffer durations are inconsistent")
        if not 0 <= overlap_ms < min_audio_ms:
            raise ValueError("Speech overlap must be shorter than the minimum window")
        self.transcriber = transcriber
        self.min_audio_ms = min_audio_ms
        self.end_of_utterance_ms = end_of_utterance_ms
        self.max_audio_ms = max_audio_ms
        self.overlap_ms = overlap_ms
        self.buffer_ms = buffer_ms
        self._buffer = bytearray()
        self._consumed = 0
        self._levels: deque[float] = deque(maxlen=buffer_ms // self.FRAME_MS)
        self._voice_seen = False
        self._future: Future[SpeechRecognition] | None = None
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

        levels = _frame_levels_dbfs(pcm, sample_rate, self.FRAME_MS)
        self._levels.extend(levels)
        # Real microphones idle around -60 dBFS; clamp so digital silence does
        # not turn every faint hum into "speech".
        noise_floor = max(_percentile(self._levels, 0.10), self.MIN_NOISE_FLOOR_DBFS)
        active_ms = sum(1 for level in levels if level >= noise_floor + self.ACTIVITY_MARGIN_DB) * self.FRAME_MS
        trailing_silence_ms = 0
        for level in reversed(levels):
            if level >= noise_floor + self.SILENCE_MARGIN_DB:
                break
            trailing_silence_ms += self.FRAME_MS
        activity = voice_detected or active_ms >= self.MIN_ACTIVITY_MS

        self._buffer.extend(pcm)
        self._trim(sample_rate)
        if activity:
            self._voice_seen = True

        unsent_ms = _pcm_duration_ms(self._buffer[self._consumed :], sample_rate)
        utterance_ended = self._voice_seen and (
            not activity or trailing_silence_ms >= self.end_of_utterance_ms
        )
        should_submit = self._voice_seen and (utterance_ended or unsent_ms >= self.max_audio_ms)
        if should_submit and phrase_triggers:
            if self._future is None:
                self._submit(sample_rate, phrase_triggers, prompt, hotwords or [], sensitivity)
            # Otherwise the worker is busy; the unsent audio stays queued for the next update.
        elif not self._voice_seen or not phrase_triggers:
            # Silence only (or nothing to listen for): keep the buffer as pre-roll
            # but do not accumulate it as unsent speech.
            self._consumed = len(self._buffer)
            self._voice_seen = False
        return completed, self._future is not None

    def close(self) -> None:
        self.reset()
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def reset(self) -> None:
        """Discard buffered/pending results when an audio-stream session changes."""
        self._buffer.clear()
        self._consumed = 0
        self._levels.clear()
        self._voice_seen = False
        if self._future is not None:
            self._future.cancel()
            self._future = None

    def _submit(
        self,
        sample_rate: int,
        phrase_triggers: list[str],
        prompt: str,
        hotwords: list[str],
        sensitivity: float,
    ) -> None:
        total = len(self._buffer)
        overlap_bytes = _bytes_for_ms(sample_rate, self.overlap_ms)
        start = max(0, self._consumed - overlap_bytes, total - _bytes_for_ms(sample_rate, self.max_audio_ms))
        start = max(0, min(start, total - _bytes_for_ms(sample_rate, self.min_audio_ms)))
        audio = bytes(self._buffer[start:])
        self._consumed = total
        self._voice_seen = False
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
        maximum_bytes = _bytes_for_ms(sample_rate, self.buffer_ms)
        excess = len(self._buffer) - maximum_bytes
        if excess > 0:
            del self._buffer[:excess]
            self._consumed = max(0, self._consumed - excess)


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
    window_ms = _pcm_duration_ms(pcm, sample_rate)
    if transcript is None:
        return SpeechRecognition(
            transcript=None,
            phrase_match=None,
            inference_ms=round(inference_ms, 2),
            diagnostics=SpeechDiagnostics(window_ms, None, None, False, "no_speech", False),
        )
    evaluation = evaluate_phrase_match(transcript, phrase_triggers, sensitivity)
    return SpeechRecognition(
        transcript=transcript,
        phrase_match=evaluation.match,
        inference_ms=round(inference_ms, 2),
        diagnostics=SpeechDiagnostics(
            window_ms=window_ms,
            asr_confidence=evaluation.asr_confidence,
            match_score=evaluation.best_score if evaluation.best_phrase is not None else None,
            matched=evaluation.match is not None,
            reject_reason=evaluation.reject_reason,
            transcribed=True,
        ),
    )


def _frame_levels_dbfs(pcm: bytes, sample_rate: int, frame_ms: int) -> list[float]:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    frame = max(1, sample_rate * frame_ms // 1_000)
    levels: list[float] = []
    for start in range(0, len(samples) - frame + 1, frame):
        chunk = samples[start : start + frame]
        energy = sum(sample * sample for sample in chunk) / frame
        levels.append(20.0 * math.log10(max(math.sqrt(energy) / 32768.0, 1e-9)))
    return levels


def _percentile(values: deque[float] | list[float], fraction: float) -> float:
    if not values:
        return -180.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction)))
    return ordered[index]


def _bytes_for_ms(sample_rate: int, duration_ms: int) -> int:
    return round(sample_rate * duration_ms / 1_000) * 2


def _pcm_duration_ms(pcm: bytes | bytearray, sample_rate: int) -> int:
    return round((len(pcm) // 2) * 1_000 / sample_rate)


# --------------------------------------------------------------------------- text similarity


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    words_only = re.sub(r"[^a-z0-9]+", " ", without_marks)
    return " ".join(words_only.split())


def _phrase_similarity(left: str, right: str) -> float:
    """1.0 exact, 0.9 phonetically equal, else letter edit similarity."""
    if left == right:
        return 1.0
    left_joined = left.replace(" ", "")
    right_joined = right.replace(" ", "")
    if left_joined == right_joined:
        return 0.95
    letters = _edit_similarity(left, right)
    if (
        min(len(left_joined), len(right_joined)) >= 3
        and letters >= 0.5
        and _phonetic_key(left_joined) == _phonetic_key(right_joined)
        and _vowel_groups(left_joined) == _vowel_groups(right_joined)
    ):
        return 0.9
    # Names that do not sound alike lose a little, so a two-edit neighbour of a
    # five-letter name (Ryan/Ron/Robin for Rohan) sits below the default 0.6
    # sensitivity while a one-edit variant (Roan) stays above it.
    return max(0.0, letters - 0.05)


_VOWELS = set("aeiouy")
_DIGRAPHS = (
    ("sch", "sk"),
    ("ph", "f"),
    ("ck", "k"),
    ("kh", "k"),
    ("sh", "x"),
    ("ch", "x"),
    ("th", "0"),
    ("dj", "j"),
)


def _phonetic_key(token: str) -> str:
    """Compact name-oriented phonetic code.

    Vowel letters, intervocalic h/w and doubled letters are dropped, common
    digraphs collapsed, and c/q/z folded so that Rohan/Rowan/Ruhan or
    Stefan/Stephan or Maya/Maia share one code.
    """
    value = token.replace("x", "ks")
    for digraph, replacement in _DIGRAPHS:
        value = value.replace(digraph, replacement)
    if len(value) > 2:
        value = value[:2] + value[2:].replace("gh", "")
    value = value.replace("q", "k").replace("c", "k").replace("z", "s")
    characters: list[str] = []
    for index, character in enumerate(value):
        if character in "hw" and index > 0 and value[index - 1] in _VOWELS:
            continue
        characters.append(character)
    collapsed: list[str] = []
    for character in characters:
        if collapsed and collapsed[-1] == character:
            continue
        collapsed.append(character)
    if not collapsed:
        return ""
    return collapsed[0] + "".join(character for character in collapsed[1:] if character not in _VOWELS)


def _vowel_groups(token: str) -> int:
    groups = 0
    previous_vowel = False
    for character in token:
        is_vowel = character in _VOWELS
        if is_vowel and not previous_vowel:
            groups += 1
        previous_vowel = is_vowel
    return groups


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
