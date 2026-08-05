"""Raw-TCP inference hub for Uno Q audio chunks."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from backend.app.status_server import StatusHttpServer
from backend.communication.stream_protocol import ProtocolError, WireMessage, read_message, write_message
from backend.inference.custom_sound_matcher import CustomSoundMatcher
from backend.inference.pipeline import HubInferencePipeline, HubInferenceResult, SoundClassifier
from backend.profiles.defaults import all_profiles, get_profile
from backend.profiles.engine import DecisionResult, ProfileDecisionEngine
from backend.profiles.wire_codec import decode_profile
from backend.telemetry.alert_store import AlertStateStore


LOGGER = logging.getLogger("quietcue.hub")
DEFAULT_PORT = 8765
DEFAULT_STATE_PORT = 8787


class QuietCueHubServer:
    def __init__(
        self,
        pipeline_factory: Callable[[], HubInferencePipeline],
        decision_engine: ProfileDecisionEngine,
        state_store: AlertStateStore,
        custom_matcher: CustomSoundMatcher | None = None,
        pairing_token: str = "",
    ) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipeline: HubInferencePipeline | None = None
        self._pipeline_lock = asyncio.Lock()
        self._decision_engine = decision_engine
        self._state_store = state_store
        self._custom_matcher = custom_matcher or CustomSoundMatcher(decision_engine.profile.custom_sounds)
        self._pairing_token = pairing_token

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        device_id = "unknown"
        session_id = uuid.uuid4().hex
        try:
            hello = await asyncio.wait_for(read_message(reader), timeout=5.0)
            if hello.kind != "edge_hello":
                raise ProtocolError("First message must be edge_hello")
            device_id = str(hello.body.get("device_id", "unknown"))
            supplied_token = str(hello.body.get("pairing_token", ""))
            if self._pairing_token and supplied_token != self._pairing_token:
                await write_message(
                    writer,
                    WireMessage("error", {"code": "pairing_failed", "message": "Invalid pairing token"}),
                )
                return

            await self._reset_pipeline_stream()

            await write_message(
                writer,
                WireMessage(
                    "hub_hello",
                    {
                        "node_id": "quietcue-copilot-hub",
                        "kind": "copilot_pc",
                        "protocol": 1,
                        "capabilities": [
                            "sound_confirmation",
                            "speech_detection",
                            "speech_to_text_optional",
                        ],
                    },
                ),
            )
            LOGGER.info("Uno Q %s connected from %s", device_id, peer)
            self._state_store.connected(session_id, device_id)

            while True:
                message = await read_message(reader)
                if message.kind == "heartbeat":
                    await write_message(writer, WireMessage("heartbeat_ack", message.body))
                    continue
                if message.kind != "audio_chunk":
                    raise ProtocolError(f"Unsupported message kind: {message.kind}")
                result, decisions = await self._process_audio(message)
                await write_message(
                    writer,
                    WireMessage(
                        "detection_result",
                        {
                            "sequence": message.body.get("sequence"),
                            **result.to_wire(),
                            **decisions.to_wire(),
                        },
                    ),
                )
                for alert in decisions.alerts:
                    LOGGER.warning(
                        "SIMULATED HAPTIC %s: %s (%s, %.1f%%) via profile %s",
                        alert.pattern,
                        alert.event,
                        alert.category,
                        alert.confidence * 100,
                        alert.profile_name,
                    )
        except asyncio.IncompleteReadError:
            LOGGER.info("Uno Q %s disconnected", device_id)
        except (ProtocolError, ValueError, asyncio.TimeoutError) as exc:
            LOGGER.warning("Rejected message from %s: %s", peer, exc)
            try:
                await write_message(
                    writer,
                    WireMessage("error", {"code": "invalid_message", "message": str(exc)}),
                )
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
        finally:
            self._state_store.disconnected(session_id)
            writer.close()
            await writer.wait_closed()

    async def _process_audio(self, message: WireMessage) -> tuple[HubInferenceResult, DecisionResult]:
        body = message.body
        if body.get("encoding") != "pcm_s16le" or body.get("channels") != 1:
            raise ValueError("Only mono pcm_s16le audio is supported")
        sample_rate = int(body.get("sample_rate", 0))
        sequence = int(body.get("sequence", -1))
        captured_at_ms = int(body.get("captured_at_ms", 0))
        if sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if captured_at_ms <= 0:
            raise ValueError("captured_at_ms must be a positive epoch timestamp")
        phrase_triggers = body.get("phrase_triggers", [])
        if not isinstance(phrase_triggers, list) or not all(
            isinstance(phrase, str) for phrase in phrase_triggers
        ):
            raise ValueError("phrase_triggers must be a list of strings")

        async with self._pipeline_lock:
            if self._pipeline is None:
                self._pipeline = await asyncio.to_thread(self._pipeline_factory)
            inference = await asyncio.to_thread(
                self._pipeline.process_pcm16,
                message.payload,
                sample_rate,
                body.get("edge_analysis") if isinstance(body.get("edge_analysis"), dict) else None,
                list(dict.fromkeys([*self._decision_engine.profile.phrase_triggers, *phrase_triggers])),
            )
            custom_events = await asyncio.to_thread(
                self._custom_matcher.match_pcm16,
                message.payload,
                sample_rate,
            )
            if custom_events:
                inference = replace(inference, events=inference.events + custom_events)
        decisions = self._decision_engine.decide(
            inference.events,
            captured_at_ms=captured_at_ms,
            source_sequence=sequence,
            now_ms=int(time.time() * 1_000),
        )
        self._state_store.record(sequence, inference, decisions)
        return inference, decisions

    async def close(self) -> None:
        async with self._pipeline_lock:
            pipeline, self._pipeline = self._pipeline, None
        if pipeline is not None:
            await asyncio.to_thread(pipeline.close)

    async def _reset_pipeline_stream(self) -> None:
        async with self._pipeline_lock:
            if self._pipeline is not None:
                self._pipeline.reset_stream()


def _pipeline_factory(
    classifier: str,
    speech_model: str,
    speech_device: str,
    speech_compute_type: str,
    speech_language: str,
) -> Callable[[], HubInferencePipeline]:
    def build(sound_classifier: SoundClassifier) -> HubInferencePipeline:
        transcriber = None
        if speech_model:
            from backend.inference.speech import FasterWhisperTranscriber

            transcriber = FasterWhisperTranscriber(
                speech_model,
                device=speech_device,
                compute_type=speech_compute_type,
                language=None if speech_language == "auto" else speech_language,
            )
        return HubInferencePipeline(sound_classifier, transcriber)

    if classifier == "demo":
        from backend.inference.demo_classifier import DemoToneSoundClassifier

        return lambda: build(DemoToneSoundClassifier())
    if classifier == "yamnet":
        def create_yamnet() -> HubInferencePipeline:
            from backend.inference.sound_classifier import YamnetSoundClassifier

            return build(YamnetSoundClassifier())

        return create_yamnet
    raise ValueError(f"Unknown classifier: {classifier}")


async def serve(
    host: str,
    port: int,
    state_host: str,
    state_port: int,
    pairing_token: str,
    classifier: str,
    profile_id: str,
    event_log: Path | None,
    speech_model: str,
    speech_device: str,
    speech_compute_type: str,
    speech_language: str,
) -> None:
    profile = get_profile(profile_id)
    state_store = AlertStateStore(profile, jsonl_path=event_log)
    decision_engine = ProfileDecisionEngine(profile)
    custom_matcher = CustomSoundMatcher(profile.custom_sounds)
    hub = QuietCueHubServer(
        _pipeline_factory(
            classifier,
            speech_model,
            speech_device,
            speech_compute_type,
            speech_language,
        ),
        decision_engine,
        state_store,
        custom_matcher,
        pairing_token=pairing_token,
    )

    def update_profile(document: dict[str, object]) -> dict[str, object]:
        updated = decode_profile(document)
        decision_engine.set_profile(updated)
        custom_matcher.set_prototypes(updated.custom_sounds)
        state_store.set_profile(updated)
        LOGGER.info(
            "Active profile synchronized: %s (%d rules, %d enrolled sounds)",
            updated.name,
            len(updated.sound_rules),
            len(updated.custom_sounds),
        )
        return {"status": "updated", "active_profile": updated.summary()}

    status = StatusHttpServer(state_store.snapshot, update_profile=update_profile)
    audio_server = await asyncio.start_server(hub.handle_client, host, port)
    state_server = await asyncio.start_server(status.handle_client, state_host, state_port)
    audio_addresses = ", ".join(str(socket.getsockname()) for socket in audio_server.sockets or [])
    state_addresses = ", ".join(str(socket.getsockname()) for socket in state_server.sockets or [])
    LOGGER.info("QuietCue audio hub listening on %s", audio_addresses)
    LOGGER.info("Android state API listening on %s", state_addresses)
    LOGGER.info("Classifier=%s profile=%s", classifier, profile.name)
    LOGGER.info(
        "Speech model=%s device=%s compute=%s",
        speech_model or "disabled",
        speech_device,
        speech_compute_type,
    )
    try:
        async with audio_server, state_server:
            await asyncio.gather(audio_server.serve_forever(), state_server.serve_forever())
    finally:
        await hub.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the QuietCue Copilot inference hub")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--state-host", default="127.0.0.1")
    parser.add_argument("--state-port", type=int, default=DEFAULT_STATE_PORT)
    parser.add_argument("--classifier", choices=("demo", "yamnet"), default="yamnet")
    parser.add_argument("--profile", choices=tuple(all_profiles()), default="home")
    parser.add_argument(
        "--speech-model",
        default=os.environ.get("QUIETCUE_SPEECH_MODEL", ""),
        help="Optional local Faster-Whisper model name/path, for example tiny.en",
    )
    parser.add_argument(
        "--speech-device",
        default=os.environ.get("QUIETCUE_SPEECH_DEVICE", "cpu"),
        help="Faster-Whisper execution device (default: cpu)",
    )
    parser.add_argument(
        "--speech-compute-type",
        default=os.environ.get("QUIETCUE_SPEECH_COMPUTE_TYPE", "int8"),
        help="Faster-Whisper compute type (default: int8)",
    )
    parser.add_argument(
        "--speech-language",
        default=os.environ.get("QUIETCUE_SPEECH_LANGUAGE", "en"),
        help="Speech language code or auto (default: en)",
    )
    parser.add_argument(
        "--event-log",
        type=Path,
        help="Optional metadata-only JSONL event log (raw audio is never written)",
    )
    parser.add_argument(
        "--pairing-token",
        default=os.environ.get("QUIETCUE_PAIRING_TOKEN", ""),
        help="Shared development token; defaults to QUIETCUE_PAIRING_TOKEN",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.pairing_token:
        LOGGER.warning("No pairing token configured; use only on a trusted development network")
    try:
        asyncio.run(
            serve(
                args.host,
                args.port,
                args.state_host,
                args.state_port,
                args.pairing_token,
                args.classifier,
                args.profile,
                args.event_log,
                args.speech_model.strip(),
                args.speech_device,
                args.speech_compute_type,
                args.speech_language,
            )
        )
    except KeyboardInterrupt:
        LOGGER.info("QuietCue hub stopped")


if __name__ == "__main__":
    main()
