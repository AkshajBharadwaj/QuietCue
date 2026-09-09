"""Backend equivalents of the Android built-in QuietCue profiles."""

from __future__ import annotations

from dataclasses import replace

from backend.profiles.engine import AlertProfile, QuietHours, SoundRule
from backend.profiles.speech_context import SpeechMode


EVENTS = (
    "fire_alarm",
    "doorbell_knock",
    "car_horn",
    "siren",
    "name_called",
    "baby_crying",
    "kitchen_timer",
    "phone_ringing",
)


def get_profile(profile_id: str) -> AlertProfile:
    try:
        return all_profiles()[profile_id]
    except KeyError as exc:
        choices = ", ".join(all_profiles())
        raise ValueError(f"Unknown profile {profile_id!r}; choose one of: {choices}") from exc


def all_profiles() -> dict[str, AlertProfile]:
    return {
        "home": _home(),
        "work": _work(),
        "driving": _driving(),
        "sleep": _sleep(),
        "emergency": _emergency(),
    }


def _home() -> AlertProfile:
    return _profile(
        "home",
        "Home",
        disabled={"car_horn"},
        thresholds={"doorbell_knock": 0.55, "baby_crying": 0.50},
    )


def _work() -> AlertProfile:
    return _profile(
        "work",
        "Work / School",
        disabled={"baby_crying", "kitchen_timer"},
        thresholds={"name_called": 0.48, "phone_ringing": 0.65},
        phrase_triggers=("front desk",),
        speech_mode=SpeechMode.ALWAYS_ON,
        overrides={"phone_ringing": {"category": "informational", "pattern": "short_pulse"}},
    )


def _driving() -> AlertProfile:
    return _profile(
        "driving",
        "Driving / Transit",
        disabled={"doorbell_knock", "baby_crying", "kitchen_timer", "phone_ringing"},
        thresholds={"car_horn": 0.42, "siren": 0.45},
        overrides={
            "car_horn": {
                "category": "emergency",
                "pattern": "urgent_repeat",
                "strength": "strong",
                "requires_ack": True,
                "cooldown_seconds": 8,
            }
        },
    )


def _sleep() -> AlertProfile:
    return _profile(
        "sleep",
        "Sleep / Night",
        disabled={"doorbell_knock", "car_horn", "kitchen_timer", "phone_ringing"},
        thresholds={"baby_crying": 0.42},
        quiet_hours=QuietHours(True, 22 * 60, 7 * 60),
        speech_mode=SpeechMode.OFF,
        overrides={
            "baby_crying": {
                "category": "emergency",
                "pattern": "urgent_repeat",
                "strength": "strong",
                "requires_ack": True,
            }
        },
    )


def _emergency() -> AlertProfile:
    critical = {"fire_alarm", "car_horn", "siren"}
    rules = tuple(
        replace(
            _base_rule(event),
            enabled=event in critical,
            confidence_threshold=0.35 if event in critical else 0.65,
            category="emergency" if event in critical else "attention",
            pattern="urgent_repeat" if event in critical else "long_pulse",
            strength="strong",
            requires_ack=event in critical,
            cooldown_seconds=5 if event in critical or event == "name_called" else 20,
        )
        for event in EVENTS
    )
    return AlertProfile("emergency", "Emergency", (), QuietHours(), rules)


def _profile(
    profile_id: str,
    name: str,
    *,
    disabled: set[str],
    thresholds: dict[str, float] | None = None,
    phrase_triggers: tuple[str, ...] = (),
    quiet_hours: QuietHours = QuietHours(),
    overrides: dict[str, dict[str, object]] | None = None,
    speech_mode: SpeechMode = SpeechMode.INHERIT,
) -> AlertProfile:
    thresholds = thresholds or {}
    overrides = overrides or {}
    rules: list[SoundRule] = []
    for event in EVENTS:
        rule = replace(
            _base_rule(event),
            enabled=event not in disabled,
            confidence_threshold=thresholds.get(event, _base_rule(event).confidence_threshold),
        )
        if event in overrides:
            rule = replace(rule, **overrides[event])
        rules.append(rule)
    return AlertProfile(
        profile_id,
        name,
        phrase_triggers,
        quiet_hours,
        tuple(rules),
        speech_mode=speech_mode,
    )


def _base_rule(event: str) -> SoundRule:
    emergency = event in {"fire_alarm", "siren"}
    return SoundRule(
        event=event,
        enabled=True,
        confidence_threshold=0.45 if emergency else 0.60,
        category="emergency" if emergency else "attention",
        pattern="urgent_repeat" if emergency else "long_pulse",
        strength="strong" if emergency else "standard",
        requires_ack=emergency,
        cooldown_seconds=_default_cooldown_seconds(event, emergency),
    )


def _default_cooldown_seconds(event: str, emergency: bool) -> int:
    # Someone calling your name twice in a row should register twice.
    if event == "name_called":
        return 5
    return 10 if emergency else 20
