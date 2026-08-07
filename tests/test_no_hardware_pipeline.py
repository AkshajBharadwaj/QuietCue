from __future__ import annotations

import asyncio
import time
import unittest
from datetime import datetime

from backend.audio.demo_audio import generate_tone_pcm
from backend.audio.wav_source import AudioChunk
from backend.communication.stream_protocol import WireMessage, read_message, write_message
from backend.inference.demo_classifier import DemoToneSoundClassifier
from backend.inference.pipeline import ConfirmedEvent, HubInferencePipeline
from backend.inference.models import SoundPrediction
from backend.profiles.defaults import get_profile
from backend.profiles.engine import ProfileDecisionEngine
from backend.profiles.wire_codec import decode_profile
from backend.telemetry.alert_store import AlertStateStore
from backend.app.hub_server import QuietCueHubServer
from uno_q.linux.rpc_client import AlertDispatcher
from uno_q.linux.transport.hub_client import Endpoint, stream_chunks
from uno_q.linux.transport.hub_selector import HubKind, RoutingPreference


class ConnectedFireAlarmClassifier:
    def __init__(self) -> None:
        self.calls = 0

    def classify_pcm16(
        self, pcm: bytes, sample_rate: int, top_k: int = 10
    ) -> list[SoundPrediction]:
        self.calls += 1
        return [SoundPrediction("Fire alarm", 0.93)]


class ConnectedVacuumClassifier:
    def classify_pcm16(
        self, pcm: bytes, sample_rate: int, top_k: int = 10
    ) -> list[SoundPrediction]:
        return [SoundPrediction("Vacuum cleaner", 0.88)]


class RecordingHapticTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def play_haptic(self, pattern: str, intensity: int, repeat_count: int) -> bool:
        self.calls.append(("play_haptic", pattern, intensity, repeat_count))
        return True

    def play_custom_haptic(self, encoded_steps: str, intensity: int, repeat_count: int) -> bool:
        self.calls.append(("play_custom_haptic", encoded_steps, intensity, repeat_count))
        return True

    def stop_haptic(self) -> bool:
        self.calls.append(("stop_haptic",))
        return True

    def get_button_state(self) -> bool:
        return False

    def set_status_led(self, state: bool) -> bool:
        return True

    def health_check(self) -> bool:
        return True


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
    async def test_approved_classifier_label_reaches_profile_alert_pipeline(self) -> None:
        profile = decode_profile(
            {
                "id": "home",
                "name": "Home",
                "sound_rules": [
                    {
                        "event": "custom:vacuum",
                        "enabled": True,
                        "confidence_threshold": 0.70,
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
        store = AlertStateStore(profile)
        hub = QuietCueHubServer(
            lambda: HubInferencePipeline(ConnectedVacuumClassifier()),
            ProfileDecisionEngine(profile),
            store,
        )
        server = await asyncio.start_server(hub.handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            await write_message(writer, WireMessage("edge_hello", {"device_id": "label-test"}))
            await read_message(reader)
            await write_message(
                writer,
                WireMessage(
                    "audio_chunk",
                    {
                        "sequence": 0,
                        "captured_at_ms": int(time.time() * 1_000),
                        "sample_rate": 16_000,
                        "channels": 1,
                        "encoding": "pcm_s16le",
                    },
                    generate_tone_pcm("fire_alarm", 0.5),
                ),
            )
            response = await read_message(reader)
            writer.close()
            await writer.wait_closed()

            self.assertEqual(response.body["alerts"][0]["event"], "custom:vacuum")
            self.assertEqual(response.body["alerts"][0]["pattern"], "two_short")
        finally:
            server.close()
            await server.wait_closed()

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

    async def test_connected_hub_inference_reaches_haptic_transport_end_to_end(self) -> None:
        profile = get_profile("home")
        classifier = ConnectedFireAlarmClassifier()
        hub = QuietCueHubServer(
            lambda: HubInferencePipeline(classifier),
            ProfileDecisionEngine(profile),
            AlertStateStore(profile),
        )
        server = await asyncio.start_server(hub.handle_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        transport = RecordingHapticTransport()
        now_ms = int(time.time() * 1_000)
        pcm = generate_tone_pcm("fire_alarm", 0.5)
        chunks = (
            AudioChunk(0, now_ms, pcm),
            AudioChunk(1, now_ms + 500, pcm),
        )
        try:
            await stream_chunks(
                chunks,
                [Endpoint("pc", HubKind.COPILOT_PC, "127.0.0.1", port)],
                RoutingPreference.AUTO,
                "connected-hub-haptic-test",
                "",
                [],
                compact=True,
                alert_dispatcher=AlertDispatcher(transport),
            )

            self.assertEqual(classifier.calls, 2)
            self.assertIn(("play_haptic", "urgent_repeat", 255, 0), transport.calls)
        finally:
            server.close()
            await server.wait_closed()

    async def test_stop_haptic_is_delivered_to_connected_uno_q(self) -> None:
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
                WireMessage("edge_hello", {"device_id": "stop-test", "protocol": 1}),
            )
            await read_message(reader)
            now_ms = int(time.time() * 1_000)

            async def send_chunk(sequence: int) -> WireMessage:
                await write_message(
                    writer,
                    WireMessage(
                        "audio_chunk",
                        {
                            "sequence": sequence,
                            "captured_at_ms": now_ms,
                            "sample_rate": 16_000,
                            "channels": 1,
                            "encoding": "pcm_s16le",
                        },
                        generate_tone_pcm("fire_alarm", 0.5),
                    ),
                )
                return await read_message(reader)

            first = await send_chunk(0)
            event_id = first.body["alerts"][0]["event_id"]
            queued = hub.stop_haptic(event_id)
            second = await send_chunk(1)
            writer.close()
            await writer.wait_closed()

            self.assertEqual(queued["status"], "stop_queued")
            self.assertEqual(second.body["control_commands"][0]["command"], "stop_haptic")
            self.assertFalse(store.snapshot()["latest_alert"]["haptic_active"])
        finally:
            server.close()
            await server.wait_closed()
