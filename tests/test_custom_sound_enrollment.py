from __future__ import annotations

import math
import struct
import unittest

from backend.inference.custom_sound_matcher import CustomSoundMatcher, fingerprint_pcm16
from backend.profiles.engine import ProfileDecisionEngine
from backend.profiles.wire_codec import decode_profile


class CustomSoundEnrollmentTest(unittest.TestCase):
    def test_synced_prototype_matches_and_uses_profile_rule(self) -> None:
        pcm = _tone_pcm16(1_000)
        prototype, _ = fingerprint_pcm16(pcm, 16_000)
        profile = decode_profile(
            {
                "id": "custom-library",
                "name": "Library",
                "phrase_triggers": ["Akshaj"],
                "quiet_hours": {"enabled": False, "start_minutes": 1320, "end_minutes": 420},
                "sound_rules": [
                    {
                        "event": "custom:buzzer",
                        "enabled": True,
                        "confidence_threshold": 0.80,
                        "category": "attention",
                        "pattern": "long_pulse",
                        "strength": "standard",
                        "requires_ack": False,
                        "cooldown_seconds": 20,
                    }
                ],
                "custom_sounds": [
                    {
                        "event": "custom:buzzer",
                        "label": "Apartment buzzer",
                        "prototype": list(prototype),
                        "similarity_threshold": 0.80,
                        "matcher_version": 1,
                    }
                ],
            }
        )

        matches = CustomSoundMatcher(profile.custom_sounds).match_pcm16(pcm, 16_000)
        decisions = ProfileDecisionEngine(profile).decide(
            matches,
            captured_at_ms=1_000,
            source_sequence=0,
            now_ms=1_010,
        )

        self.assertEqual(matches[0].event, "custom:buzzer")
        self.assertEqual(decisions.alerts[0].profile_name, "Library")
        self.assertEqual(decisions.alerts[0].pattern, "long_pulse")

    def test_invalid_non_normalized_prototype_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "normalized"):
            decode_profile(
                {
                    "id": "profile",
                    "name": "Profile",
                    "sound_rules": [
                        {
                            "event": "custom:buzzer",
                            "enabled": True,
                            "confidence_threshold": 0.8,
                            "category": "attention",
                            "pattern": "long_pulse",
                            "strength": "standard",
                            "requires_ack": False,
                            "cooldown_seconds": 20,
                        }
                    ],
                    "custom_sounds": [
                        {
                            "event": "custom:buzzer",
                            "label": "Buzzer",
                            "prototype": [1.0] * 8,
                            "similarity_threshold": 0.8,
                        }
                    ],
                }
            )


def _tone_pcm16(frequency: int, seconds: float = 0.5) -> bytes:
    return b"".join(
        struct.pack("<h", round(12_000 * math.sin(2 * math.pi * frequency * index / 16_000)))
        for index in range(round(16_000 * seconds))
    )
