"""Map AudioSet/YAMNet labels into QuietCue's small event vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class Prediction(Protocol):
    label: str
    confidence: float


@dataclass(frozen=True)
class MappedEvent:
    event: str
    confidence: float
    source_label: str


@dataclass(frozen=True)
class MappingResult:
    events: tuple[MappedEvent, ...]
    speech_confidence: float


_EVENT_TERMS: dict[str, tuple[str, ...]] = {
    "fire_alarm": ("fire alarm", "smoke detector", "smoke alarm"),
    "doorbell_knock": ("doorbell", "ding-dong", "knock"),
    "car_horn": ("vehicle horn", "car horn", "honking", "air horn", "truck horn"),
    "siren": ("siren", "emergency vehicle"),
    "baby_crying": ("baby cry", "infant cry", "crying, sobbing"),
    "kitchen_timer": ("timer", "alarm clock"),
    "phone_ringing": ("telephone bell ringing", "ringtone"),
}

_SPEECH_TERMS = (
    "speech",
    "conversation",
    "narration",
    "child speech",
)


def map_predictions(
    predictions: Sequence[Prediction],
    minimum_confidence: float = 0.10,
) -> MappingResult:
    """Return the strongest supported label for each QuietCue event."""
    strongest: dict[str, MappedEvent] = {}
    speech_confidence = 0.0
    for prediction in predictions:
        label = prediction.label.strip().lower()
        confidence = float(prediction.confidence)
        if any(term in label for term in _SPEECH_TERMS):
            speech_confidence = max(speech_confidence, confidence)
        for event, terms in _EVENT_TERMS.items():
            if confidence < minimum_confidence or not any(term in label for term in terms):
                continue
            existing = strongest.get(event)
            if existing is None or confidence > existing.confidence:
                strongest[event] = MappedEvent(
                    event=event,
                    confidence=confidence,
                    source_label=prediction.label,
                )
    return MappingResult(
        events=tuple(sorted(strongest.values(), key=lambda event: event.confidence, reverse=True)),
        speech_confidence=speech_confidence,
    )
