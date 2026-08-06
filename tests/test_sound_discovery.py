from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.status_server import StatusHttpServer
from backend.inference.pipeline import HubInferenceResult
from backend.profiles.defaults import get_profile
from backend.profiles.engine import DecisionResult
from backend.telemetry.alert_store import AlertStateStore
from backend.telemetry.sound_discovery import SoundDiscoveryTracker


class SoundDiscoveryTrackerTest(unittest.TestCase):
    def test_consecutive_frames_are_grouped_into_distinct_episodes(self) -> None:
        tracker = SoundDiscoveryTracker(episode_gap_ms=3_000, minimum_episodes=3)
        predictions = ({"label": "Dog", "confidence": 0.65},)

        tracker.observe(predictions, profile_name="Home", observed_at_ms=1_000)
        tracker.observe(
            ({"label": "Dog", "confidence": 0.80},),
            profile_name="Home",
            observed_at_ms=2_000,
        )
        tracker.observe(predictions, profile_name="Home", observed_at_ms=6_000)
        self.assertEqual(tracker.candidates(), [])

        tracker.observe(
            ({"label": "Dog", "confidence": 0.90},),
            profile_name="Work / School",
            observed_at_ms=10_000,
        )

        candidate = tracker.candidates()[0]
        self.assertEqual(candidate["label"], "Dog")
        self.assertEqual(candidate["episodes"], 3)
        self.assertEqual(candidate["mean_confidence"], 0.7833)
        self.assertEqual(candidate["profile_names"], ["Home", "Work / School"])

    def test_mapped_generic_low_confidence_and_custom_sound_windows_are_ignored(self) -> None:
        tracker = SoundDiscoveryTracker(minimum_episodes=1)
        tracker.observe(
            (
                {"label": "Fire alarm", "confidence": 0.91},
                {"label": "Speech", "confidence": 0.88},
                {"label": "Dog", "confidence": 0.20},
                {"label": "Vacuum cleaner", "confidence": float("nan")},
            ),
            mapped_source_labels=("Fire alarm",),
            profile_name="Home",
            observed_at_ms=1_000,
        )
        tracker.observe(
            ({"label": "Vacuum cleaner", "confidence": 0.80},),
            profile_name="Home",
            observed_at_ms=5_000,
            custom_sound_matched=True,
        )

        self.assertEqual(tracker.candidates(), [])

    def test_dismissed_candidate_does_not_reappear(self) -> None:
        tracker = SoundDiscoveryTracker(minimum_episodes=1)
        prediction = ({"label": "Vacuum cleaner", "confidence": 0.80},)
        tracker.observe(prediction, profile_name="Home", observed_at_ms=1_000)
        candidate_id = str(tracker.candidates()[0]["id"])

        self.assertTrue(tracker.dismiss(candidate_id))
        tracker.observe(prediction, profile_name="Home", observed_at_ms=10_000)

        self.assertEqual(tracker.candidates(), [])

    def test_state_store_records_metadata_only_observations(self) -> None:
        tracker = SoundDiscoveryTracker(minimum_episodes=1)
        store = AlertStateStore(get_profile("home"), discovery_tracker=tracker)
        inference = HubInferenceResult(
            events=(),
            voice_detected=False,
            speech_confidence=0.0,
            transcript=None,
            speech_pending=False,
            speech_inference_ms=None,
            speech_error=None,
            inference_ms=12.0,
            total_ms=13.0,
            top_predictions=({"label": "Vacuum cleaner", "confidence": 0.82},),
            inference_source="test",
        )

        store.record(4, inference, DecisionResult((), ()), captured_at_ms=123_000)
        snapshot = store.snapshot()

        observation = snapshot["recent_observations"][0]
        self.assertEqual(observation["captured_at_ms"], 123_000)
        self.assertEqual(observation["profile"]["name"], "Home")
        self.assertNotIn("pcm", json.dumps(observation).lower())
        self.assertEqual(snapshot["discoveries"]["candidates"][0]["label"], "Vacuum cleaner")

    def test_candidates_and_dismissals_persist_without_audio(self) -> None:
        with tempfile.TemporaryDirectory(prefix="quietcue-discovery-") as directory:
            state_path = Path(directory) / "discoveries.json"
            tracker = SoundDiscoveryTracker(minimum_episodes=1, state_path=state_path)
            tracker.observe(
                ({"label": "Vacuum cleaner", "confidence": 0.82},),
                profile_name="Home",
                observed_at_ms=1_000,
            )

            restored = SoundDiscoveryTracker(minimum_episodes=1, state_path=state_path)
            candidate_id = str(restored.candidates()[0]["id"])
            self.assertEqual(restored.candidates()[0]["label"], "Vacuum cleaner")
            self.assertNotIn("pcm", state_path.read_text(encoding="utf-8").lower())

            self.assertTrue(restored.dismiss(candidate_id))
            dismissed = SoundDiscoveryTracker(minimum_episodes=1, state_path=state_path)
            self.assertEqual(dismissed.candidates(), [])


class SoundDiscoveryHttpTest(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_can_be_dismissed_through_status_api(self) -> None:
        tracker = SoundDiscoveryTracker(minimum_episodes=1)
        tracker.observe(
            ({"label": "Dog", "confidence": 0.80},),
            profile_name="Home",
            observed_at_ms=1_000,
        )
        store = AlertStateStore(get_profile("home"), discovery_tracker=tracker)
        candidate_id = str(store.snapshot()["discoveries"]["candidates"][0]["id"])
        status = StatusHttpServer(
            store.snapshot,
            update_discovery=store.update_discovery,
        )
        server = await asyncio.start_server(status.handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        body = b'{"action":"dismiss"}'
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(
                (
                    f"POST /api/discoveries/{candidate_id} HTTP/1.1\r\n"
                    f"Host: 127.0.0.1\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode("ascii")
                + body
            )
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()

            self.assertIn(b"200 OK", response)
            self.assertIn(b'"status":"dismiss"', response)
            self.assertEqual(store.snapshot()["discoveries"]["candidates"], [])
        finally:
            server.close()
            await server.wait_closed()
