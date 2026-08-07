from __future__ import annotations

import math
import struct
import unittest

from backend.inference.custom_sound_matcher import (
    CustomSoundMatcher,
    fingerprint_pcm16,
    speech_confidence_from_predictions,
)
from backend.profiles.engine import CustomSoundPrototype, ProfileDecisionEngine
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

    def test_multiple_prototypes_match_the_strongest_variant(self) -> None:
        low_pcm = _tone_pcm16(250)
        high_pcm = _tone_pcm16(3_000)
        low_prototype, _ = fingerprint_pcm16(low_pcm, 16_000)
        high_prototype, _ = fingerprint_pcm16(high_pcm, 16_000)
        profile = decode_profile(
            {
                "id": "multi-sample",
                "name": "Multi sample",
                "sound_rules": [{
                    "event": "custom:buzzer", "enabled": True, "confidence_threshold": 0.8,
                    "category": "attention", "pattern": "long_pulse", "strength": "standard",
                    "requires_ack": False, "cooldown_seconds": 20,
                }],
                "custom_sounds": [{
                    "event": "custom:buzzer", "label": "Buzzer",
                    "prototype": list(low_prototype),
                    "prototypes": [list(low_prototype), list(high_prototype)],
                    "similarity_threshold": 0.8, "matcher_version": 2,
                }],
            }
        )

        matches = CustomSoundMatcher(profile.custom_sounds).match_pcm16(high_pcm, 16_000)

        self.assertEqual("custom:buzzer", matches[0].event)
        self.assertGreater(matches[0].confidence, 0.99)

    def test_more_than_thirty_prototypes_is_rejected(self) -> None:
        pcm = _tone_pcm16(1_000)
        prototype, _ = fingerprint_pcm16(pcm, 16_000)
        document = {
            "id": "bounded", "name": "Bounded",
            "sound_rules": [{
                "event": "custom:buzzer", "enabled": True, "confidence_threshold": 0.8,
                "category": "attention", "pattern": "long_pulse", "strength": "standard",
                "requires_ack": False, "cooldown_seconds": 20,
            }],
            "custom_sounds": [{
                "event": "custom:buzzer", "label": "Buzzer", "prototype": list(prototype),
                "prototypes": [list(prototype)] * 31, "similarity_threshold": 0.8,
            }],
        }

        with self.assertRaisesRegex(ValueError, "one and 30"):
            decode_profile(document)

    def test_speech_dominated_audio_cannot_trigger_an_enrolled_sound(self) -> None:
        pcm = _tone_pcm16(1_000)
        prototype, _ = fingerprint_pcm16(pcm, 16_000)
        profile = decode_profile(
            {
                "id": "speech-safe", "name": "Speech safe",
                "sound_rules": [{
                    "event": "custom:buzzer", "enabled": True, "confidence_threshold": 0.9,
                    "category": "attention", "pattern": "long_pulse", "strength": "standard",
                    "requires_ack": False, "cooldown_seconds": 20,
                }],
                "custom_sounds": [{
                    "event": "custom:buzzer", "label": "Buzzer",
                    "prototype": list(prototype), "prototypes": [list(prototype)] * 3,
                    "similarity_threshold": 0.9, "matcher_version": 3,
                }],
            }
        )

        matches = CustomSoundMatcher(profile.custom_sounds).match_pcm16(
            pcm,
            16_000,
            speech_confidence=0.2,
        )

        self.assertEqual((), matches)

    def test_new_matcher_rejects_a_candidate_supported_by_only_one_repeat(self) -> None:
        second = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        third = [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        centroid = [1 / math.sqrt(3)] * 3 + [0.0] * 5
        candidate = b"".join(struct.pack("<h", sample) for sample in _tone_samples(1_000))
        candidate_features, _ = fingerprint_pcm16(candidate, 16_000)
        enrolled = CustomSoundPrototype(
            event="custom:buzzer",
            label="Buzzer",
            prototype=tuple(centroid),
            similarity_threshold=0.9,
            matcher_version=4,
            prototypes=(candidate_features, tuple(second), tuple(third)),
        )

        self.assertEqual((), CustomSoundMatcher((enrolled,)).match_pcm16(candidate, 16_000))

    def test_speech_confidence_uses_explicit_speech_labels_only(self) -> None:
        confidence = speech_confidence_from_predictions(
            (
                {"label": "Speech", "confidence": 0.72},
                {"label": "Baby cry, infant cry", "confidence": 0.91},
            )
        )

        self.assertEqual(0.72, confidence)


def _tone_pcm16(frequency: int, seconds: float = 0.5) -> bytes:
    return b"".join(struct.pack("<h", sample) for sample in _tone_samples(frequency, seconds))


def _tone_samples(frequency: int, seconds: float = 0.5) -> list[int]:
    return [
        round(12_000 * math.sin(2 * math.pi * frequency * index / 16_000))
        for index in range(round(16_000 * seconds))
    ]
