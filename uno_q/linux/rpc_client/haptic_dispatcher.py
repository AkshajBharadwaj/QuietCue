"""Dispatch hub alert commands to the STM32 haptic firmware over Arduino RPC.

The hub answers every audio chunk with a ``detection_result`` message whose
``alerts`` list contains profile-approved alert commands. This module turns
those commands into the semantic RPC calls the STM32 firmware exposes —
``play_haptic``, ``stop_haptic``, ``set_status_led``, ``get_button_state`` —
while protecting the wearer from duplicate buzzing after reconnects or
repeated detections. The dispatcher never makes safety decisions of its own;
it only rate-limits delivery of decisions the hub already made.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Protocol


DEFAULT_COOLDOWN_SECONDS = 10.0
"""Minimum spacing between deliveries of the same non-emergency event."""

EMERGENCY_COOLDOWN_SECONDS = 2.0
"""Emergency events use a much shorter cooldown so they stay persistent."""

URGENT_REPEAT_UNTIL_STOPPED = 0
"""A repeat count of zero asks the firmware to repeat until stop or timeout."""

_SEEN_EVENT_ID_LIMIT = 256


class HapticTransport(Protocol):
    """RPC surface the STM32 firmware exposes through the Arduino bridge."""

    def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> None: ...

    def stop_haptic(self) -> None: ...

    def get_button_state(self) -> bool: ...

    def set_status_led(self, state: str) -> None: ...

    def health_check(self) -> bool: ...


@dataclass(frozen=True)
class PatternPlan:
    """Concrete motor plan for one alert category."""

    pattern: str
    intensity: int
    repeat_count: int
    led_state: str


_CATEGORY_PLANS: dict[str, PatternPlan] = {
    "emergency": PatternPlan("urgent_repeat", 100, URGENT_REPEAT_UNTIL_STOPPED, "emergency"),
    "attention": PatternPlan("long_pulse", 80, 1, "attention"),
    "informational": PatternPlan("two_short", 60, 1, "notice"),
}

_FALLBACK_PLAN = _CATEGORY_PLANS["informational"]


@dataclass(frozen=True)
class DispatchOutcome:
    """Result of attempting to deliver one alert to the haptic hardware."""

    event: str
    delivered: bool
    reason: str
    pattern: str

    def to_wire(self) -> dict[str, object]:
        return {
            "event": self.event,
            "delivered": self.delivered,
            "reason": self.reason,
            "pattern": self.pattern,
        }


class AlertDispatcher:
    """Deliver hub alert commands to a haptic transport with dedup and cooldowns.

    Alerts are accepted as dictionaries carrying at least the confirmed-event
    fields (``event``, ``category``, ``pattern``, ``requires_ack``); the richer
    hub ``AlertCommand`` wire shape is a superset and is used when present
    (``event_id`` enables exact replay suppression after a reconnect).
    """

    def __init__(
        self,
        transport: HapticTransport,
        *,
        default_cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
        emergency_cooldown_seconds: float = EMERGENCY_COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._transport = transport
        self._default_cooldown = default_cooldown_seconds
        self._emergency_cooldown = emergency_cooldown_seconds
        self._clock = clock
        self._last_delivered: dict[str, float] = {}
        self._seen_event_ids: OrderedDict[str, None] = OrderedDict()
        self._pending_ack_event: str | None = None
        self._delivered_count = 0
        self._suppressed_count = 0
        self._last_transport_error: str | None = None
        self._last_delivered_event: str | None = None

    def handle_detection_result(self, body: dict[str, object]) -> list[DispatchOutcome]:
        """Dispatch every alert in one hub ``detection_result`` body."""
        alerts = body.get("alerts", [])
        if not isinstance(alerts, list):
            return []
        return [self.dispatch(alert) for alert in alerts if isinstance(alert, dict)]

    def dispatch(self, alert: dict[str, object]) -> DispatchOutcome:
        """Deliver one alert unless dedup or cooldown rules suppress it."""
        event = str(alert.get("event", "")) or "unknown"
        category = str(alert.get("category", "")) or "informational"
        plan = self._plan_for(alert, category)

        event_id = alert.get("event_id")
        if isinstance(event_id, str) and event_id:
            if event_id in self._seen_event_ids:
                self._suppressed_count += 1
                return DispatchOutcome(event, False, "duplicate_event_id", plan.pattern)
            self._remember_event_id(event_id)

        now = self._clock()
        cooldown = self._emergency_cooldown if category == "emergency" else self._default_cooldown
        last = self._last_delivered.get(event)
        if last is not None and (now - last) < cooldown:
            self._suppressed_count += 1
            return DispatchOutcome(event, False, "cooldown_active", plan.pattern)

        try:
            self._transport.set_status_led(plan.led_state)
            self._transport.play_haptic(plan.pattern, plan.intensity, plan.repeat_count)
        except Exception as exc:  # noqa: BLE001 - hardware faults must not kill the stream loop.
            self._last_transport_error = f"{type(exc).__name__}: {exc}"
            return DispatchOutcome(event, False, "transport_error", plan.pattern)

        self._last_transport_error = None
        self._last_delivered[event] = now
        self._last_delivered_event = event
        self._delivered_count += 1
        if bool(alert.get("requires_ack", False)):
            self._pending_ack_event = event
        return DispatchOutcome(event, True, "delivered", plan.pattern)

    def poll_acknowledge(self) -> bool:
        """Stop a pending acknowledgeable pattern once the button is pressed."""
        if self._pending_ack_event is None:
            return False
        try:
            pressed = bool(self._transport.get_button_state())
            if not pressed:
                return False
            self._transport.stop_haptic()
            self._transport.set_status_led("idle")
        except Exception as exc:  # noqa: BLE001 - hardware faults must not kill the stream loop.
            self._last_transport_error = f"{type(exc).__name__}: {exc}"
            return False
        self._pending_ack_event = None
        return True

    def health_snapshot(self) -> dict[str, object]:
        """Summarize dispatcher and transport health for hub-side reporting."""
        try:
            transport_healthy = bool(self._transport.health_check())
        except Exception as exc:  # noqa: BLE001 - a dead bridge is a report, not a crash.
            self._last_transport_error = f"{type(exc).__name__}: {exc}"
            transport_healthy = False
        return {
            "transport_healthy": transport_healthy,
            "delivered": self._delivered_count,
            "suppressed": self._suppressed_count,
            "pending_ack_event": self._pending_ack_event,
            "last_delivered_event": self._last_delivered_event,
            "last_transport_error": self._last_transport_error,
        }

    def _plan_for(self, alert: dict[str, object], category: str) -> PatternPlan:
        plan = _CATEGORY_PLANS.get(category, _FALLBACK_PLAN)
        pattern = alert.get("pattern")
        if isinstance(pattern, str) and pattern:
            return PatternPlan(pattern, plan.intensity, plan.repeat_count, plan.led_state)
        return plan

    def _remember_event_id(self, event_id: str) -> None:
        self._seen_event_ids[event_id] = None
        while len(self._seen_event_ids) > _SEEN_EVENT_ID_LIMIT:
            self._seen_event_ids.popitem(last=False)


class ConsoleHapticTransport:
    """Development transport that prints each RPC call instead of driving hardware."""

    def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> None:
        print(f"RPC play_haptic(pattern={pattern!r}, intensity={intensity}, repeat_count={repeat_count})")

    def stop_haptic(self) -> None:
        print("RPC stop_haptic()")

    def get_button_state(self) -> bool:
        return False

    def set_status_led(self, state: str) -> None:
        print(f"RPC set_status_led(state={state!r})")

    def health_check(self) -> bool:
        return True
