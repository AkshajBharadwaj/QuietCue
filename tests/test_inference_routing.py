from __future__ import annotations

import asyncio
import time
import unittest

from backend.app.hub_server import SAMSUNG_PHONE, QuietCueHubServer
from backend.app.samsung_inference_proxy import SamsungEndpoint, SamsungInferenceProxy
from backend.communication.stream_protocol import WireMessage, read_message, write_message
from backend.inference.pipeline import HubInferencePipeline
from backend.inference.demo_classifier import DemoToneSoundClassifier
from backend.profiles.defaults import get_profile
from backend.profiles.engine import ProfileDecisionEngine
from backend.telemetry.alert_store import AlertStateStore


def samsung_result(sequence: int) -> dict[str, object]:
    return {
        "sequence": sequence,
        "events": [],
        "voice_detected": False,
        "speech_confidence": 0.01,
        "transcript": None,
        "speech_pending": False,
        "speech_inference_ms": None,
        "speech_error": None,
        "inference_ms": 12.5,
        "total_ms": 13.0,
        "top_predictions": [{"label": "Silence", "confidence": 0.98}],
        "inference_source": "samsung_onnx_cpu",
        "alerts": [],
        "suppressed": [],
    }


class FakeSamsungProxy:
    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    async def infer(self, message: WireMessage) -> dict[str, object]:
        self.calls += 1
        return samsung_result(int(message.body["sequence"]))

    async def close(self) -> None:
        self.closed = True


class InferenceRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_hub_switches_audio_to_samsung_without_restarting_uno(self) -> None:
        profile = get_profile("home")
        store = AlertStateStore(profile)
        phone = FakeSamsungProxy()
        hub = QuietCueHubServer(
            lambda: HubInferencePipeline(DemoToneSoundClassifier()),
            ProfileDecisionEngine(profile),
            store,
            samsung_proxy=phone,
        )
        selected = hub.set_inference_device(SAMSUNG_PHONE)
        self.assertEqual(SAMSUNG_PHONE, selected["requested_device"])

        result, decisions = await hub._process_audio(
            WireMessage(
                "audio_chunk",
                {
                    "sequence": 7,
                    "captured_at_ms": int(time.time() * 1_000),
                    "sample_rate": 16_000,
                    "channels": 1,
                    "encoding": "pcm_s16le",
                },
                payload=b"\x00\x00" * 8_000,
            )
        )

        self.assertEqual("samsung_onnx_cpu", result.inference_source)
        self.assertEqual((), decisions.alerts)
        self.assertEqual(1, phone.calls)
        self.assertEqual(SAMSUNG_PHONE, hub.inference_status()["active_device"])
        self.assertEqual("samsung_onnx_cpu", store.snapshot()["latest_result"]["inference_source"])
        await hub.close()
        self.assertTrue(phone.closed)

    async def test_proxy_authenticates_and_forwards_audio(self) -> None:
        received_token = ""

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal received_token
            hello = await read_message(reader)
            received_token = str(hello.body.get("pairing_token", ""))
            await write_message(
                writer,
                WireMessage(
                    "hub_hello",
                    {
                        "node_id": "test-samsung",
                        "kind": "samsung_phone",
                        "capabilities": ["sound_confirmation"],
                    },
                ),
            )
            audio = await read_message(reader)
            await write_message(
                writer,
                WireMessage("detection_result", samsung_result(int(audio.body["sequence"]))),
            )
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = int(server.sockets[0].getsockname()[1])
        proxy = SamsungInferenceProxy(SamsungEndpoint("127.0.0.1", port), "shared-token")
        try:
            response = await proxy.infer(
                WireMessage(
                    "audio_chunk",
                    {"sequence": 3},
                    payload=b"\x00\x00",
                )
            )
            self.assertEqual("shared-token", received_token)
            self.assertEqual("samsung_onnx_cpu", response["inference_source"])
        finally:
            await proxy.close()
            server.close()
            await server.wait_closed()


class SamsungEndpointTest(unittest.TestCase):
    def test_parses_host_and_port(self) -> None:
        self.assertEqual(SamsungEndpoint("127.0.0.1", 18765), SamsungEndpoint.parse("127.0.0.1:18765"))

    def test_rejects_missing_port(self) -> None:
        with self.assertRaises(ValueError):
            SamsungEndpoint.parse("phone.local")
