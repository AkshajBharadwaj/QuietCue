"""Second-stage environmental and speech inference on a capable hub."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Protocol

from backend.inference.event_mapper import MappedEvent, map_predictions
from backend.inference.models import SoundPrediction
from backend.inference.speech import DisabledTranscriber, SpeechTranscriber, find_phrase_match


class SoundClassifier(Protocol):
    def classify_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        top_k: int = 10,
    ) -> list[SoundPrediction]: ...


@dataclass(frozen=True)
class ConfirmedEvent:
    event: str
    confidence: float
    source_label: str
    category: str
    pattern: str
    requires_ack: bool


@dataclass(frozen=True)
class HubInferenceResult:
    events: tuple[ConfirmedEvent, ...]
    voice_detected: bool
    speech_confidence: float
    transcript: str | None
    inference_ms: float
    total_ms: float
    top_predictions: tuple[dict[str, object], ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "events": [asdict(event) for event in self.events],
            "voice_detected": self.voice_detected,
            "speech_confidence": self.speech_confidence,
            "transcript": self.transcript,
            "inference_ms": self.inference_ms,
            "total_ms": self.total_ms,
            "top_predictions": list(self.top_predictions),
        }


class HubInferencePipeline:
    """Confirm edge candidates while keeping speech on a separate gated path."""

    def __init__(
        self,
        classifier: SoundClassifier,
        transcriber: SpeechTranscriber | None = None,
    ) -> None:
        self.classifier = classifier
        self.transcriber = transcriber or DisabledTranscriber()

    def process_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        edge_analysis: dict[str, object] | None = None,
        phrase_triggers: list[str] | None = None,
    ) -> HubInferenceResult:
        if sample_rate != 16_000:
            raise ValueError("Hub baseline currently requires 16 kHz audio")
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM16 payload must contain complete samples")

        started = time.perf_counter()
        inference_started = time.perf_counter()
        predictions = self.classifier.classify_pcm16(pcm, sample_rate, top_k=10)
        inference_ms = (time.perf_counter() - inference_started) * 1_000
        mapping = map_predictions(predictions)

        edge_voice = bool((edge_analysis or {}).get("voice_activity", False))
        voice_detected = edge_voice or mapping.speech_confidence >= 0.10
        transcript = None
        events = [_confirmed_event(event) for event in mapping.events]
        if voice_detected and phrase_triggers:
            transcript_result = self.transcriber.transcribe_pcm16(pcm, sample_rate)
            if transcript_result is not None:
                transcript = transcript_result.text
                phrase_match = find_phrase_match(transcript_result, phrase_triggers)
                if phrase_match is not None:
                    events.append(
                        ConfirmedEvent(
                            event="name_called",
                            confidence=phrase_match.confidence,
                            source_label=f'phrase: "{phrase_match.phrase}"',
                            category="attention",
                            pattern="long_pulse",
                            requires_ack=False,
                        )
                    )

        total_ms = (time.perf_counter() - started) * 1_000
        top_predictions = tuple(
            {
                "label": prediction.label,
                "confidence": round(float(prediction.confidence), 4),
            }
            for prediction in predictions[:5]
        )
        return HubInferenceResult(
            events=tuple(events),
            voice_detected=voice_detected,
            speech_confidence=round(mapping.speech_confidence, 4),
            transcript=transcript,
            inference_ms=round(inference_ms, 2),
            total_ms=round(total_ms, 2),
            top_predictions=top_predictions,
        )


def _confirmed_event(event: MappedEvent) -> ConfirmedEvent:
    if event.event in {"fire_alarm", "siren"}:
        category, pattern, requires_ack = "emergency", "urgent_repeat", True
    elif event.event in {"car_horn", "doorbell_knock", "baby_crying"}:
        category, pattern, requires_ack = "attention", "long_pulse", False
    else:
        category, pattern, requires_ack = "informational", "two_short", False
    return ConfirmedEvent(
        event=event.event,
        confidence=round(event.confidence, 4),
        source_label=event.source_label,
        category=category,
        pattern=pattern,
        requires_ack=requires_ack,
    )
