"""Forward QuietCue audio frames to the Samsung on-device inference server."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.communication.stream_protocol import WireMessage, read_message, write_message


@dataclass(frozen=True)
class SamsungEndpoint:
    host: str
    port: int

    @classmethod
    def parse(cls, value: str) -> "SamsungEndpoint":
        host, separator, port_text = value.rpartition(":")
        if not separator or not host:
            raise ValueError("Samsung endpoint must be HOST:PORT")
        port = int(port_text)
        if port not in range(1, 65_536):
            raise ValueError("Samsung endpoint port is out of range")
        return cls(host, port)


class SamsungInferenceProxy:
    """Maintain one authenticated stream to the phone and forward audio serially."""

    def __init__(
        self,
        endpoint: SamsungEndpoint,
        pairing_token: str,
        *,
        connect_timeout_seconds: float = 2.0,
        response_timeout_seconds: float = 8.0,
    ) -> None:
        self.endpoint = endpoint
        self._pairing_token = pairing_token
        self._connect_timeout_seconds = connect_timeout_seconds
        self._response_timeout_seconds = response_timeout_seconds
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def infer(self, message: WireMessage) -> dict[str, object]:
        if message.kind != "audio_chunk":
            raise ValueError("Only audio chunks can be forwarded to Samsung inference")
        async with self._lock:
            for attempt in range(2):
                try:
                    await self._ensure_connected()
                    assert self._reader is not None and self._writer is not None
                    await write_message(self._writer, message)
                    response = await asyncio.wait_for(
                        read_message(self._reader),
                        timeout=self._response_timeout_seconds,
                    )
                    if response.kind != "detection_result":
                        raise ConnectionError(
                            f"Samsung returned {response.kind} instead of detection_result"
                        )
                    return response.body
                except (OSError, ConnectionError, asyncio.TimeoutError, asyncio.IncompleteReadError):
                    await self._disconnect()
                    if attempt:
                        raise
            raise ConnectionError("Samsung inference is unavailable")

    async def close(self) -> None:
        async with self._lock:
            await self._disconnect()

    async def _ensure_connected(self) -> None:
        if self._reader is not None and self._writer is not None and not self._writer.is_closing():
            return
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.endpoint.host, self.endpoint.port),
            timeout=self._connect_timeout_seconds,
        )
        try:
            await write_message(
                writer,
                WireMessage(
                    "edge_hello",
                    {
                        "device_id": "quietcue-pc-forwarder",
                        "protocol": 1,
                        "pairing_token": self._pairing_token,
                    },
                ),
            )
            hello = await asyncio.wait_for(
                read_message(reader),
                timeout=self._connect_timeout_seconds,
            )
            if hello.kind != "hub_hello" or hello.body.get("kind") != "samsung_phone":
                raise ConnectionError("Endpoint is not a QuietCue Samsung inference server")
        except BaseException:
            writer.close()
            await writer.wait_closed()
            raise
        self._reader = reader
        self._writer = writer

    async def _disconnect(self) -> None:
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            writer.close()
            await writer.wait_closed()
