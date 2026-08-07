"""Apply the active QuietCue profile to confirmed sound events."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime

from backend.inference.pipeline import ConfirmedEvent
from backend.profiles.speech_context import SpeechContext, SpeechMode


@dataclass(frozen=True)
class QuietHours:
    enabled: bool = False
    start_minutes: int = 22 * 60
    end_minutes: int = 7 * 60


@dataclass(frozen=True)
class SoundRule:
    event: str
    enabled: bool
    confidence_threshold: float
    category: str
    pattern: str
    strength: str
    requires_ack: bool
    cooldown_seconds: int


@dataclass(frozen=True)
class CustomSoundPrototype:
    event: str
    label: str
    prototype: tuple[float, ...]
    similarity_threshold: float
    matcher_version: int = 1


@dataclass(frozen=True)
class ClassifierLabelRule:
    event: str
    label: str


@dataclass(frozen=True)
class AlertProfile:
    profile_id: str
    name: str
    phrase_triggers: tuple[str, ...]
    quiet_hours: QuietHours
    sound_rules: tuple[SoundRule, ...]
    custom_sounds: tuple[CustomSoundPrototype, ...] = ()
    classifier_label_rules: tuple[ClassifierLabelRule, ...] = ()
    speech_context: SpeechContext = SpeechContext()
    speech_mode: SpeechMode = SpeechMode.INHERIT

    def rule_for(self, event: str) -> SoundRule | None:
        return next((rule for rule in self.sound_rules if rule.event == event), None)

    def summary(self) -> dict[str, object]:
        return {"id": self.profile_id, "name": self.name}

    def speech_enabled(self) -> bool:
        return self.speech_mode is SpeechMode.ALWAYS_ON or (
            self.speech_mode is SpeechMode.INHERIT and self.speech_context.settings.enabled
        )


@dataclass(frozen=True)
class AlertCommand:
    event_id: str
    event: str
    category: str
    confidence: float
    pattern: str
    strength: str
    requires_ack: bool
    profile_id: str
    profile_name: str
    source_label: str
    source_sequence: int
    captured_at_ms: int
    issued_at_ms: int
    total_after_capture_ms: int
    simulated: bool = True
    fallback_to_phone: bool = False

    def to_wire(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SuppressedEvent:
    event: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class DecisionResult:
    alerts: tuple[AlertCommand, ...]
    suppressed: tuple[SuppressedEvent, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "alerts": [alert.to_wire() for alert in self.alerts],
            "suppressed": [asdict(event) for event in self.suppressed],
        }


class ProfileDecisionEngine:
    """Filter confirmed events using thresholds, quiet hours, and cooldowns."""

    def __init__(self, profile: AlertProfile) -> None:
        self.profile = profile
        self._last_alert_ms: dict[str, int] = {}

    def set_profile(self, profile: AlertProfile) -> None:
        self.profile = profile
        self._last_alert_ms.clear()

    def decide(
        self,
        events: tuple[ConfirmedEvent, ...],
        *,
        captured_at_ms: int,
        source_sequence: int,
        now_ms: int | None = None,
        local_datetime: datetime | None = None,
    ) -> DecisionResult:
        issued_at_ms = now_ms if now_ms is not None else int(time.time() * 1_000)
        local_time = local_datetime or datetime.now().astimezone()
        quiet_now = _is_quiet_time(self.profile.quiet_hours, local_time.hour * 60 + local_time.minute)
        alerts: list[AlertCommand] = []
        suppressed: list[SuppressedEvent] = []

        for event in events:
            rule = self.profile.rule_for(event.event)
            fallback_to_phone = rule is None
            if rule is None:
                rule = _phone_fallback_rule(event.event)
            reason = self._suppression_reason(
                event,
                rule,
                issued_at_ms,
                quiet_now and not fallback_to_phone,
            )
            if reason is not None:
                suppressed.append(SuppressedEvent(event.event, event.confidence, reason))
                continue
            assert rule is not None
            self._last_alert_ms[event.event] = issued_at_ms
            alerts.append(
                AlertCommand(
                    event_id=f"evt_{uuid.uuid4().hex}",
                    event=event.event,
                    category=rule.category,
                    confidence=event.confidence,
                    pattern=rule.pattern,
                    strength=rule.strength,
                    requires_ack=rule.requires_ack,
                    profile_id=self.profile.profile_id,
                    profile_name=self.profile.name,
                    source_label=event.source_label,
                    source_sequence=source_sequence,
                    captured_at_ms=captured_at_ms,
                    issued_at_ms=issued_at_ms,
                    total_after_capture_ms=max(0, issued_at_ms - captured_at_ms),
                    fallback_to_phone=fallback_to_phone,
                )
            )
        return DecisionResult(tuple(alerts), tuple(suppressed))

    def _suppression_reason(
        self,
        event: ConfirmedEvent,
        rule: SoundRule | None,
        now_ms: int,
        quiet_now: bool,
    ) -> str | None:
        if rule is None:
            return "unsupported_by_profile"
        if not rule.enabled:
            return "disabled_by_profile"
        if event.confidence < rule.confidence_threshold:
            return "below_confidence_threshold"
        if quiet_now and rule.category != "emergency":
            return "quiet_hours"
        last_alert_ms = self._last_alert_ms.get(event.event)
        if last_alert_ms is not None and now_ms - last_alert_ms < rule.cooldown_seconds * 1_000:
            return "cooldown"
        return None


def _is_quiet_time(quiet_hours: QuietHours, minute_of_day: int) -> bool:
    if not quiet_hours.enabled or quiet_hours.start_minutes == quiet_hours.end_minutes:
        return False
    if quiet_hours.start_minutes < quiet_hours.end_minutes:
        return quiet_hours.start_minutes <= minute_of_day < quiet_hours.end_minutes
    return minute_of_day >= quiet_hours.start_minutes or minute_of_day < quiet_hours.end_minutes


def _phone_fallback_rule(event: str) -> SoundRule:
    """Use one gentle, profile-independent cue for recognized unconfigured sounds."""
    return SoundRule(
        event=event,
        enabled=True,
        confidence_threshold=0.0,
        category="informational",
        pattern="two_short",
        strength="gentle",
        requires_ack=False,
        cooldown_seconds=30,
    )
