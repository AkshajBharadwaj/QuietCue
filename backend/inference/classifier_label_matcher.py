"""Match user-approved classifier labels to custom QuietCue events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.inference.pipeline import ConfirmedEvent
from backend.profiles.engine import ClassifierLabelRule


class ClassifierLabelMatcher:
    """Convert exact model labels into events only after profile approval."""

    def __init__(self, rules: tuple[ClassifierLabelRule, ...] = ()) -> None:
        self._rules = rules

    def set_rules(self, rules: tuple[ClassifierLabelRule, ...]) -> None:
        self._rules = rules

    def match_predictions(
        self,
        predictions: Sequence[Mapping[str, object]],
    ) -> tuple[ConfirmedEvent, ...]:
        by_label: dict[str, tuple[str, float]] = {}
        for prediction in predictions:
            label_value = prediction.get("label")
            confidence_value = prediction.get("confidence")
            if not isinstance(label_value, str) or isinstance(confidence_value, bool):
                continue
            if not isinstance(confidence_value, (int, float)):
                continue
            normalized = _normalize(label_value)
            confidence = float(confidence_value)
            existing = by_label.get(normalized)
            if existing is None or confidence > existing[1]:
                by_label[normalized] = (label_value.strip(), confidence)

        strongest: dict[str, ConfirmedEvent] = {}
        for rule in self._rules:
            prediction = by_label.get(_normalize(rule.label))
            if prediction is None:
                continue
            source_label, confidence = prediction
            event = ConfirmedEvent(
                event=rule.event,
                confidence=round(confidence, 4),
                source_label=source_label,
                category="informational",
                pattern="two_short",
                requires_ack=False,
            )
            existing = strongest.get(rule.event)
            if existing is None or event.confidence > existing.confidence:
                strongest[rule.event] = event
        return tuple(sorted(strongest.values(), key=lambda item: item.confidence, reverse=True))


def _normalize(label: str) -> str:
    return " ".join(label.strip().casefold().split())
