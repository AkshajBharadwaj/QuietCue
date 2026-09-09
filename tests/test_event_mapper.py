"""Tests for the AudioSet label to QuietCue event mapper."""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from backend.inference.event_mapper import map_predictions


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
        self.assertEqual(events["fire_alarm"], (0.5, "Smoke detector, smoke alarm"))
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
        self.assertEqual(events["fire_alarm"], (0.6, "Alarm"))
        self.assertEqual(events["doorbell_knock"], (0.45, "Buzzer"))
        self.assertEqual(events["kitchen_timer"], (0.5, "Beep, bleep"))
        self.assertEqual(events["baby_crying"], (0.33, "Whimper"))

    def test_generic_labels_below_floor_are_ignored(self) -> None:
        events = _events(("Telephone", 0.29), ("Alarm", 0.2), ("Door", 0.15))
        self.assertEqual(events, {})

    def test_generic_terms_require_the_exact_label(self) -> None:
        # "Car alarm" and "Whimper (dog)" contain generic terms but are not the parent label.
        events = _events(("Car alarm", 0.9), ("Whimper (dog)", 0.9), ("Sliding door", 0.9))
        self.assertNotIn("fire_alarm", events)
        self.assertNotIn("baby_crying", events)
        self.assertNotIn("doorbell_knock", events)

    def test_specific_floor_is_lower_than_generic_floor(self) -> None:
        events = _events(("Fire alarm", 0.12), ("Alarm", 0.12))
        self.assertEqual(events["fire_alarm"], (0.12, "Fire alarm"))

    def test_strongest_label_wins_per_event(self) -> None:
        events = _events(("Telephone", 0.8), ("Ringtone", 0.6), ("Telephone bell ringing", 0.7))
        self.assertEqual(events["phone_ringing"], (0.8, "Telephone"))

    def test_speech_confidence_tracks_speech_labels(self) -> None:
        result = map_predictions([_Prediction("Speech", 0.7), _Prediction("Narration, monologue", 0.9)])
        self.assertEqual(result.speech_confidence, 0.9)
        self.assertEqual(result.events, ())


if __name__ == "__main__":
    unittest.main()
