from __future__ import annotations

import unittest

from backend.profiles.speech_context import KnownPerson, ManualContext, SpeechContext, UserIdentity
from backend.profiles.wire_codec import decode_profile


class SpeechContextTest(unittest.TestCase):
    def test_identity_people_and_manual_context_build_bounded_hints(self) -> None:
        context = SpeechContext(
            identity=UserIdentity("Akshaj", "Ak-shudge", ("Ak",), ("Hey oxides",)),
            people=(KnownPerson("Maya", "sister", "My-uh", ("May",), "visits on weekends"),),
            contexts=(ManualContext("Tuesday class", "Accessibility design in Building 4"),),
        )

        self.assertEqual(
            context.identity_triggers(),
            ("Akshaj", "Ak-shudge", "Ak", "Hey oxides"),
        )
        self.assertIn("Maya", context.hotwords())
        self.assertIn("Tuesday class", context.hotwords())
        self.assertIn("visits on weekends", context.prompt())
        self.assertLessEqual(len(context.prompt()), 800)

    def test_profile_sync_decodes_user_approved_context(self) -> None:
        profile = decode_profile(
            {
                "id": "home",
                "name": "Home",
                "phrase_triggers": [],
                "speech_context": {
                    "identity": {
                        "name": "Akshaj",
                        "pronunciation": "Ak-shudge",
                        "aliases": ["Ak"],
                        "recognition_phrases": ["Hey oxides"],
                    },
                    "people": [
                        {
                            "name": "Maya",
                            "relationship": "Sister",
                            "pronunciation": "My-uh",
                            "aliases": ["May"],
                            "notes": "Visits on weekends",
                        }
                    ],
                    "contexts": [
                        {"title": "Tuesday class", "details": "Building 4"},
                    ],
                },
                "sound_rules": [
                    {
                        "event": "name_called",
                        "enabled": True,
                        "confidence_threshold": 0.6,
                        "category": "attention",
                        "pattern": "long_pulse",
                        "strength": "standard",
                        "requires_ack": False,
                        "cooldown_seconds": 20,
                    }
                ],
            }
        )

        self.assertEqual(profile.speech_context.identity.name, "Akshaj")
        self.assertEqual(profile.speech_context.people[0].name, "Maya")
        self.assertEqual(profile.speech_context.contexts[0].details, "Building 4")

    def test_profile_without_context_remains_backward_compatible(self) -> None:
        profile = decode_profile(
            {
                "id": "home",
                "name": "Home",
                "sound_rules": [
                    {
                        "event": "fire_alarm",
                        "enabled": True,
                        "confidence_threshold": 0.5,
                        "category": "emergency",
                        "pattern": "urgent_repeat",
                        "strength": "strong",
                        "requires_ack": True,
                        "cooldown_seconds": 10,
                    }
                ],
            }
        )

        self.assertIsNone(profile.speech_context.identity)
        self.assertEqual(profile.speech_context.people, ())


if __name__ == "__main__":
    unittest.main()
