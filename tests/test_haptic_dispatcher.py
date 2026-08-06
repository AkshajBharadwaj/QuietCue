from __future__ import annotations

import unittest

from uno_q.linux.rpc_client import AlertDispatcher


class FakeHapticTransport:
    """Records every RPC call so tests can assert on the exact sequence."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.button_pressed = False
        self.healthy = True

    def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> None:
        self.calls.append(("play_haptic", pattern, intensity, repeat_count))

    def stop_haptic(self) -> None:
        self.calls.append(("stop_haptic",))

    def get_button_state(self) -> bool:
        return self.button_pressed

    def set_status_led(self, state: str) -> None:
        self.calls.append(("set_status_led", state))

    def health_check(self) -> bool:
        return self.healthy


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def _alert(
    event: str = "doorbell_knock",
    category: str = "attention",
    pattern: str = "long_pulse",
    requires_ack: bool = False,
    event_id: str | None = None,
) -> dict[str, object]:
    alert: dict[str, object] = {
        "event": event,
        "category": category,
        "pattern": pattern,
        "confidence": 0.9,
        "requires_ack": requires_ack,
    }
    if event_id is not None:
        alert["event_id"] = event_id
    return alert


class AlertDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeHapticTransport()
        self.clock = FakeClock()
        self.dispatcher = AlertDispatcher(self.transport, clock=self.clock)

    def test_emergency_alert_maps_to_urgent_repeat_at_full_intensity(self) -> None:
        outcome = self.dispatcher.dispatch(
            _alert(event="fire_alarm", category="emergency", pattern="urgent_repeat", requires_ack=True)
        )

        self.assertTrue(outcome.delivered)
        self.assertIn(("play_haptic", "urgent_repeat", 100, 0), self.transport.calls)
        self.assertIn(("set_status_led", "emergency"), self.transport.calls)

    def test_informational_alert_uses_two_short_at_reduced_intensity(self) -> None:
        outcome = self.dispatcher.dispatch(
            _alert(event="kitchen_timer", category="informational", pattern="two_short")
        )

        self.assertTrue(outcome.delivered)
        self.assertIn(("play_haptic", "two_short", 60, 1), self.transport.calls)

    def test_unknown_category_falls_back_to_informational_plan(self) -> None:
        outcome = self.dispatcher.dispatch(_alert(category="mystery", pattern="long_pulse"))

        self.assertTrue(outcome.delivered)
        self.assertIn(("play_haptic", "long_pulse", 60, 1), self.transport.calls)

    def test_repeated_event_within_cooldown_is_suppressed(self) -> None:
        first = self.dispatcher.dispatch(_alert())
        self.clock.advance(3.0)
        second = self.dispatcher.dispatch(_alert())

        self.assertTrue(first.delivered)
        self.assertFalse(second.delivered)
        self.assertEqual(second.reason, "cooldown_active")

    def test_repeated_event_after_cooldown_is_delivered_again(self) -> None:
        self.dispatcher.dispatch(_alert())
        self.clock.advance(11.0)
        second = self.dispatcher.dispatch(_alert())

        self.assertTrue(second.delivered)

    def test_emergency_repeat_is_not_suppressed_by_the_default_cooldown(self) -> None:
        alarm = _alert(event="fire_alarm", category="emergency", pattern="urgent_repeat")
        first = self.dispatcher.dispatch(alarm)
        self.clock.advance(3.0)
        second = self.dispatcher.dispatch(alarm)

        self.assertTrue(first.delivered)
        self.assertTrue(second.delivered)

    def test_duplicate_event_id_is_never_replayed(self) -> None:
        alarm = _alert(event="fire_alarm", category="emergency", event_id="evt_01")
        first = self.dispatcher.dispatch(alarm)
        self.clock.advance(60.0)
        replay = self.dispatcher.dispatch(alarm)

        self.assertTrue(first.delivered)
        self.assertFalse(replay.delivered)
        self.assertEqual(replay.reason, "duplicate_event_id")

    def test_handle_detection_result_dispatches_each_alert(self) -> None:
        outcomes = self.dispatcher.handle_detection_result(
            {
                "alerts": [
                    _alert(event="fire_alarm", category="emergency", pattern="urgent_repeat"),
                    _alert(event="doorbell_knock"),
                ]
            }
        )

        self.assertEqual([outcome.delivered for outcome in outcomes], [True, True])

    def test_handle_detection_result_ignores_missing_or_malformed_alerts(self) -> None:
        self.assertEqual(self.dispatcher.handle_detection_result({}), [])
        self.assertEqual(self.dispatcher.handle_detection_result({"alerts": "nope"}), [])

    def test_acknowledge_button_stops_a_pending_pattern(self) -> None:
        self.dispatcher.dispatch(
            _alert(event="fire_alarm", category="emergency", pattern="urgent_repeat", requires_ack=True)
        )
        self.assertFalse(self.dispatcher.poll_acknowledge())

        self.transport.button_pressed = True
        self.assertTrue(self.dispatcher.poll_acknowledge())
        self.assertIn(("stop_haptic",), self.transport.calls)
        self.assertIn(("set_status_led", "idle"), self.transport.calls)
        self.assertFalse(self.dispatcher.poll_acknowledge())

    def test_transport_failure_is_reported_not_raised(self) -> None:
        class BrokenTransport(FakeHapticTransport):
            def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> None:
                raise ConnectionError("bridge offline")

        dispatcher = AlertDispatcher(BrokenTransport(), clock=self.clock)
        outcome = dispatcher.dispatch(_alert())

        self.assertFalse(outcome.delivered)
        self.assertEqual(outcome.reason, "transport_error")
        self.assertIn("bridge offline", str(dispatcher.health_snapshot()["last_transport_error"]))

    def test_health_snapshot_counts_deliveries_and_suppressions(self) -> None:
        self.dispatcher.dispatch(_alert())
        self.dispatcher.dispatch(_alert())

        snapshot = self.dispatcher.health_snapshot()
        self.assertTrue(snapshot["transport_healthy"])
        self.assertEqual(snapshot["delivered"], 1)
        self.assertEqual(snapshot["suppressed"], 1)
        self.assertEqual(snapshot["last_delivered_event"], "doorbell_knock")


if __name__ == "__main__":
    unittest.main()
