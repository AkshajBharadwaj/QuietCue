from __future__ import annotations

import unittest

from backend.inference.pipeline import ConfirmedEvent
from backend.profiles.engine import ProfileDecisionEngine
from backend.profiles.wire_codec import decode_profile


def _custom_profile_document() -> dict[str, object]:
    return {
        "id": "custom-haptics",
        "name": "Custom haptics",
        "sound_rules": [
            {
                "event": "doorbell_knock",
                "enabled": True,
                "confidence_threshold": 0.6,
                "category": "attention",
                "pattern": "custom",
                "strength": "standard",
                "requires_ack": False,
                "cooldown_seconds": 20,
                "custom_pattern": {
                    "name": "Knock knock",
                    "steps": [
                        {"on_ms": 420, "off_ms": 180},
                        {"on_ms": 650, "off_ms": 200},
                    ],
                },
            }
        ],
    }


class CustomHapticProfileTest(unittest.TestCase):
    def test_touch_pattern_reaches_alert_wire_command(self) -> None:
        profile = decode_profile(_custom_profile_document())
        decisions = ProfileDecisionEngine(profile).decide(
            (ConfirmedEvent("doorbell_knock", 0.9, "Doorbell", "attention", "long_pulse", False),),
            captured_at_ms=1_000,
            source_sequence=4,
            now_ms=1_050,
        )

        alert = decisions.alerts[0].to_wire()
        self.assertEqual(alert["pattern"], "custom")
        self.assertEqual(alert["custom_pattern"], "420,180;650,200")

    def test_custom_pattern_requires_recorded_steps(self) -> None:
        document = _custom_profile_document()
        rule = document["sound_rules"][0]  # type: ignore[index]
        del rule["custom_pattern"]  # type: ignore[index]

        with self.assertRaisesRegex(ValueError, "custom_pattern"):
            decode_profile(document)

    def test_custom_pattern_rejects_out_of_bounds_timing(self) -> None:
        document = _custom_profile_document()
        rule = document["sound_rules"][0]  # type: ignore[index]
        custom = rule["custom_pattern"]  # type: ignore[index]
        custom["steps"][0]["on_ms"] = 99  # type: ignore[index]

        with self.assertRaisesRegex(ValueError, "between 100 and 2000"):
            decode_profile(document)

    def test_alarm_custom_pattern_is_not_replaced_by_emergency_default(self) -> None:
        document = _custom_profile_document()
        rule = document["sound_rules"][0]  # type: ignore[index]
        rule["event"] = "alarm"  # type: ignore[index]
        rule["category"] = "emergency"  # type: ignore[index]
        rule["strength"] = "strong"  # type: ignore[index]
        rule["requires_ack"] = True  # type: ignore[index]
        profile = decode_profile(document)

        decisions = ProfileDecisionEngine(profile).decide(
            (ConfirmedEvent("alarm", 0.95, "Fire alarm", "emergency", "urgent_repeat", True),),
            captured_at_ms=1_000,
            source_sequence=5,
            now_ms=1_050,
        )

        alert = decisions.alerts[0].to_wire()
        self.assertEqual("custom", alert["pattern"])
        self.assertEqual("420,180;650,200", alert["custom_pattern"])


if __name__ == "__main__":
    unittest.main()
