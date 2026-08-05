"""Uno Q WAV-stream client used before live microphone capture is connected."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path

from backend.audio.wav_source import SAMPLE_RATE, iter_wav_chunks
from backend.communication.stream_protocol import WireMessage, read_message, write_message
from uno_q.linux.audio_capture.edge_analyzer import EdgeAudioAnalyzer
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


async def stream_wav(
    path: Path,
    endpoints: list[Endpoint],
    preference: RoutingPreference,
    device_id: str,
    pairing_token: str,
    phrase_triggers: list[str],
    chunk_ms: int,
    realtime: bool,
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
        print("No eligible hub is connected; showing Uno Q edge candidates only.")
        _print_edge_only(path, chunk_ms, analyzer)
        return

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

        for chunk in iter_wav_chunks(path, chunk_ms=chunk_ms, realtime=realtime):
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
            print(json.dumps(response.body, indent=2))
    finally:
        writer.close()
        await writer.wait_closed()


def _print_edge_only(path: Path, chunk_ms: int, analyzer: EdgeAudioAnalyzer) -> None:
    for chunk in iter_wav_chunks(path, chunk_ms=chunk_ms):
        print(
            json.dumps(
                {**chunk.to_wire(), "edge_analysis": analyzer.analyze_pcm16(chunk.pcm).to_wire()},
                indent=2,
            )
        )


def _endpoint(value: str, kind: HubKind, node_id: str) -> Endpoint:
    host, separator, port_text = value.rpartition(":")
    if not separator or not host:
        raise argparse.ArgumentTypeError("Endpoint must be HOST:PORT")
    return Endpoint(node_id=node_id, kind=kind, host=host, port=int(port_text))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream a WAV from Uno Q to the selected hub")
    parser.add_argument("wav_file", type=Path)
    parser.add_argument("--pc", help="Copilot hub as HOST:PORT")
    parser.add_argument("--phone", help="Samsung hub as HOST:PORT")
    parser.add_argument(
        "--preference",
        choices=[preference.value for preference in RoutingPreference],
        default=RoutingPreference.AUTO.value,
    )
    parser.add_argument("--device-id", default="uno-q-dev")
    parser.add_argument("--pairing-token", default="")
    parser.add_argument("--phrase", action="append", default=[])
    parser.add_argument("--chunk-ms", type=int, default=500)
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Pace chunks like live capture instead of replaying as fast as possible",
    )
    return parser.parse_args()


def _now_ms() -> int:
    return int(time.monotonic() * 1_000)


def main() -> None:
    args = _parse_args()
    endpoints: list[Endpoint] = []
    if args.pc:
        endpoints.append(_endpoint(args.pc, HubKind.COPILOT_PC, "configured-pc"))
    if args.phone:
        endpoints.append(_endpoint(args.phone, HubKind.SAMSUNG_PHONE, "configured-phone"))
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
        )
    )


if __name__ == "__main__":
    main()
