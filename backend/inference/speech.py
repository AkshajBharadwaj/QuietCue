"""Speech gating and configured phrase matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol


class SpeechTranscriber(Protocol):
    """Interface for a local Whisper/ASR implementation on a capable hub."""

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int) -> "Transcript | None": ...


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

    def transcribe_pcm16(self, pcm: bytes, sample_rate: int) -> Transcript | None:
        return None


def find_phrase_match(transcript: Transcript, phrases: list[str]) -> PhraseMatch | None:
    """Match normalized whole-word phrases, preferring the longest match."""
    normalized_transcript = _normalize(transcript.text)
    candidates = sorted(
        ((_normalize(phrase), phrase.strip()) for phrase in phrases if phrase.strip()),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for normalized_phrase, original_phrase in candidates:
        if not normalized_phrase:
            continue
        pattern = rf"(?:^|\s){re.escape(normalized_phrase)}(?:$|\s)"
        if re.search(pattern, normalized_transcript):
            return PhraseMatch(
                phrase=original_phrase,
                transcript=transcript.text,
                confidence=transcript.confidence if transcript.confidence is not None else 0.75,
            )
    return None


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    without_marks = "".join(character for character in decomposed if not unicodedata.combining(character))
    words_only = re.sub(r"[^a-z0-9]+", " ", without_marks)
    return " ".join(words_only.split())
