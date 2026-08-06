from __future__ import annotations

import unittest

from backend.inference.classifier_label_matcher import ClassifierLabelMatcher
from backend.profiles.engine import ProfileDecisionEngine
from backend.profiles.wire_codec import decode_profile


class ClassifierLabelMatcherTest(unittest.TestCase):
    def test_approved_label_matches_and_uses_profile_rule(self) -> None:
        profile = decode_profile(
            {
                "id": "home",
                "name": "Home",
                "sound_rules": [
                    {
                        "event": "custom:vacuum",
                        "enabled": True,
                        "confidence_threshold": 0.60,
                        "category": "informational",
                        "pattern": "two_short",
                        "strength": "gentle",
                        "requires_ack": False,
                        "cooldown_seconds": 30,
                    }
                ],
                "classifier_label_rules": [
                    {"event": "custom:vacuum", "label": "Vacuum cleaner"}
                ],
            }
        )

        events = ClassifierLabelMatcher(profile.classifier_label_rules).match_predictions(
            ({"label": "vacuum CLEANER", "confidence": 0.84},)
        )
        decisions = ProfileDecisionEngine(profile).decide(
            events,
            captured_at_ms=1_000,
            source_sequence=4,
            now_ms=1_010,
        )

        self.assertEqual(events[0].event, "custom:vacuum")
        self.assertEqual(decisions.alerts[0].pattern, "two_short")
        self.assertEqual(decisions.alerts[0].strength, "gentle")
        self.assertFalse(decisions.alerts[0].fallback_to_phone)

    def test_unapproved_label_does_not_match(self) -> None:
        matcher = ClassifierLabelMatcher()

        self.assertEqual(
            matcher.match_predictions(({"label": "Vacuum cleaner", "confidence": 0.90},)),
            (),
        )

    def test_label_rule_must_reference_a_custom_sound_rule(self) -> None:
        with self.assertRaisesRegex(ValueError, "custom sound rule"):
            decode_profile(
                {
                    "id": "home",
                    "name": "Home",
                    "sound_rules": [
                        {
                            "event": "fire_alarm",
                            "enabled": True,
                            "confidence_threshold": 0.45,
                            "category": "emergency",
                            "pattern": "urgent_repeat",
                            "strength": "strong",
                            "requires_ack": True,
                            "cooldown_seconds": 10,
                        }
                    ],
                    "classifier_label_rules": [
                        {"event": "fire_alarm", "label": "Vacuum cleaner"}
                    ],
                }
            )
