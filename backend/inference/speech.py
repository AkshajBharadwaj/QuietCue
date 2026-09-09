"""Speech gating and configured phrase matching.

Design notes (September 2026 overhaul):

* Audio is never discarded before transcription. A rolling buffer keeps the
  last few seconds; the voice gate only decides *when* a window is sent to
  Whisper, so quiet or distant speech and names that straddle a chunk
  boundary still reach the model.
* The event confidence is the phrase-match score alone. Whisper's sentence
  log-probability is a poor proxy for "the name was said", so it is only used
  as a coarse floor against hallucinated text (word-level when available).
* Names are never primed into the decoder. Measured on quiet-room audio
  (September 2026): with the name in ``initial_prompt`` or ``hotwords``
  Whisper wrote it onto 30-90 % of noise-only windows (tiny/base/small.en),
  and without any prompt onto none, at the cost of the very quietest windows.
  Enrollment (``name_enrollment.py``) learns the unprompted spellings
  ("Rowan" for Rohan) so recall comes from matching, not from priming.
* A window only reaches the decoder when Silero VAD hears speech somewhere in
  it. The whole window is kept or skipped; audio is never trimmed by VAD.
* After decoding, Whisper's own ``no_speech_prob`` and a repetition check
  reject the hallucination shapes noise produces ("Rohan Rohan.",
  "Hi Rohan." x29 at a fallback temperature).
* Diagnostics carry the match score, ASR confidence, no-speech probability,
  VAD speech length, window length, and the rejection reason, never text.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
import unicodedata
import zlib
from array import array
from collections import deque
from concurrent.futures import Executor, Future, ThreadPoolExecutor, wait
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
    # Whisper's probability that the window held no speech (max over segments).
    no_speech_probability: float | None = None
    # Highest decoding temperature the fallback ladder reached.
    temperature: float | None = None


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

    # Silero gate: lenient on purpose. Genuine speech in a 2.5 s window measured
    # >= 750 ms even 10 dB under the room bed; most noise windows measured 0 ms.
    VAD_THRESHOLD = 0.35
    VAD_MIN_SPEECH_MS = 100
    MAX_NEW_TOKENS = 48

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
        self._vad_unavailable = False

    def detect_speech_ms(self, pcm: bytes, sample_rate: int) -> int | None:
        """Milliseconds of speech Silero VAD hears in the window; None if unavailable.

        Unlike ``vad_filter=True`` this never cuts audio out of the window: the
        recognizer only uses it to skip windows that contain no speech at all.
        """
        if sample_rate != 16_000:
            raise ValueError("Faster-Whisper VAD input must be 16 kHz")
        if self._vad_unavailable:
            return None
        try:
            import numpy as np
            from faster_whisper.vad import VadOptions, get_speech_timestamps
        except ImportError:
            self._vad_unavailable = True
            return None
        waveform = np.frombuffer(pcm[: len(pcm) - len(pcm) % 2], dtype="<i2").astype(np.float32) / 32768.0
        try:
            spans = get_speech_timestamps(
                waveform,
                VadOptions(threshold=self.VAD_THRESHOLD, min_speech_duration_ms=self.VAD_MIN_SPEECH_MS),
            )
        except Exception as exc:  # A missing VAD asset must not disable name detection.
            LOGGER.warning("Silero VAD unavailable; transcribing every window: %s", exc)
            self._vad_unavailable = True
            return None
        return int(sum(span["end"] - span["start"] for span in spans) * 1_000 // sample_rate)

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
            # A 2.5 s window holds a dozen words at most. Capping the decoder
            # bounds the repetition loops noise triggers: base.en noise windows
            # went from ~2 s (max 3.8 s) to ~0.4 s (max 1 s) with speech output
            # unchanged, so a stuck decode can no longer delay the next window.
            max_new_tokens=self.MAX_NEW_TOKENS,
        )
        completed = list(segments)
        text = " ".join(segment.text.strip() for segment in completed if segment.text.strip()).strip()
        if not text:
            return None
        mean_log_probability = sum(float(segment.avg_logprob) for segment in completed) / len(completed)
        confidence = max(0.0, min(1.0, math.exp(min(0.0, mean_log_probability))))
        no_speech = max(float(segment.no_speech_prob) for segment in completed)
        temperature = max(float(getattr(segment, "temperature", 0.0) or 0.0) for segment in completed)
        return Transcript(
            text=text,
            confidence=round(confidence, 4),
            no_speech_probability=round(max(0.0, min(1.0, no_speech)), 4),
            temperature=round(temperature, 2),
        )

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
# Whisper echoes prompt names onto near-silent audio as a short transcript or
# a repeated name ("I'm Rohan Rohan.", confidence ~0.4). Genuine names alone
# measured 0.64-0.92 on tiny/base/small, so those shapes need more confidence.
ECHO_CONFIDENCE_FLOOR = 0.50
ECHO_MAX_TOKENS = 3
# Whisper's own no-speech estimate separates noise from speech far better than
# its log-probability: hallucinated names on room noise measured 0.44-0.86
# (tiny/base/small.en), genuine names at or above the room level 0.00-0.47.
MAX_NO_SPEECH_PROBABILITY = 0.60
# A decoder stuck in a loop ("Hi Rohan. Hi Rohan. ..." x29) compresses far
# better than speech; Whisper uses the same 2.4 ratio for its own fallback.
LOOP_COMPRESSION_RATIO = 2.4
# A 2.5 s window cannot hold a name three or more times.
LOOP_MIN_HITS = 3


def evaluate_phrase_match(
    transcript: Transcript,
    phrases: list[str],
    sensitivity: float = 0.6,
    asr_floor: float = ASR_CONFIDENCE_FLOOR,
    echo_floor: float = ECHO_CONFIDENCE_FLOOR,
    max_no_speech: float = MAX_NO_SPEECH_PROBABILITY,
) -> PhraseEvaluation:
    """Fuzzily match bounded token windows without exposing transcript text.

    The returned confidence is the match score. The other signals only reject:
    Whisper's no-speech probability and a repetition check catch what noise
    produces, and ASR confidence is a low floor against hallucinated text with
    a higher one for the transcript shapes a prompt echo produces.
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
    hits = 0
    for normalized_phrase, original_phrase in candidates:
        if not normalized_phrase:
            continue
        phrase_tokens = normalized_phrase.split()
        for window_size in range(max(1, len(phrase_tokens) - 1), len(phrase_tokens) + 2):
            for start in range(0, len(tokens) - window_size + 1):
                window = " ".join(tokens[start : start + window_size])
                score = _phrase_similarity(normalized_phrase, window)
                if window_size == len(phrase_tokens) and score >= sensitivity:
                    hits += 1
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
    no_speech = transcript.no_speech_probability
    if no_speech is not None and no_speech > max_no_speech:
        LOGGER.debug("Rejected %r: no-speech probability %.3f", phrase, no_speech)
        return PhraseEvaluation(None, phrase, round(score, 4), round(asr_confidence, 4), "no_speech_probability")
    if hits >= LOOP_MIN_HITS or _compression_ratio(transcript.text) > LOOP_COMPRESSION_RATIO:
        LOGGER.debug("Rejected %r: repetitive transcript (%d hits)", phrase, hits)
        return PhraseEvaluation(None, phrase, round(score, 4), round(asr_confidence, 4), "hallucination_loop")
    if asr_confidence < asr_floor:
        LOGGER.debug("Rejected %r: ASR confidence %.3f below floor", phrase, asr_confidence)
        return PhraseEvaluation(None, phrase, round(score, 4), round(asr_confidence, 4), "asr_confidence_floor")
    echo_shaped = len(tokens) <= ECHO_MAX_TOKENS or hits > 1
    if echo_shaped and asr_confidence < echo_floor:
        LOGGER.debug("Rejected %r: looks like a prompt echo (%d tokens, %d hits, %.3f)", phrase, len(tokens), hits, asr_confidence)
        return PhraseEvaluation(None, phrase, round(score, 4), round(asr_confidence, 4), "likely_prompt_echo")
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


# Windows with less Silero-detected speech than this skip the decoder entirely.
MIN_VAD_SPEECH_MS = 200


@dataclass(frozen=True)
class SpeechDiagnostics:
    """Metadata about one transcription window; never contains text."""

    window_ms: int
    asr_confidence: float | None
    match_score: float | None
    matched: bool
    reject_reason: str | None
    transcribed: bool
    speech_ms: int | None = None
    no_speech_probability: float | None = None

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
    MAX_NOISE_FLOOR_DBFS = -35.0
    MIN_FLOOR_HISTORY_FRAMES = 2_000 // FRAME_MS
    TAIL_PADDING_MS = 400

    def __init__(
        self,
        transcriber: SpeechTranscriber,
        *,
        min_audio_ms: int = 1_000,
        end_of_utterance_ms: int = 450,
        max_audio_ms: int = 2_500,
        overlap_ms: int = 800,
        buffer_ms: int = 6_000,
        result_wait_ms: int = 600,
        executor: Executor | None = None,
    ) -> None:
        if not 200 <= end_of_utterance_ms <= min_audio_ms <= max_audio_ms <= buffer_ms:
            raise ValueError("Speech buffer durations are inconsistent")
        if not 0 <= overlap_ms < min_audio_ms:
            raise ValueError("Speech overlap must be shorter than the minimum window")
        if result_wait_ms < 0:
            raise ValueError("Speech result wait must not be negative")
        self.transcriber = transcriber
        self.min_audio_ms = min_audio_ms
        self.end_of_utterance_ms = end_of_utterance_ms
        self.max_audio_ms = max_audio_ms
        self.overlap_ms = overlap_ms
        self.buffer_ms = buffer_ms
        self.result_wait_ms = result_wait_ms
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
        # not turn every faint hum into "speech". Until ~2 s of history exists
        # the percentile would just be the current chunk (speech included), so
        # start from the clamp instead.
        if len(self._levels) >= self.MIN_FLOOR_HISTORY_FRAMES:
            # Also cap it: a "floor" above -35 dBFS is sustained speech or
            # alarm, not the room, and would silence its own detection.
            noise_floor = min(
                self.MAX_NOISE_FLOOR_DBFS,
                max(_percentile(self._levels, 0.10), self.MIN_NOISE_FLOOR_DBFS),
            )
        else:
            noise_floor = self.MIN_NOISE_FLOOR_DBFS
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
                self._submit(sample_rate, phrase_triggers, prompt, hotwords or [], sensitivity, noise_floor)
                if completed is None and self._future is not None:
                    # A short decode (base.en: ~300 ms) can finish inside this
                    # chunk cycle; waiting briefly delivers the alert a full
                    # chunk earlier. The phone buffers its next chunk meanwhile.
                    completed = self._take_completed(timeout_ms=self.result_wait_ms)
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
        noise_floor: float,
    ) -> None:
        total = len(self._buffer)
        overlap_bytes = _bytes_for_ms(sample_rate, self.overlap_ms)
        # Take the *oldest* unsent audio first (with pre-roll). If more than one
        # window is queued, the remainder stays unsent for the next update so a
        # name at the start of a long sentence is never cut off.
        start = max(0, self._consumed - overlap_bytes)
        end = min(total, start + _bytes_for_ms(sample_rate, self.max_audio_ms))
        minimum_bytes = _bytes_for_ms(sample_rate, self.min_audio_ms)
        if end - start < minimum_bytes:
            start = max(0, end - minimum_bytes)
        consumed_before = self._consumed
        self._consumed = end
        self._voice_seen = end < total

        # Whisper hallucinates prompt names onto silence, so cut the window
        # shortly after the last speech-like frame and skip windows whose new
        # (non-overlap) audio carries no activity at all.
        audio = bytes(self._buffer[start:end])
        levels = _frame_levels_dbfs(audio, sample_rate, self.FRAME_MS)
        frame_bytes = _bytes_for_ms(sample_rate, self.FRAME_MS)
        active_threshold = noise_floor + self.SILENCE_MARGIN_DB
        last_active = max((index for index, level in enumerate(levels) if level >= active_threshold), default=-1)
        new_audio_start_frame = max(0, (consumed_before - start) // frame_bytes)
        new_active_ms = sum(
            self.FRAME_MS for level in levels[new_audio_start_frame:] if level >= active_threshold
        )
        if last_active < 0 or new_active_ms < self.MIN_ACTIVITY_MS // 2:
            return
        cut = min(len(audio), max(minimum_bytes, (last_active + 1) * frame_bytes + _bytes_for_ms(sample_rate, self.TAIL_PADDING_MS)))
        audio = audio[:cut]
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

    def _take_completed(self, timeout_ms: int = 0) -> SpeechRecognition | None:
        future = self._future
        if future is None:
            return None
        if not future.done():
            if timeout_ms <= 0:
                return None
            wait([future], timeout=timeout_ms / 1_000)
            if not future.done():
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
    window_ms = _pcm_duration_ms(pcm, sample_rate)
    speech_ms: int | None = None
    detect = getattr(transcriber, "detect_speech_ms", None)
    if callable(detect):
        speech_ms = detect(pcm, sample_rate)
        if speech_ms is not None and speech_ms < MIN_VAD_SPEECH_MS:
            inference_ms = (time.perf_counter() - started) * 1_000
            return SpeechRecognition(
                transcript=None,
                phrase_match=None,
                inference_ms=round(inference_ms, 2),
                diagnostics=SpeechDiagnostics(
                    window_ms, None, None, False, "vad_no_speech", False, speech_ms=speech_ms
                ),
            )
    transcript = transcriber.transcribe_pcm16(pcm, sample_rate, prompt, hotwords)
    inference_ms = (time.perf_counter() - started) * 1_000
    if transcript is None:
        return SpeechRecognition(
            transcript=None,
            phrase_match=None,
            inference_ms=round(inference_ms, 2),
            diagnostics=SpeechDiagnostics(
                window_ms, None, None, False, "no_speech", False, speech_ms=speech_ms
            ),
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
            speech_ms=speech_ms,
            no_speech_probability=transcript.no_speech_probability,
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


def _compression_ratio(text: str) -> float:
    """Whisper's repetition measure: bytes of text per byte of zlib output."""
    encoded = text.encode("utf-8")
    if not encoded:
        return 0.0
    return len(encoded) / max(1, len(zlib.compress(encoded)))


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
