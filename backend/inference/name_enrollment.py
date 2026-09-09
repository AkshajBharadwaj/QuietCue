"""Learn how the hub's own Whisper model spells a user's name.

The phone's speech recognizer learns Apple's confusions, not Whisper's. This
controller captures a few seconds of the live stream while someone says the
name, transcribes it with the same model and prompt the live path uses, and
returns only the word(s) closest to the name. Raw audio and the surrounding
transcript are discarded.
"""

from __future__ import annotations

import uuid
from array import array
from typing import Any

from backend.inference.speech import (
    SpeechTranscriber,
    Transcript,
    _normalize,
    _phrase_similarity,
)


SAMPLE_RATE = 16_000
MIN_DURATION_MS = 2_000
MAX_DURATION_MS = 8_000
DEFAULT_DURATION_MS = 4_000
MIN_SUGGESTION_SCORE = 0.5
MAX_KNOWN_SPELLINGS = 20
_FILLER_WORDS = {"hey", "hi", "yo", "oh", "um", "uh"}


class NameEnrollmentController:
    """State machine: idle -> recording -> processing -> complete | error."""

    def __init__(self) -> None:
        self._state = "idle"
        self._session_id = ""
        self._name = ""
        self._known: tuple[str, ...] = ()
        self._target_bytes = 0
        self._samples = bytearray()
        self._result: dict[str, Any] = {}

    def start(
        self,
        name: str,
        known_spellings: list[str] | tuple[str, ...] = (),
        duration_ms: int = DEFAULT_DURATION_MS,
    ) -> dict[str, Any]:
        cleaned = name.strip()
        if not cleaned or len(cleaned) > 60:
            raise ValueError("Name must be between 1 and 60 characters")
        if not MIN_DURATION_MS <= duration_ms <= MAX_DURATION_MS:
            raise ValueError(
                f"Name enrollment duration must be between {MIN_DURATION_MS} and {MAX_DURATION_MS} ms"
            )
        if len(known_spellings) > MAX_KNOWN_SPELLINGS:
            raise ValueError("Too many known spellings")
        self._state = "recording"
        self._session_id = uuid.uuid4().hex
        self._name = cleaned
        self._known = tuple(
            value.strip() for value in known_spellings if isinstance(value, str) and value.strip()
        )
        self._target_bytes = SAMPLE_RATE * duration_ms // 1_000 * 2
        self._samples = bytearray()
        self._result = {}
        return self.status()

    def cancel(self) -> dict[str, Any]:
        self._state = "idle"
        self._samples = bytearray()
        self._result = {}
        return self.status()

    def observe(self, pcm: bytes, sample_rate: int) -> bytes | None:
        """Buffer live audio; return the captured window once the session is full."""
        if self._state != "recording":
            return None
        if sample_rate != SAMPLE_RATE:
            self.fail("Name enrollment requires 16 kHz audio")
            return None
        if not pcm or len(pcm) % 2:
            self.fail("Name enrollment received malformed PCM audio")
            return None
        remaining = self._target_bytes - len(self._samples)
        self._samples.extend(pcm[:remaining])
        if len(self._samples) < self._target_bytes:
            return None
        captured = bytes(self._samples)
        self._samples = bytearray()
        self._state = "processing"
        return captured

    def complete(self, result: dict[str, Any]) -> None:
        if self._state != "processing":
            return
        self._result = result
        self._state = "complete"

    def fail(self, message: str) -> None:
        self._state = "error"
        self._result = {"error": message}
        self._samples = bytearray()

    @property
    def name(self) -> str:
        return self._name

    @property
    def known_spellings(self) -> tuple[str, ...]:
        return self._known

    def status(self) -> dict[str, Any]:
        remaining_bytes = max(0, self._target_bytes - len(self._samples)) if self._state == "recording" else 0
        document: dict[str, Any] = {
            "state": self._state,
            "session_id": self._session_id,
            "remaining_ms": round(remaining_bytes / 2 * 1_000 / SAMPLE_RATE),
        }
        document.update(self._result)
        return document


def analyze_name_sample(
    transcriber: SpeechTranscriber,
    pcm: bytes,
    sample_rate: int,
    name: str,
    known_spellings: tuple[str, ...] | list[str],
    prompt: str,
    hotwords: list[str],
) -> dict[str, Any]:
    """Return the spellings Whisper produced for ``name``; never the transcript.

    The window is transcribed twice: with the live prompt/hotwords (what the
    detector will see) and without (what an unbiased decode hears). Any window
    of one or two words that resembles the name and is not already a known
    spelling becomes a suggestion.
    """
    if _rms(pcm) < 0.003:
        return {"heard": [], "recognized": False, "error": "No speech was heard; say the name closer to the phone"}
    targets = [name, *known_spellings]
    normalized_known = {_normalize(value) for value in targets}
    suggestions: list[str] = []
    recognized = False
    best_score = 0.0
    for use_prompt in (True, False):
        transcript = transcriber.transcribe_pcm16(
            pcm,
            sample_rate,
            prompt if use_prompt else "",
            hotwords if use_prompt else None,
        )
        if transcript is None:
            continue
        window, score = _closest_window(transcript, targets)
        best_score = max(best_score, score)
        if window is None:
            continue
        if _normalize(window) in normalized_known:
            recognized = True
            continue
        if score < MIN_SUGGESTION_SCORE:
            # The user was asked to say only the name. If Whisper heard one or
            # two words, that *is* its spelling of the name, however far off.
            short = _short_utterance(transcript)
            if short is None or _normalize(short) in normalized_known:
                recognized = recognized or short is not None
                continue
            window = short
        if window.casefold() not in {item.casefold() for item in suggestions}:
            suggestions.append(window)
    if not recognized and not suggestions:
        return {
            "heard": [],
            "recognized": False,
            "best_score": round(best_score, 3),
            "error": "Nothing close to the name was recognized; try again in a quieter spot",
        }
    return {"heard": suggestions, "recognized": recognized, "best_score": round(best_score, 3)}


def _short_utterance(transcript: Transcript) -> str | None:
    tokens = [token.strip(" ,.!?;:\"'") for token in transcript.text.split()]
    tokens = [token for token in tokens if token and _normalize(token) not in _FILLER_WORDS]
    if not tokens or len(tokens) > 2:
        return None
    return " ".join(tokens)


def _closest_window(transcript: Transcript, targets: list[str]) -> tuple[str | None, float]:
    words = [word.text for word in transcript.words] or transcript.text.split()
    display_tokens: list[str] = []
    normalized_tokens: list[str] = []
    for word in words:
        normalized = _normalize(word)
        if normalized:
            display_tokens.append(word.strip(" ,.!?;:\"'"))
            normalized_tokens.append(normalized)
    best: tuple[float, str] | None = None
    normalized_targets = [_normalize(target) for target in targets if _normalize(target)]
    for size in (1, 2):
        for start in range(0, len(normalized_tokens) - size + 1):
            window = " ".join(normalized_tokens[start : start + size])
            score = max((_phrase_similarity(target, window) for target in normalized_targets), default=0.0)
            if best is None or score > best[0]:
                best = (score, " ".join(display_tokens[start : start + size]))
    if best is None:
        return None, 0.0
    return best[1], best[0]


def _rms(pcm: bytes) -> float:
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    if not samples:
        return 0.0
    return (sum(sample * sample for sample in samples) / len(samples)) ** 0.5 / 32768.0
