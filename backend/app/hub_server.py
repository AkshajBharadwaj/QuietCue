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

from backend.app.samsung_inference_proxy import SamsungEndpoint, SamsungInferenceProxy
from backend.app.status_server import StatusHttpServer
from backend.communication.stream_protocol import ProtocolError, WireMessage, read_message, write_message
from backend.inference.custom_sound_matcher import (
    CustomSoundMatcher,
    speech_confidence_from_predictions,
)
from backend.inference.enrollment_capture import EnrollmentCaptureController
from backend.inference.classifier_label_matcher import ClassifierLabelMatcher
from backend.inference.pipeline import (
    ConfirmedEvent,
    HubInferencePipeline,
    HubInferenceResult,
    SoundClassifier,
)
from backend.profiles.defaults import all_profiles, get_profile
from backend.profiles.engine import (
    AlertCommand,
    DecisionResult,
    ProfileDecisionEngine,
    SuppressedEvent,
)
from backend.profiles.wire_codec import decode_profile
from backend.telemetry.alert_store import AlertStateStore


LOGGER = logging.getLogger("quietcue.hub")
DEFAULT_PORT = 8765
DEFAULT_STATE_PORT = 8787
COPILOT_PC = "copilot_pc"
SAMSUNG_PHONE = "samsung_phone"


class QuietCueHubServer:
    def __init__(
        self,
        pipeline_factory: Callable[[], HubInferencePipeline],
        decision_engine: ProfileDecisionEngine,
        state_store: AlertStateStore,
        custom_matcher: CustomSoundMatcher | None = None,
        classifier_label_matcher: ClassifierLabelMatcher | None = None,
        pairing_token: str = "",
        enrollment_capture: EnrollmentCaptureController | None = None,
        samsung_proxy: SamsungInferenceProxy | None = None,
    ) -> None:
        self._pipeline_factory = pipeline_factory
        self._pipeline: HubInferencePipeline | None = None
        self._pipeline_lock = asyncio.Lock()
        self._decision_engine = decision_engine
        self._state_store = state_store
        self._custom_matcher = custom_matcher or CustomSoundMatcher(decision_engine.profile.custom_sounds)
        self._classifier_label_matcher = classifier_label_matcher or ClassifierLabelMatcher(
            decision_engine.profile.classifier_label_rules
        )
        self._pairing_token = pairing_token
        self._enrollment_capture = enrollment_capture or EnrollmentCaptureController()
        self._control_queues: dict[str, list[dict[str, object]]] = {}
        self._samsung_proxy = samsung_proxy
        self._requested_inference_device = COPILOT_PC
        self._active_inference_device = COPILOT_PC
        self._inference_error: str | None = None
        self._samsung_retry_after = 0.0

    def set_inference_device(self, device: str) -> dict[str, object]:
        if device not in {COPILOT_PC, SAMSUNG_PHONE}:
            raise ValueError("Inference device must be copilot_pc or samsung_phone")
        if device == SAMSUNG_PHONE and self._samsung_proxy is None:
            raise ValueError("Samsung inference is unavailable; connect the phone and restart the demo")
        self._requested_inference_device = device
        self._inference_error = None
        self._samsung_retry_after = 0.0
        LOGGER.info("Inference device requested: %s", device)
        return self.inference_status()

    def inference_status(self) -> dict[str, object]:
        return {
            "requested_device": self._requested_inference_device,
            "active_device": self._active_inference_device,
            "samsung_available": self._samsung_proxy is not None,
            "switch_pending": self._requested_inference_device != self._active_inference_device,
            "error": self._inference_error,
        }

    def stop_haptic(self, event_id: str | None = None) -> dict[str, object]:
        acknowledgement = self._state_store.stop_haptic(event_id)
        command = {
            "command": "stop_haptic",
            "event_id": acknowledgement["event_id"],
            "issued_at_ms": acknowledgement["acknowledged_at_ms"],
        }
        for queue in self._control_queues.values():
            queue.append(command)
        return {
            "status": "stop_queued" if self._control_queues else "acknowledged_no_device",
            "queued_devices": len(self._control_queues),
            **acknowledgement,
        }

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
            self._control_queues[session_id] = []

            while True:
                message = await read_message(reader)
                if message.kind == "heartbeat":
                    await write_message(writer, WireMessage("heartbeat_ack", message.body))
                    continue
                if message.kind == "haptic_result":
                    self._state_store.record_haptic_result(device_id, message.body)
                    for outcome in message.body.get("outcomes", []):
                        if not isinstance(outcome, dict):
                            continue
                        LOGGER.info(
                            "HAPTIC %s: %s (%s) on %s",
                            "delivered" if outcome.get("delivered") else "not delivered",
                            outcome.get("event", "unknown"),
                            outcome.get("reason", "unknown"),
                            device_id,
                        )
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
                            "control_commands": self._drain_control_commands(session_id),
                        },
                    ),
                )
                for alert in decisions.alerts:
                    LOGGER.warning(
                        "ALERT COMMAND %s: %s (%s, %.1f%%) via profile %s",
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
            self._control_queues.pop(session_id, None)
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
        phrase_triggers = _bounded_phrase_triggers(body.get("phrase_triggers", []))

        if (
            self._requested_inference_device == SAMSUNG_PHONE
            and self._samsung_proxy is not None
            and time.monotonic() >= self._samsung_retry_after
        ):
            try:
                remote = await self._samsung_proxy.infer(message)
                inference = _decode_remote_inference(remote)
                decisions = _decode_remote_decisions(remote)
                self._enrollment_capture.observe(
                    message.payload,
                    sample_rate,
                    speech_confidence=speech_confidence_from_predictions(
                        inference.top_predictions
                    ),
                )
                self._active_inference_device = SAMSUNG_PHONE
                self._inference_error = None
                self._state_store.record(
                    sequence,
                    inference,
                    decisions,
                    captured_at_ms=captured_at_ms,
                )
                return inference, decisions
            except (OSError, ConnectionError, ProtocolError, asyncio.TimeoutError, ValueError) as exc:
                self._active_inference_device = COPILOT_PC
                self._inference_error = f"Samsung unavailable; using PC ({exc})"
                self._samsung_retry_after = time.monotonic() + 5.0
                LOGGER.warning("Samsung inference failed; falling back to PC: %s", exc)

        async with self._pipeline_lock:
            if self._pipeline is None:
                self._pipeline = await asyncio.to_thread(self._pipeline_factory)
            profile = self._decision_engine.profile
            speech_context = profile.speech_context
            resolved_phrases = speech_context.trigger_phrases(
                profile.phrase_triggers,
                phrase_triggers,
            )
            inference = await asyncio.to_thread(
                self._pipeline.process_pcm16,
                message.payload,
                sample_rate,
                body.get("edge_analysis") if isinstance(body.get("edge_analysis"), dict) else None,
                list(resolved_phrases),
                speech_context.prompt(),
                list(speech_context.hotwords()),
                profile.speech_enabled(),
                speech_context.settings.sensitivity,
            )
            custom_events = await asyncio.to_thread(
                self._custom_matcher.match_pcm16,
                message.payload,
                sample_rate,
                speech_confidence=speech_confidence_from_predictions(inference.top_predictions),
            )
            label_events = self._classifier_label_matcher.match_predictions(
                inference.top_predictions
            )
            additional_events = (*label_events, *custom_events)
            if additional_events:
                strongest = {event.event: event for event in inference.events}
                for event in additional_events:
                    existing = strongest.get(event.event)
                    if existing is None or event.confidence > existing.confidence:
                        strongest[event.event] = event
                inference = replace(inference, events=tuple(strongest.values()))
            self._enrollment_capture.observe(
                message.payload,
                sample_rate,
                speech_confidence=speech_confidence_from_predictions(inference.top_predictions),
            )
        self._active_inference_device = COPILOT_PC
        decisions = self._decision_engine.decide(
            inference.events,
            captured_at_ms=captured_at_ms,
            source_sequence=sequence,
            now_ms=int(time.time() * 1_000),
        )
        self._state_store.record(
            sequence,
            inference,
            decisions,
            captured_at_ms=captured_at_ms,
        )
        return inference, decisions

    async def close(self) -> None:
        async with self._pipeline_lock:
            pipeline, self._pipeline = self._pipeline, None
        if pipeline is not None:
            await asyncio.to_thread(pipeline.close)
        if self._samsung_proxy is not None:
            await self._samsung_proxy.close()

    async def _reset_pipeline_stream(self) -> None:
        async with self._pipeline_lock:
            if self._pipeline is not None:
                self._pipeline.reset_stream()

    def _drain_control_commands(self, session_id: str) -> list[dict[str, object]]:
        queue = self._control_queues.get(session_id, [])
        commands = list(queue)
        queue.clear()
        return commands


def _bounded_phrase_triggers(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("phrase_triggers must be a list of at most 20 strings")
    phrases: list[str] = []
    for phrase in value:
        if not isinstance(phrase, str):
            raise ValueError("phrase_triggers must contain only strings")
        cleaned = phrase.strip()
        if not cleaned or len(cleaned) > 40:
            raise ValueError("phrase triggers must be 1 to 40 characters")
        phrases.append(cleaned)
    return phrases


def _decode_remote_inference(document: dict[str, object]) -> HubInferenceResult:
    raw_events = document.get("events", [])
    if not isinstance(raw_events, list):
        raise ValueError("Samsung events must be a list")
    events = tuple(
        ConfirmedEvent(
            event=str(item["event"]),
            confidence=float(item["confidence"]),
            source_label=str(item.get("source_label", item["event"])),
            category=str(item["category"]),
            pattern=str(item["pattern"]),
            requires_ack=bool(item.get("requires_ack", False)),
        )
        for item in raw_events
        if isinstance(item, dict)
    )
    raw_predictions = document.get("top_predictions", [])
    if not isinstance(raw_predictions, list):
        raise ValueError("Samsung predictions must be a list")
    predictions = tuple(item for item in raw_predictions if isinstance(item, dict))
    return HubInferenceResult(
        events=events,
        voice_detected=bool(document.get("voice_detected", False)),
        speech_confidence=float(document.get("speech_confidence", 0.0)),
        transcript=None,
        speech_pending=bool(document.get("speech_pending", False)),
        speech_inference_ms=_optional_float(document.get("speech_inference_ms")),
        speech_error=_optional_string(document.get("speech_error")),
        inference_ms=float(document.get("inference_ms", 0.0)),
        total_ms=float(document.get("total_ms", 0.0)),
        top_predictions=predictions,
        inference_source=str(document.get("inference_source", "samsung_onnx_cpu")),
    )


def _decode_remote_decisions(document: dict[str, object]) -> DecisionResult:
    raw_alerts = document.get("alerts", [])
    raw_suppressed = document.get("suppressed", [])
    if not isinstance(raw_alerts, list) or not isinstance(raw_suppressed, list):
        raise ValueError("Samsung decisions must contain alert and suppressed lists")
    alerts = tuple(
        AlertCommand(
            event_id=str(item["event_id"]),
            event=str(item["event"]),
            category=str(item["category"]),
            confidence=float(item["confidence"]),
            pattern=str(item["pattern"]),
            strength=str(item["strength"]),
            requires_ack=bool(item.get("requires_ack", False)),
            profile_id=str(item["profile_id"]),
            profile_name=str(item["profile_name"]),
            source_label=str(item.get("source_label", item["event"])),
            source_sequence=int(item["source_sequence"]),
            captured_at_ms=int(item["captured_at_ms"]),
            issued_at_ms=int(item["issued_at_ms"]),
            total_after_capture_ms=int(item["total_after_capture_ms"]),
            simulated=bool(item.get("simulated", False)),
            fallback_to_phone=bool(item.get("fallback_to_phone", False)),
            custom_pattern=str(item.get("custom_pattern", "")),
        )
        for item in raw_alerts
        if isinstance(item, dict)
    )
    suppressed = tuple(
        SuppressedEvent(
            event=str(item["event"]),
            confidence=float(item["confidence"]),
            reason=str(item["reason"]),
        )
        for item in raw_suppressed
        if isinstance(item, dict)
    )
    return DecisionResult(alerts, suppressed)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


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
    if classifier == "onnx":
        def create_onnx() -> HubInferencePipeline:
            from backend.inference.onnx_sound_classifier import (
                OnnxSoundClassifier,
                resolve_model_paths,
            )

            model_path, labels_path, precision = resolve_model_paths(
                os.environ.get("QUIETCUE_ONNX_PRECISION", "auto")
            )
            sound_classifier = OnnxSoundClassifier(
                model_path=os.environ.get("QUIETCUE_ONNX_MODEL", model_path),
                labels_path=os.environ.get("QUIETCUE_ONNX_LABELS", labels_path),
                target=os.environ.get("QUIETCUE_ONNX_TARGET", "auto"),
                cache_dir=os.environ.get("QUIETCUE_ONNX_CACHE_DIR") or None,
            )
            LOGGER.info(
                "ONNX classifier active: model=%s precision=%s provider=%s",
                sound_classifier.model_path,
                precision,
                sound_classifier.active_provider,
            )
            if precision == "w8a8":
                LOGGER.warning(
                    "Using the quantized w8a8 YAMNet: confidences are coarse and thresholds "
                    "between 0.50 and 0.68 cannot be met. Run scripts/fetch_models.sh for float."
                )
            return build(sound_classifier)

        return create_onnx
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
    phone_endpoint: str,
) -> None:
    profile = get_profile(profile_id)
    state_store = AlertStateStore(profile, jsonl_path=event_log)
    decision_engine = ProfileDecisionEngine(profile)
    custom_matcher = CustomSoundMatcher(profile.custom_sounds)
    classifier_label_matcher = ClassifierLabelMatcher(profile.classifier_label_rules)
    enrollment_capture = EnrollmentCaptureController()
    samsung_proxy = (
        SamsungInferenceProxy(SamsungEndpoint.parse(phone_endpoint), pairing_token)
        if phone_endpoint
        else None
    )
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
        classifier_label_matcher,
        pairing_token=pairing_token,
        enrollment_capture=enrollment_capture,
        samsung_proxy=samsung_proxy,
    )

    def update_profile(document: dict[str, object]) -> dict[str, object]:
        updated = decode_profile(document)
        decision_engine.set_profile(updated)
        custom_matcher.set_prototypes(updated.custom_sounds)
        classifier_label_matcher.set_rules(updated.classifier_label_rules)
        state_store.set_profile(updated)
        LOGGER.info(
            "Active profile synchronized: %s (%d rules, %d enrolled sounds, %d label rules, identity=%s, %d people, %d contexts)",
            updated.name,
            len(updated.sound_rules),
            len(updated.custom_sounds),
            len(updated.classifier_label_rules),
            "yes" if updated.speech_context.identity is not None else "no",
            len(updated.speech_context.people),
            len(updated.speech_context.contexts),
        )
        return {"status": "updated", "active_profile": updated.summary()}

    def snapshot() -> dict[str, object]:
        document = state_store.snapshot()
        document["inference"] = hub.inference_status()
        return document

    status = StatusHttpServer(
        snapshot,
        update_profile=update_profile,
        stop_haptic=hub.stop_haptic,
        update_inference_device=hub.set_inference_device,
        start_enrollment=enrollment_capture.start,
        enrollment_status=enrollment_capture.status,
        cancel_enrollment=enrollment_capture.cancel,
    )
    audio_server = await asyncio.start_server(hub.handle_client, host, port)
    state_server = await asyncio.start_server(status.handle_client, state_host, state_port)
    audio_addresses = ", ".join(str(socket.getsockname()) for socket in audio_server.sockets or [])
    state_addresses = ", ".join(str(socket.getsockname()) for socket in state_server.sockets or [])
    LOGGER.info("QuietCue audio hub listening on %s", audio_addresses)
    LOGGER.info("Android state API listening on %s", state_addresses)
    LOGGER.info("Classifier=%s profile=%s", classifier, profile.name)
    LOGGER.info("Samsung inference=%s", phone_endpoint or "not configured")
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
    parser.add_argument(
        "--classifier",
        choices=("demo", "yamnet", "onnx"),
        default=os.environ.get("QUIETCUE_CLASSIFIER", "onnx"),
    )
    parser.add_argument(
        "--onnx-precision",
        choices=("auto", "float", "w8a8"),
        default=os.environ.get("QUIETCUE_ONNX_PRECISION", "auto"),
        help="YAMNet ONNX export for --classifier onnx: float gives continuous confidences "
        "(default auto: float when downloaded, else the checked-in w8a8)",
    )
    parser.add_argument("--profile", choices=tuple(all_profiles()), default="home")
    parser.add_argument(
        "--speech-model",
        default=os.environ.get("QUIETCUE_SPEECH_MODEL", "base.en"),
        help="Local Faster-Whisper model name/path (default: base.en)",
    )
    parser.add_argument(
        "--no-speech",
        action="store_true",
        help="Disable speech transcription even when the active profile enables it",
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
    parser.add_argument(
        "--phone-endpoint",
        default=os.environ.get("QUIETCUE_PHONE_INFERENCE_ENDPOINT", ""),
        help="Optional Samsung inference endpoint as HOST:PORT",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.pairing_token:
        LOGGER.warning("No pairing token configured; use only on a trusted development network")
    # The pipeline is built lazily inside the hub; hand the choice over via the
    # same environment variable the factory reads.
    os.environ["QUIETCUE_ONNX_PRECISION"] = args.onnx_precision
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
                "" if args.no_speech else args.speech_model.strip(),
                args.speech_device,
                args.speech_compute_type,
                args.speech_language,
                args.phone_endpoint.strip(),
            )
        )
    except KeyboardInterrupt:
        LOGGER.info("QuietCue hub stopped")


if __name__ == "__main__":
    main()
