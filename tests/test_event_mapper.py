"""Tests for the AudioSet label to QuietCue event mapper and the sound catalog."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path

from backend.inference.event_mapper import map_predictions
from backend.inference.sound_catalog import (
    CATALOG,
    EVENT_IDS,
    LEGACY_EVENT_ALIASES,
    canonical_event,
    default_category,
)


@dataclass(frozen=True)
class _Prediction:
    label: str
    confidence: float


def _events(*predictions: tuple[str, float]) -> dict[str, tuple[float, str]]:
    result = map_predictions([_Prediction(label, confidence) for label, confidence in predictions])
    return {event.event: (event.confidence, event.source_label) for event in result.events}


class EventMapperTests(unittest.TestCase):
    def test_specific_labels_match_as_substrings(self) -> None:
        events = _events(
            ("Police car (siren)", 0.4),
            ("Smoke detector, smoke alarm", 0.5),
            ("Telephone bell ringing", 0.2),
        )
        self.assertEqual(events["siren"], (0.4, "Police car (siren)"))
        self.assertEqual(events["alarm"], (0.5, "Smoke detector, smoke alarm"))
        self.assertEqual(events["phone_ringing"], (0.2, "Telephone bell ringing"))

    def test_generic_parent_labels_map_above_their_floor(self) -> None:
        events = _events(
            ("Telephone", 0.35),
            ("Alarm", 0.6),
            ("Door", 0.31),
            ("Buzzer", 0.45),
            ("Beep, bleep", 0.5),
            ("Whimper", 0.33),
        )
        self.assertEqual(events["phone_ringing"], (0.35, "Telephone"))
        self.assertEqual(events["alarm"], (0.6, "Alarm"))
        self.assertEqual(events["doorbell_knock"], (0.31, "Door"))
        self.assertEqual(events["appliance_beep"], (0.5, "Beep, bleep"))
        self.assertEqual(events["baby_crying"], (0.33, "Whimper"))

    def test_alarm_catches_every_alarm_like_label(self) -> None:
        # Sirens, alarm clocks and phone rings all made YAMNet say "Alarm" on
        # real clips; one Alarm option is meant to catch all of them.
        for label in ("Fire alarm", "Smoke detector, smoke alarm", "Alarm clock", "Alarm", "Buzzer"):
            self.assertIn("alarm", _events((label, 0.5)), label)

    def test_generic_labels_below_floor_are_ignored(self) -> None:
        events = _events(("Telephone", 0.29), ("Alarm", 0.2), ("Door", 0.15))
        self.assertEqual(events, {})

    def test_generic_terms_require_the_exact_label(self) -> None:
        # "Car alarm", "Whimper (dog)" and "Sliding door" contain generic terms but are not the parent label.
        events = _events(("Car alarm", 0.9), ("Whimper (dog)", 0.9), ("Sliding door", 0.9), ("Bicycle bell", 0.9))
        self.assertNotIn("alarm", events)
        self.assertNotIn("baby_crying", events)
        self.assertNotIn("doorbell_knock", events)
        self.assertNotIn("bell", events)

    def test_excluded_substrings_do_not_count(self) -> None:
        # A washing machine scored "Engine knocking" 0.23; it is not a knock.
        self.assertEqual(_events(("Engine knocking", 0.9)), {})

    def test_emergency_vehicle_no_longer_counts_as_a_siren(self) -> None:
        # Two of five plain car-horn clips scored "Emergency vehicle" 0.64-0.70.
        events = _events(("Emergency vehicle", 0.9))
        self.assertNotIn("siren", events)

    def test_new_catalog_sounds_map_from_their_labels(self) -> None:
        events = _events(
            ("Bark", 0.9),
            ("Meow", 0.8),
            ("Shatter", 0.7),
            ("Fireworks", 0.6),
            ("Church bell", 0.5),
            ("Thunderstorm", 0.4),
            ("Train horn", 0.45),
            ("Applause", 0.35),
            ("Throat clearing", 0.3),
            ("Toilet flush", 0.25),
            ("Computer keyboard", 0.2),
            ("Snoring", 0.15),
            ("Chainsaw", 0.12),
        )
        expected = {
            "dog_bark": "Bark", "cat": "Meow", "glass_breaking": "Shatter", "loud_bang": "Fireworks",
            "bell": "Church bell", "thunder": "Thunderstorm", "train": "Train horn", "clapping": "Applause",
            "cough": "Throat clearing", "toilet_flush": "Toilet flush", "typing": "Computer keyboard",
            "snoring": "Snoring", "chainsaw": "Chainsaw",
        }
        for event, label in expected.items():
            self.assertEqual(events[event][1], label, event)

    def test_specific_floor_is_lower_than_generic_floor(self) -> None:
        events = _events(("Fire alarm", 0.12), ("Alarm", 0.12))
        self.assertEqual(events["alarm"], (0.12, "Fire alarm"))

    def test_strongest_label_wins_per_event(self) -> None:
        events = _events(("Telephone", 0.8), ("Ringtone", 0.6), ("Telephone bell ringing", 0.7))
        self.assertEqual(events["phone_ringing"], (0.8, "Telephone"))

    def test_speech_confidence_tracks_speech_labels(self) -> None:
        result = map_predictions([_Prediction("Speech", 0.7), _Prediction("Narration, monologue", 0.9)])
        self.assertEqual(result.speech_confidence, 0.9)
        self.assertEqual(result.events, ())


class SoundCatalogTests(unittest.TestCase):
    def test_ids_are_unique_and_categories_valid(self) -> None:
        self.assertEqual(len(EVENT_IDS), len(set(EVENT_IDS)))
        for entry in CATALOG:
            self.assertIn(entry.category, {"emergency", "attention", "informational"}, entry.event)
            self.assertTrue(entry.labels or entry.exact_labels or entry.event == "name_called", entry.event)

    def test_every_catalog_label_exists_in_the_yamnet_vocabulary(self) -> None:
        labels_path = Path("models/source/yamnet-onnx-w8a8/yamnet-onnx-w8a8/labels.txt")
        vocabulary = [line.strip().lower() for line in labels_path.read_text().splitlines() if line.strip()]
        for entry in CATALOG:
            for term in entry.labels:
                self.assertTrue(any(term in label for label in vocabulary), f"{entry.event}: {term}")
            for term in entry.exact_labels:
                self.assertIn(term, vocabulary, f"{entry.event}: {term}")

    def test_legacy_ids_translate_to_current_ones(self) -> None:
        self.assertEqual(canonical_event("fire_alarm"), "alarm")
        self.assertEqual(canonical_event("kitchen_timer"), "appliance_beep")
        self.assertEqual(canonical_event("siren"), "siren")
        for target in LEGACY_EVENT_ALIASES.values():
            self.assertIn(target, EVENT_IDS)

    def test_default_categories(self) -> None:
        self.assertEqual(default_category("alarm"), "emergency")
        self.assertEqual(default_category("siren"), "emergency")
        self.assertEqual(default_category("doorbell_knock"), "attention")
        self.assertEqual(default_category("appliance_beep"), "informational")
        self.assertEqual(default_category("custom:abc"), "informational")


if __name__ == "__main__":
    unittest.main()
