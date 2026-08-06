from __future__ import annotations

import asyncio
import time
import unittest
from datetime import datetime

from backend.audio.demo_audio import generate_tone_pcm
from backend.communication.stream_protocol import WireMessage, read_message, write_message
from backend.inference.demo_classifier import DemoToneSoundClassifier
from backend.inference.pipeline import ConfirmedEvent, HubInferencePipeline
from backend.profiles.defaults import get_profile
from backend.profiles.engine import ProfileDecisionEngine
from backend.telemetry.alert_store import AlertStateStore
from backend.app.hub_server import QuietCueHubServer


class DemoPipelineTest(unittest.TestCase):
    def test_tone_maps_to_confirmed_event_and_profile_alert(self) -> None:
        pipeline = HubInferencePipeline(DemoToneSoundClassifier())
        inference = pipeline.process_pcm16(generate_tone_pcm("fire_alarm", 0.5), 16_000)

        self.assertEqual(inference.events[0].event, "fire_alarm")
        decisions = ProfileDecisionEngine(get_profile("home")).decide(
            inference.events,
            captured_at_ms=1_000,
            source_sequence=0,
            now_ms=1_050,
        )
        self.assertEqual(decisions.alerts[0].pattern, "urgent_repeat")
        self.assertEqual(decisions.alerts[0].total_after_capture_ms, 50)

    def test_profile_can_disable_an_event(self) -> None:
        pipeline = HubInferencePipeline(DemoToneSoundClassifier())
        inference = pipeline.process_pcm16(generate_tone_pcm("car_horn", 0.5), 16_000)

        decisions = ProfileDecisionEngine(get_profile("home")).decide(
            inference.events,
            captured_at_ms=1_000,
            source_sequence=0,
            now_ms=1_050,
        )
        self.assertFalse(decisions.alerts)
        self.assertEqual(decisions.suppressed[0].reason, "disabled_by_profile")

    def test_quiet_hours_suppress_attention_but_not_emergency(self) -> None:
        engine = ProfileDecisionEngine(get_profile("sleep"))
        events = (
            ConfirmedEvent("name_called", 0.90, "phrase", "attention", "long_pulse", False),
            ConfirmedEvent("fire_alarm", 0.90, "Fire alarm", "emergency", "urgent_repeat", True),
        )

        decisions = engine.decide(
            events,
            captured_at_ms=1_000,
            source_sequence=0,
            now_ms=1_010,
            local_datetime=datetime(2026, 8, 4, 23, 0),
        )

        self.assertEqual([alert.event for alert in decisions.alerts], ["fire_alarm"])
        self.assertEqual(decisions.suppressed[0].reason, "quiet_hours")

    def test_unconfigured_recognized_sound_uses_phone_fallback_cue(self) -> None:
        engine = ProfileDecisionEngine(get_profile("sleep"))
        event = ConfirmedEvent(
            "custom:unconfigured",
            0.88,
            "enrolled: Unknown appliance",
            "attention",
            "long_pulse",
            False,
        )

        decisions = engine.decide(
            (event,),
            captured_at_ms=1_000,
            source_sequence=0,
            now_ms=1_010,
            local_datetime=datetime(2026, 8, 4, 23, 0),
        )

        self.assertEqual(decisions.alerts[0].pattern, "two_short")
        self.assertEqual(decisions.alerts[0].strength, "gentle")
        self.assertTrue(decisions.alerts[0].fallback_to_phone)


class HubIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_audio_frame_returns_alert_command(self) -> None:
        profile = get_profile("home")
        store = AlertStateStore(profile)
        hub = QuietCueHubServer(
            lambda: HubInferencePipeline(DemoToneSoundClassifier()),
            ProfileDecisionEngine(profile),
            store,
        )
        server = await asyncio.start_server(hub.handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await write_message(
                writer,
                WireMessage("edge_hello", {"device_id": "wav-test", "protocol": 1}),
            )
            self.assertEqual((await read_message(reader)).kind, "hub_hello")
            now_ms = int(time.time() * 1_000)
            await write_message(
                writer,
                WireMessage(
                    "audio_chunk",
                    {
                        "sequence": 0,
                        "captured_at_ms": now_ms,
                        "sample_rate": 16_000,
                        "channels": 1,
                        "encoding": "pcm_s16le",
                    },
                    generate_tone_pcm("fire_alarm", 0.5),
                ),
            )
            response = await read_message(reader)
            event_id = response.body["alerts"][0]["event_id"]
            await write_message(
                writer,
                WireMessage(
                    "haptic_result",
                    {
                        "sequence": 0,
                        "outcomes": [
                            {
                                "event_id": event_id,
                                "event": "fire_alarm",
                                "delivered": True,
                                "reason": "delivered",
                                "pattern": "urgent_repeat",
                            }
                        ],
                        "health": {"transport_healthy": True},
                    },
                ),
            )
            await asyncio.sleep(0.02)
            writer.close()
            await writer.wait_closed()

            self.assertEqual(response.kind, "detection_result")
            self.assertEqual(response.body["alerts"][0]["event"], "fire_alarm")
            self.assertEqual(store.snapshot()["latest_alert"]["pattern"], "urgent_repeat")
            self.assertFalse(store.snapshot()["latest_alert"]["simulated"])
            self.assertTrue(
                store.snapshot()["haptics"]["latest_result"]["health"]["transport_healthy"]
            )
        finally:
            server.close()
            await server.wait_closed()
