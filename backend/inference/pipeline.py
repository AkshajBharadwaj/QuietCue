"""Second-stage environmental and speech inference on a capable hub."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Protocol

from backend.inference.event_mapper import MappedEvent, map_predictions
from backend.inference.models import SoundPrediction
from backend.inference.speech import (
    BufferedSpeechRecognizer,
    SpeechTranscriber,
)


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
    speech_pending: bool
    speech_inference_ms: float | None
    speech_error: str | None
    inference_ms: float
    total_ms: float
    top_predictions: tuple[dict[str, object], ...]
    inference_source: str
    speech_diagnostics: dict[str, object] | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "events": [asdict(event) for event in self.events],
            "voice_detected": self.voice_detected,
            "speech_confidence": self.speech_confidence,
            # Transcripts are intentionally process-local. Only a configured
            # matched phrase may leave inference through an event source label.
            "transcript": None,
            "speech_pending": self.speech_pending,
            "speech_inference_ms": self.speech_inference_ms,
            "speech_error": self.speech_error,
            # Match score, ASR confidence, window length and rejection reason only.
            "speech_diagnostics": self.speech_diagnostics,
            "inference_ms": self.inference_ms,
            "total_ms": self.total_ms,
            "top_predictions": list(self.top_predictions),
            "inference_source": self.inference_source,
        }


class HubInferencePipeline:
    """Confirm edge candidates while keeping speech on a separate gated path."""

    def __init__(
        self,
        classifier: SoundClassifier,
        transcriber: SpeechTranscriber | None = None,
    ) -> None:
        self.classifier = classifier
        self.transcriber = transcriber
        self.speech_recognizer = BufferedSpeechRecognizer(transcriber) if transcriber else None

    def close(self) -> None:
        if self.speech_recognizer is not None:
            self.speech_recognizer.close()

    def reset_stream(self) -> None:
        if self.speech_recognizer is not None:
            self.speech_recognizer.reset()

    def process_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        edge_analysis: dict[str, object] | None = None,
        phrase_triggers: list[str] | None = None,
        speech_prompt: str = "",
        speech_hotwords: list[str] | None = None,
        speech_enabled: bool = True,
        speech_sensitivity: float = 0.6,
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

        edge_document = edge_analysis or {}
        edge_voice = bool(edge_document.get("voice_activity", False))
        edge_probability = edge_document.get("voice_probability", 0.0)
        if isinstance(edge_probability, bool) or not isinstance(edge_probability, (int, float)):
            edge_probability = 0.0
        speech_confidence = max(mapping.speech_confidence, float(edge_probability))
        voice_detected = edge_voice or speech_confidence >= 0.10
        transcript = None
        speech_pending = False
        speech_inference_ms = None
        speech_error = None
        speech_diagnostics = None
        events = [_confirmed_event(event) for event in mapping.events]
        if self.speech_recognizer is not None and speech_enabled:
            recognition, speech_pending = self.speech_recognizer.update(
                pcm,
                sample_rate,
                voice_detected,
                phrase_triggers or [],
                speech_prompt,
                speech_hotwords or [],
                speech_sensitivity,
            )
            if recognition is not None:
                speech_inference_ms = recognition.inference_ms
                speech_error = recognition.error
                if recognition.diagnostics is not None:
                    speech_diagnostics = recognition.diagnostics.to_wire()
                if recognition.transcript is not None:
                    transcript = recognition.transcript.text
                phrase_match = recognition.phrase_match
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
        elif self.speech_recognizer is not None:
            self.speech_recognizer.reset()

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
            speech_confidence=round(speech_confidence, 4),
            transcript=transcript,
            speech_pending=speech_pending,
            speech_inference_ms=speech_inference_ms,
            speech_error=speech_error,
            inference_ms=round(inference_ms, 2),
            total_ms=round(total_ms, 2),
            top_predictions=top_predictions,
            inference_source="connected_hub",
            speech_diagnostics=speech_diagnostics,
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
