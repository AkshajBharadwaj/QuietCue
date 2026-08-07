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

    def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> bool | None: ...

    def play_custom_haptic(
        self, encoded_steps: str, intensity: int, repeat_count: int
    ) -> bool | None: ...

    def stop_haptic(self) -> bool | None: ...

    def get_button_state(self) -> bool: ...

    def set_status_led(self, state: bool) -> bool | None: ...

    def health_check(self) -> bool: ...


@dataclass(frozen=True)
class PatternPlan:
    """Concrete motor plan for one alert category."""

    pattern: str
    intensity: int
    repeat_count: int
    custom_pattern: str = ""


_CATEGORY_PLANS: dict[str, PatternPlan] = {
    "emergency": PatternPlan("urgent_repeat", 255, URGENT_REPEAT_UNTIL_STOPPED),
    "attention": PatternPlan("long_pulse", 230, 1),
    "informational": PatternPlan("two_short", 190, 1),
}

_FALLBACK_PLAN = _CATEGORY_PLANS["informational"]

_STRENGTH_INTENSITIES = {
    "gentle": 190,
    "standard": 230,
    "strong": 255,
}


@dataclass(frozen=True)
class DispatchOutcome:
    """Result of attempting to deliver one alert to the haptic hardware."""

    event: str
    delivered: bool
    reason: str
    pattern: str
    event_id: str = ""

    def to_wire(self) -> dict[str, object]:
        return {
            "event": self.event,
            "delivered": self.delivered,
            "reason": self.reason,
            "pattern": self.pattern,
            "event_id": self.event_id,
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
        """Dispatch alerts, then apply controls so a remote stop wins any race."""
        alerts = body.get("alerts", [])
        outcomes = (
            [self.dispatch(alert) for alert in alerts if isinstance(alert, dict)]
            if isinstance(alerts, list)
            else []
        )
        commands = body.get("control_commands", [])
        if isinstance(commands, list):
            for command in commands:
                if isinstance(command, dict) and command.get("command") == "stop_haptic":
                    self.stop_haptic()
        return outcomes

    def stop_haptic(self) -> bool:
        """Stop the motor through RPC for either app or hardware-button acknowledgement."""
        try:
            stopped = self._transport.stop_haptic()
            if stopped is False:
                raise RuntimeError("firmware refused stop_haptic")
            try:
                self._transport.set_status_led(False)
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001 - hardware faults must not kill the stream loop.
            self._last_transport_error = f"{type(exc).__name__}: {exc}"
            return False
        self._last_transport_error = None
        self._pending_ack_event = None
        return True

    def dispatch(self, alert: dict[str, object]) -> DispatchOutcome:
        """Deliver one alert unless dedup or cooldown rules suppress it."""
        event = str(alert.get("event", "")) or "unknown"
        category = str(alert.get("category", "")) or "informational"
        plan = self._plan_for(alert, category)

        event_id_value = alert.get("event_id")
        event_id = event_id_value if isinstance(event_id_value, str) else ""
        if event_id:
            if event_id in self._seen_event_ids:
                self._suppressed_count += 1
                return DispatchOutcome(event, False, "duplicate_event_id", plan.pattern, event_id)

        now = self._clock()
        cooldown = self._emergency_cooldown if category == "emergency" else self._default_cooldown
        last = self._last_delivered.get(event)
        if last is not None and (now - last) < cooldown:
            self._suppressed_count += 1
            return DispatchOutcome(event, False, "cooldown_active", plan.pattern, event_id)

        try:
            if plan.pattern == "custom":
                if not plan.custom_pattern:
                    raise ValueError("custom pattern has no recorded steps")
                # The STM32 correctly refuses to let an arbitrary custom cue
                # interrupt an active emergency pattern. A profile edit can,
                # however, replace the cue for that *same* acknowledged event
                # while urgent_repeat is still running. Stop only that stale
                # same-event cue before asking the firmware to play its newly
                # selected custom replacement.
                if self._pending_ack_event == event:
                    stopped = self._transport.stop_haptic()
                    if stopped is False:
                        raise RuntimeError("firmware refused to stop the previous same-event pattern")
                    self._pending_ack_event = None
                accepted = self._transport.play_custom_haptic(
                    plan.custom_pattern,
                    plan.intensity,
                    plan.repeat_count,
                )
            else:
                accepted = self._transport.play_haptic(
                    plan.pattern,
                    plan.intensity,
                    plan.repeat_count,
                )
            if accepted is False:
                raise RuntimeError(f"firmware refused pattern {plan.pattern!r}")
        except Exception as exc:  # noqa: BLE001 - hardware faults must not kill the stream loop.
            self._last_transport_error = f"{type(exc).__name__}: {exc}"
            return DispatchOutcome(event, False, "transport_error", plan.pattern, event_id)

        self._last_transport_error = None
        self._last_delivered[event] = now
        self._last_delivered_event = event
        self._delivered_count += 1
        if event_id:
            self._remember_event_id(event_id)
        if bool(alert.get("requires_ack", False)):
            self._pending_ack_event = event
        return DispatchOutcome(event, True, "delivered", plan.pattern, event_id)

    def poll_acknowledge(self) -> bool:
        """Stop a pending acknowledgeable pattern once the button is pressed."""
        if self._pending_ack_event is None:
            return False
        try:
            pressed = bool(self._transport.get_button_state())
            if not pressed:
                return False
            return self.stop_haptic()
        except Exception as exc:  # noqa: BLE001 - hardware faults must not kill the stream loop.
            self._last_transport_error = f"{type(exc).__name__}: {exc}"
            return False

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
        strength = alert.get("strength")
        intensity = (
            _STRENGTH_INTENSITIES.get(strength, plan.intensity)
            if isinstance(strength, str)
            else plan.intensity
        )
        pattern = alert.get("pattern")
        if isinstance(pattern, str) and pattern:
            custom_pattern = alert.get("custom_pattern")
            return PatternPlan(
                pattern,
                intensity,
                plan.repeat_count,
                custom_pattern if isinstance(custom_pattern, str) else "",
            )
        return PatternPlan(plan.pattern, intensity, plan.repeat_count)

    def _remember_event_id(self, event_id: str) -> None:
        self._seen_event_ids[event_id] = None
        while len(self._seen_event_ids) > _SEEN_EVENT_ID_LIMIT:
            self._seen_event_ids.popitem(last=False)


class ConsoleHapticTransport:
    """Development transport that prints each RPC call instead of driving hardware."""

    def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> bool:
        print(f"RPC play_haptic(pattern={pattern!r}, intensity={intensity}, repeat_count={repeat_count})")
        return True

    def play_custom_haptic(self, encoded_steps: str, intensity: int, repeat_count: int) -> bool:
        print(
            "RPC play_custom_haptic("
            f"encoded_steps={encoded_steps!r}, intensity={intensity}, repeat_count={repeat_count})"
        )
        return True

    def stop_haptic(self) -> bool:
        print("RPC stop_haptic()")
        return True

    def get_button_state(self) -> bool:
        return False

    def set_status_led(self, state: bool) -> bool:
        print(f"RPC set_status_led(state={state!r})")
        return True

    def health_check(self) -> bool:
        return True
