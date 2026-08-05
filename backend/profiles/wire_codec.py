"""Validate the strict Android-to-hub profile synchronization schema."""

from __future__ import annotations

import math
from typing import Any

from backend.profiles.engine import (
    AlertProfile,
    CustomSoundPrototype,
    QuietHours,
    SoundRule,
)


_CATEGORIES = {"informational", "attention", "emergency"}
_PATTERNS = {"short_pulse", "two_short", "long_pulse", "urgent_repeat"}
_STRENGTHS = {"gentle", "standard", "strong"}


def decode_profile(document: dict[str, Any]) -> AlertProfile:
    profile_id = _required_text(document, "id", 80)
    name = _required_text(document, "name", 40)
    phrase_triggers = _text_list(document.get("phrase_triggers", []), 40, 20)
    quiet_document = document.get("quiet_hours", {})
    if not isinstance(quiet_document, dict):
        raise ValueError("quiet_hours must be an object")
    quiet_hours = QuietHours(
        enabled=bool(quiet_document.get("enabled", False)),
        start_minutes=_bounded_int(quiet_document.get("start_minutes", 22 * 60), 0, 1439),
        end_minutes=_bounded_int(quiet_document.get("end_minutes", 7 * 60), 0, 1439),
    )

    rules_document = document.get("sound_rules")
    if not isinstance(rules_document, list) or not rules_document:
        raise ValueError("sound_rules must be a non-empty list")
    rules: list[SoundRule] = []
    seen_events: set[str] = set()
    for item in rules_document:
        if not isinstance(item, dict):
            raise ValueError("Each sound rule must be an object")
        event = _required_text(item, "event", 100)
        if event in seen_events:
            raise ValueError(f"Duplicate sound rule: {event}")
        seen_events.add(event)
        category = _choice(item, "category", _CATEGORIES)
        pattern = _choice(item, "pattern", _PATTERNS)
        strength = _choice(item, "strength", _STRENGTHS)
        rules.append(
            SoundRule(
                event=event,
                enabled=bool(item.get("enabled", False)),
                confidence_threshold=_bounded_float(item.get("confidence_threshold"), 0.20, 0.98),
                category=category,
                pattern=pattern,
                strength=strength,
                requires_ack=bool(item.get("requires_ack", False)),
                cooldown_seconds=_bounded_int(item.get("cooldown_seconds", 20), 0, 120),
            )
        )

    custom_document = document.get("custom_sounds", [])
    if not isinstance(custom_document, list):
        raise ValueError("custom_sounds must be a list")
    custom_sounds: list[CustomSoundPrototype] = []
    for item in custom_document:
        if not isinstance(item, dict):
            raise ValueError("Each custom sound must be an object")
        event = _required_text(item, "event", 100)
        if not event.startswith("custom:") or event not in seen_events:
            raise ValueError("Custom sound must reference a custom sound rule")
        prototype_document = item.get("prototype")
        if not isinstance(prototype_document, list) or len(prototype_document) != 8:
            raise ValueError("Custom sound prototype must contain eight features")
        prototype = tuple(_bounded_float(value, 0.0, 1.0) for value in prototype_document)
        norm = math.sqrt(sum(value * value for value in prototype))
        if not 0.98 <= norm <= 1.02:
            raise ValueError("Custom sound prototype must be normalized")
        custom_sounds.append(
            CustomSoundPrototype(
                event=event,
                label=_required_text(item, "label", 40),
                prototype=prototype,
                similarity_threshold=_bounded_float(item.get("similarity_threshold"), 0.70, 0.98),
                matcher_version=_bounded_int(item.get("matcher_version", 1), 1, 1),
            )
        )

    return AlertProfile(
        profile_id=profile_id,
        name=name,
        phrase_triggers=phrase_triggers,
        quiet_hours=quiet_hours,
        sound_rules=tuple(rules),
        custom_sounds=tuple(custom_sounds),
    )


def _required_text(document: dict[str, Any], key: str, maximum: int) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{key} must be between 1 and {maximum} characters")
    return value.strip()


def _text_list(value: Any, maximum_length: int, maximum_items: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ValueError("phrase_triggers must be a bounded list")
    result = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(result) != len(value) or any(len(item) > maximum_length for item in result):
        raise ValueError("phrase_triggers contains an invalid phrase")
    return result


def _choice(document: dict[str, Any], key: str, choices: set[str]) -> str:
    value = document.get(key)
    if value not in choices:
        raise ValueError(f"{key} must be one of: {', '.join(sorted(choices))}")
    return value


def _bounded_float(value: Any, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric value")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"Value must be between {minimum} and {maximum}")
    return result


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Value must be an integer between {minimum} and {maximum}")
    return value
