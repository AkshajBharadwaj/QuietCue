from __future__ import annotations

import unittest

from backend.profiles.speech_context import (
    KnownPerson,
    ManualContext,
    SpeechContext,
    SpeechMode,
    SpeechModel,
    SpeechSettings,
    UserIdentity,
)
from backend.profiles.wire_codec import decode_profile
from backend.app.hub_server import _bounded_phrase_triggers


class SpeechContextTest(unittest.TestCase):
    def test_identity_people_and_manual_context_build_bounded_hints(self) -> None:
        context = SpeechContext(
            identity=UserIdentity("Akshaj", "Ak-shudge", ("Ak",), ("Hey oxides",)),
            people=(KnownPerson("Maya", "sister", "My-uh", ("May",), "visits on weekends"),),
            contexts=(ManualContext("Tuesday class", "Accessibility design in Building 4"),),
        )

        self.assertEqual(
            context.identity_triggers(),
            ("Akshaj", "Ak", "Hey oxides"),
            "pronunciation guides are for people; Whisper never emits them",
        )
        self.assertIn("Maya", context.hotwords())
        self.assertIn("Tuesday class", context.hotwords())
        self.assertNotIn("Ak-shudge", context.hotwords())
        self.assertNotIn("My-uh", context.hotwords())
        prompt = context.prompt()
        self.assertTrue(prompt.startswith("Akshaj. Hey Akshaj. Ak. Maya. May."), prompt)
        self.assertNotIn("visits on weekends", prompt, "prose context invites hallucination; only spoken forms")
        self.assertNotIn("The user's name", prompt)
        self.assertLessEqual(len(prompt), 400)

    def test_prompt_is_bounded_at_a_word_boundary(self) -> None:
        context = SpeechContext(
            people=tuple(KnownPerson(f"Person{index:03d}") for index in range(80)),
        )
        prompt = context.prompt()
        self.assertLessEqual(len(prompt), 400)
        self.assertTrue(prompt.endswith("."), prompt[-20:])

    def test_small_model_choice_is_accepted(self) -> None:
        profile = decode_profile(
            {
                "id": "home",
                "name": "Home",
                "speech_context": {"settings": {"model": "small_en"}},
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
        self.assertEqual(profile.speech_context.settings.model, SpeechModel.SMALL_EN)

    def test_profile_sync_decodes_user_approved_context(self) -> None:
        profile = decode_profile(
            {
                "id": "home",
                "name": "Home",
                "phrase_triggers": [],
                "speech_context": {
                    "settings": {
                        "enabled": True,
                        "model": "base_en",
                        "sensitivity": 0.72,
                        "listen_for_identity": True,
                        "listen_for_people": True,
                        "global_phrases": ["front desk"],
                    },
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
                "speech_mode": "always_on",
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
        self.assertEqual(profile.speech_context.settings.model, SpeechModel.BASE_EN)
        self.assertEqual(profile.speech_context.settings.sensitivity, 0.72)
        self.assertEqual(profile.speech_mode, SpeechMode.ALWAYS_ON)
        self.assertIn("Maya", profile.speech_context.trigger_phrases(profile.phrase_triggers))
        self.assertIn("front desk", profile.speech_context.trigger_phrases())

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
        self.assertEqual(profile.speech_context.settings, SpeechSettings())
        self.assertEqual(profile.speech_mode, SpeechMode.INHERIT)

    def test_people_are_hotwords_but_not_triggers_until_enabled(self) -> None:
        context = SpeechContext(
            identity=UserIdentity("Rohan", aliases=("Ro",)),
            people=(KnownPerson("Maya", aliases=("May",)),),
        )

        self.assertIn("Maya", context.hotwords())
        self.assertNotIn("Maya", context.trigger_phrases())
        enabled = SpeechContext(
            identity=context.identity,
            people=context.people,
            settings=SpeechSettings(listen_for_people=True),
        )
        self.assertIn("Maya", enabled.trigger_phrases())
        self.assertIn("May", enabled.trigger_phrases())

    def test_invalid_speech_settings_are_rejected(self) -> None:
        base = {
            "id": "home",
            "name": "Home",
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
        for settings in (
            {"sensitivity": 0.2},
            {"model": "large_en"},
            {"enabled": "yes"},
        ):
            with self.subTest(settings=settings):
                document = {**base, "speech_context": {"settings": settings}}
                with self.assertRaises(ValueError):
                    decode_profile(document)

    def test_runtime_phrase_triggers_are_bounded_and_trimmed(self) -> None:
        self.assertEqual(_bounded_phrase_triggers(["  front desk  "]), ["front desk"])
        invalid_values = (
            [""],
            ["x" * 41],
            [1],
            ["phrase"] * 21,
            "phrase",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _bounded_phrase_triggers(value)


if __name__ == "__main__":
    unittest.main()
