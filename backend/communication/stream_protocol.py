"""Length-prefixed QuietCue messages for raw TCP audio streaming.

Each message contains a small JSON document and an optional binary payload. Audio
therefore stays as PCM bytes instead of expanding through JSON/base64 encoding.
"""

from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import dataclass
from typing import Any


MAGIC = b"QC01"
_PREFIX = struct.Struct("!4sII")
MAX_JSON_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 1024 * 1024


class ProtocolError(ValueError):
    """Raised when a peer sends an invalid or unsafe wire message."""


@dataclass(frozen=True)
class WireMessage:
    """One decoded QuietCue transport message."""

    kind: str
    body: dict[str, Any]
    payload: bytes = b""


def encode_message(message: WireMessage) -> bytes:
    """Encode a message into the complete on-wire frame."""
    if not message.kind:
        raise ProtocolError("Message kind cannot be empty")
    document = json.dumps(
        {"kind": message.kind, "body": message.body},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(document) > MAX_JSON_BYTES:
        raise ProtocolError("Message JSON is too large")
    if len(message.payload) > MAX_PAYLOAD_BYTES:
        raise ProtocolError("Message payload is too large")
    return _PREFIX.pack(MAGIC, len(document), len(message.payload)) + document + message.payload


def decode_message(frame: bytes) -> WireMessage:
    """Decode exactly one complete frame."""
    if len(frame) < _PREFIX.size:
        raise ProtocolError("Message is shorter than its prefix")
    magic, json_length, payload_length = _PREFIX.unpack_from(frame)
    _validate_lengths(magic, json_length, payload_length)
    expected_length = _PREFIX.size + json_length + payload_length
    if len(frame) != expected_length:
        raise ProtocolError(f"Expected {expected_length} bytes, received {len(frame)}")
    document_start = _PREFIX.size
    document_end = document_start + json_length
    return _decode_parts(frame[document_start:document_end], frame[document_end:])


async def read_message(reader: asyncio.StreamReader) -> WireMessage:
    """Read one complete message from an asyncio stream."""
    prefix = await reader.readexactly(_PREFIX.size)
    magic, json_length, payload_length = _PREFIX.unpack(prefix)
    _validate_lengths(magic, json_length, payload_length)
    document = await reader.readexactly(json_length)
    payload = await reader.readexactly(payload_length)
    return _decode_parts(document, payload)


async def write_message(writer: asyncio.StreamWriter, message: WireMessage) -> None:
    """Write and flush one message to an asyncio stream."""
    writer.write(encode_message(message))
    await writer.drain()


def _validate_lengths(magic: bytes, json_length: int, payload_length: int) -> None:
    if magic != MAGIC:
        raise ProtocolError("Unrecognized QuietCue protocol magic")
    if json_length < 2 or json_length > MAX_JSON_BYTES:
        raise ProtocolError(f"Invalid JSON length: {json_length}")
    if payload_length > MAX_PAYLOAD_BYTES:
        raise ProtocolError(f"Invalid payload length: {payload_length}")


def _decode_parts(document: bytes, payload: bytes) -> WireMessage:
    try:
        decoded = json.loads(document)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError("Message JSON is invalid") from exc
    if not isinstance(decoded, dict):
        raise ProtocolError("Message document must be an object")
    kind = decoded.get("kind")
    body = decoded.get("body")
    if not isinstance(kind, str) or not kind:
        raise ProtocolError("Message kind must be a non-empty string")
    if not isinstance(body, dict):
        raise ProtocolError("Message body must be an object")
    return WireMessage(kind=kind, body=body, payload=payload)
