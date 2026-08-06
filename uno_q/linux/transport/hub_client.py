"""Stream Uno Q microphone audio or deterministic WAV replay to one inference hub."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from backend.audio.wav_source import SAMPLE_RATE, AudioChunk, iter_wav_chunks
from backend.communication.stream_protocol import ProtocolError, WireMessage, read_message, write_message
from uno_q.linux.audio_capture.alsa_source import (
    DEFAULT_ALSA_DEVICE,
    AlsaCaptureError,
    AlsaPcmSource,
    list_capture_hardware,
)
from uno_q.linux.audio_capture.edge_analyzer import EdgeAudioAnalyzer
from uno_q.linux.rpc_client import AlertDispatcher, AppLabBridgeHapticTransport
from uno_q.linux.transport.hub_selector import (
    HubCandidate,
    HubKind,
    HubSelector,
    RoutingPreference,
)


@dataclass(frozen=True)
class Endpoint:
    node_id: str
    kind: HubKind
    host: str
    port: int


class NoHubAvailable(ConnectionError):
    """Raised when configured hubs are temporarily unreachable."""


async def probe(endpoint: Endpoint, device_id: str, pairing_token: str) -> HubCandidate | None:
    started = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(endpoint.host, endpoint.port),
            timeout=1.5,
        )
        await write_message(
            writer,
            WireMessage(
                "edge_hello",
                {"device_id": device_id, "protocol": 1, "pairing_token": pairing_token},
            ),
        )
        hello = await asyncio.wait_for(read_message(reader), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        if hello.kind != "hub_hello":
            return None
        capabilities = hello.body.get("capabilities", [])
        return HubCandidate(
            node_id=str(hello.body.get("node_id", endpoint.node_id)),
            kind=endpoint.kind,
            host=endpoint.host,
            port=endpoint.port,
            capabilities=frozenset(str(capability) for capability in capabilities),
            last_seen_ms=_now_ms(),
            round_trip_ms=round((time.perf_counter() - started) * 1_000),
        )
    except (OSError, asyncio.TimeoutError, ConnectionError):
        return None


async def stream_chunks(
    chunks: Iterable[AudioChunk],
    endpoints: list[Endpoint],
    preference: RoutingPreference,
    device_id: str,
    pairing_token: str,
    phrase_triggers: list[str],
    *,
    compact: bool = False,
    alert_dispatcher: AlertDispatcher | None = None,
) -> None:
    candidates = await asyncio.gather(
        *(probe(endpoint, device_id, pairing_token) for endpoint in endpoints)
    )
    selector = HubSelector()
    for candidate in candidates:
        if candidate is not None:
            selector.update(candidate)
    lease = selector.select(_now_ms(), preference)

    analyzer = EdgeAudioAnalyzer(SAMPLE_RATE)

    if lease is None:
        if not endpoints:
            print("No hub configured; showing Uno Q signal diagnostics only.")
            _print_edge_only(chunks, analyzer, compact)
            return
        raise NoHubAvailable("No configured inference hub is reachable")

    selected = lease.candidate
    print(
        f"Selected {selected.kind.value} hub {selected.node_id} "
        f"at {selected.host}:{selected.port} ({selected.round_trip_ms} ms RTT)"
    )
    reader, writer = await asyncio.open_connection(selected.host, selected.port)
    try:
        await write_message(
            writer,
            WireMessage(
                "edge_hello",
                {"device_id": device_id, "protocol": 1, "pairing_token": pairing_token},
            ),
        )
        hello = await read_message(reader)
        if hello.kind != "hub_hello":
            raise RuntimeError(f"Hub rejected session: {hello.body}")

        for chunk in chunks:
            edge = analyzer.analyze_pcm16(chunk.pcm)
            await write_message(
                writer,
                WireMessage(
                    "audio_chunk",
                    {
                        **chunk.to_wire(),
                        "edge_analysis": edge.to_wire(),
                        "phrase_triggers": phrase_triggers,
                    },
                    payload=chunk.pcm,
                ),
            )
            response = await read_message(reader)
            if alert_dispatcher is not None and response.kind == "detection_result":
                outcomes = alert_dispatcher.handle_detection_result(response.body)
                for outcome in outcomes:
                    print(
                        f"haptic {outcome.pattern} for {outcome.event}: "
                        f"{'delivered' if outcome.delivered else outcome.reason}"
                    )
                acknowledged = alert_dispatcher.poll_acknowledge()
                if outcomes or acknowledged or chunk.sequence % 10 == 0:
                    await write_message(
                        writer,
                        WireMessage(
                            "haptic_result",
                            {
                                "sequence": chunk.sequence,
                                "outcomes": [outcome.to_wire() for outcome in outcomes],
                                "acknowledged": acknowledged,
                                "health": alert_dispatcher.health_snapshot(),
                            },
                        ),
                    )
            _print_result(chunk, edge.to_wire(), response.body, compact)
    finally:
        writer.close()
        await writer.wait_closed()


async def stream_wav(
    path: Path,
    endpoints: list[Endpoint],
    preference: RoutingPreference,
    device_id: str,
    pairing_token: str,
    phrase_triggers: list[str],
    chunk_ms: int,
    realtime: bool,
    compact: bool = False,
    alert_dispatcher: AlertDispatcher | None = None,
) -> None:
    await stream_chunks(
        iter_wav_chunks(path, chunk_ms=chunk_ms, realtime=realtime),
        endpoints,
        preference,
        device_id,
        pairing_token,
        phrase_triggers,
        compact=compact,
        alert_dispatcher=alert_dispatcher,
    )


async def stream_microphone(
    alsa_device: str,
    endpoints: list[Endpoint],
    preference: RoutingPreference,
    device_id: str,
    pairing_token: str,
    phrase_triggers: list[str],
    chunk_ms: int,
    max_chunks: int | None,
    compact: bool,
    alert_dispatcher: AlertDispatcher | None = None,
) -> None:
    source = AlsaPcmSource(alsa_device, chunk_ms=chunk_ms)
    print(
        f"Capturing {SAMPLE_RATE} Hz mono PCM16 from {alsa_device} "
        f"in {chunk_ms} ms chunks; raw audio is not stored."
    )
    with source:
        await stream_chunks(
            source.iter_chunks(max_chunks=max_chunks),
            endpoints,
            preference,
            device_id,
            pairing_token,
            phrase_triggers,
            compact=compact,
            alert_dispatcher=alert_dispatcher,
        )


async def run_microphone_client(
    alsa_device: str,
    endpoints: list[Endpoint],
    preference: RoutingPreference,
    device_id: str,
    pairing_token: str,
    phrase_triggers: list[str],
    chunk_ms: int,
    max_chunks: int | None,
    compact: bool,
    alert_dispatcher: AlertDispatcher | None,
    *,
    reconnect: bool,
) -> None:
    """Keep a live microphone session connected with bounded backoff."""
    backoff_seconds = 1.0
    while True:
        try:
            await stream_microphone(
                alsa_device,
                endpoints,
                preference,
                device_id,
                pairing_token,
                phrase_triggers,
                chunk_ms,
                max_chunks,
                compact,
                alert_dispatcher=alert_dispatcher,
            )
            return
        except (
            AlsaCaptureError,
            NoHubAvailable,
            OSError,
            ProtocolError,
            asyncio.IncompleteReadError,
            asyncio.TimeoutError,
        ) as exc:
            if not reconnect or max_chunks is not None:
                raise
            print(
                f"Live session unavailable ({type(exc).__name__}: {exc}); "
                f"retrying in {backoff_seconds:.0f}s",
                flush=True,
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(backoff_seconds * 2, 30.0)


def _print_edge_only(
    chunks: Iterable[AudioChunk],
    analyzer: EdgeAudioAnalyzer,
    compact: bool,
) -> None:
    for chunk in chunks:
        edge = analyzer.analyze_pcm16(chunk.pcm).to_wire()
        if compact:
            print(
                f"seq={chunk.sequence} rms={edge['rms_dbfs']}dBFS "
                f"peak={edge['peak_dbfs']}dBFS voice={edge['voice_activity']}"
            )
        else:
            print(json.dumps({**chunk.to_wire(), "edge_analysis": edge}, indent=2))


def _print_result(
    chunk: AudioChunk,
    edge: dict[str, object],
    response: dict[str, object],
    compact: bool,
) -> None:
    if not compact:
        print(json.dumps(response, indent=2))
        return
    events = response.get("events", [])
    alerts = response.get("alerts", [])
    event_names = [str(item.get("event")) for item in events if isinstance(item, dict)]
    alert_names = [str(item.get("event")) for item in alerts if isinstance(item, dict)]
    transcript = response.get("transcript")
    print(
        f"seq={chunk.sequence} rms={edge['rms_dbfs']}dBFS voice={response.get('voice_detected', False)} "
        f"events={event_names or '-'} "
        f"inference={response.get('inference_source', 'connected_hub')} "
        f"alerts={alert_names or '-'}"
        + (f" transcript={transcript!r}" if transcript else "")
    )


def _endpoint(value: str, kind: HubKind, node_id: str) -> Endpoint:
    host, separator, port_text = value.rpartition(":")
    if not separator or not host:
        raise argparse.ArgumentTypeError("Endpoint must be HOST:PORT")
    return Endpoint(node_id=node_id, kind=kind, host=host, port=int(port_text))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav_file", type=Path, nargs="?", help="Validated WAV replay source")
    parser.add_argument(
        "--microphone",
        action="store_true",
        help="Capture continuously from an ALSA microphone instead of replaying a WAV",
    )
    parser.add_argument(
        "--input-device",
        default=DEFAULT_ALSA_DEVICE,
        help=f"ALSA capture device (default: {DEFAULT_ALSA_DEVICE})",
    )
    parser.add_argument(
        "--list-microphones",
        action="store_true",
        help="List ALSA capture hardware and exit",
    )
    parser.add_argument("--pc", help="Copilot hub as HOST:PORT")
    parser.add_argument("--phone", help="Samsung hub as HOST:PORT")
    parser.add_argument(
        "--preference",
        choices=[preference.value for preference in RoutingPreference],
        default=RoutingPreference.AUTO.value,
    )
    parser.add_argument("--device-id", default="uno-q-dev")
    parser.add_argument(
        "--pairing-token",
        default=os.environ.get("QUIETCUE_PAIRING_TOKEN", ""),
        help="Hub pairing token; defaults to the QUIETCUE_PAIRING_TOKEN environment variable",
    )
    parser.add_argument("--phrase", action="append", default=[])
    parser.add_argument("--chunk-ms", type=int, default=500)
    parser.add_argument(
        "--max-chunks",
        type=int,
        help="Stop after this many chunks; useful for a microphone health check",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print one health/result line per chunk instead of full JSON",
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Pace chunks like live capture instead of replaying as fast as possible",
    )
    parser.add_argument(
        "--haptics",
        action="store_true",
        help="Dispatch hub alerts through the Uno Q App Lab Bridge to the STM32",
    )
    parser.add_argument(
        "--haptics-container",
        help="Override the App Lab container name (normally auto-detected)",
    )
    parser.add_argument(
        "--no-reconnect",
        action="store_true",
        help="Exit instead of reconnecting after a live microphone or hub failure",
    )
    return parser.parse_args()


def _now_ms() -> int:
    return int(time.monotonic() * 1_000)


def main() -> None:
    args = _parse_args()
    if args.list_microphones:
        print(list_capture_hardware())
        return
    if args.microphone == (args.wav_file is not None):
        raise SystemExit("Choose exactly one source: WAV_FILE or --microphone")
    if args.max_chunks is not None and args.max_chunks < 1:
        raise SystemExit("--max-chunks must be positive")
    endpoints: list[Endpoint] = []
    if args.pc:
        endpoints.append(_endpoint(args.pc, HubKind.COPILOT_PC, "configured-pc"))
    if args.phone:
        endpoints.append(_endpoint(args.phone, HubKind.SAMSUNG_PHONE, "configured-phone"))
    dispatcher = None
    if args.haptics:
        haptic_transport = AppLabBridgeHapticTransport(args.haptics_container)
        if not haptic_transport.health_check():
            raise SystemExit("STM32 haptic firmware health check failed")
        print(f"Haptic Bridge ready: {haptic_transport.firmware_version()}")
        dispatcher = AlertDispatcher(haptic_transport)
    if args.microphone:
        asyncio.run(
            run_microphone_client(
                args.input_device,
                endpoints,
                RoutingPreference(args.preference),
                args.device_id,
                args.pairing_token,
                args.phrase,
                args.chunk_ms,
                args.max_chunks,
                args.compact,
                dispatcher,
                reconnect=not args.no_reconnect,
            )
        )
    else:
        asyncio.run(
            stream_wav(
                args.wav_file,
                endpoints,
                RoutingPreference(args.preference),
                args.device_id,
                args.pairing_token,
                args.phrase,
                args.chunk_ms,
                args.realtime,
                args.compact,
                alert_dispatcher=dispatcher,
            )
        )


if __name__ == "__main__":
    main()
