"""Minimal HTTP state and profile-sync endpoint for the Android development app."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any


class StatusHttpServer:
    def __init__(
        self,
        snapshot: Callable[[], dict[str, Any]],
        update_profile: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        stop_haptic: Callable[[str | None], dict[str, Any]] | None = None,
        start_enrollment: Callable[[int], dict[str, Any]] | None = None,
        enrollment_status: Callable[[], dict[str, Any]] | None = None,
        cancel_enrollment: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._update_profile = update_profile
        self._stop_haptic = stop_haptic
        self._start_enrollment = start_enrollment
        self._enrollment_status = enrollment_status
        self._cancel_enrollment = cancel_enrollment

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2.0)
            header_lines = request.decode("ascii", errors="replace").split("\r\n")
            request_line = header_lines[0]
            method, target, _ = request_line.split(" ", 2)
            path = target.rstrip("/")
            if method == "GET" and path == "/api/state":
                await self._respond(writer, 200, self._snapshot())
            elif method == "GET" and path == "/health":
                await self._respond(writer, 200, {"status": "ok"})
            elif (
                method == "GET"
                and path == "/api/enrollment/status"
                and self._enrollment_status is not None
            ):
                await self._respond(writer, 200, self._enrollment_status())
            elif method == "PUT" and path == "/api/state" and self._update_profile is not None:
                content_length = _content_length(header_lines[1:])
                if content_length < 2 or content_length > 256 * 1024:
                    raise ValueError("Profile document has an invalid size")
                body = await reader.readexactly(content_length)
                document = json.loads(body)
                if not isinstance(document, dict):
                    raise ValueError("Profile document must be an object")
                await self._respond(writer, 200, self._update_profile(document))
            elif method == "POST" and path == "/api/haptics/stop" and self._stop_haptic is not None:
                content_length = _content_length(header_lines[1:])
                if content_length > 16 * 1024:
                    raise ValueError("Stop command has an invalid size")
                document: dict[str, Any] = {}
                if content_length:
                    body = await reader.readexactly(content_length)
                    decoded = json.loads(body)
                    if not isinstance(decoded, dict):
                        raise ValueError("Stop command must be an object")
                    document = decoded
                event_id = document.get("event_id")
                if event_id is not None and not isinstance(event_id, str):
                    raise ValueError("event_id must be a string")
                await self._respond(writer, 200, self._stop_haptic(event_id))
            elif (
                method == "POST"
                and path == "/api/enrollment/start"
                and self._start_enrollment is not None
            ):
                content_length = _content_length(header_lines[1:])
                if content_length > 4 * 1024:
                    raise ValueError("Enrollment command has an invalid size")
                document: dict[str, Any] = {}
                if content_length:
                    body = await reader.readexactly(content_length)
                    decoded = json.loads(body)
                    if not isinstance(decoded, dict):
                        raise ValueError("Enrollment command must be an object")
                    document = decoded
                duration_ms = document.get("duration_ms", 10_000)
                if not isinstance(duration_ms, int):
                    raise ValueError("duration_ms must be an integer")
                await self._respond(writer, 200, self._start_enrollment(duration_ms))
            elif (
                method == "POST"
                and path == "/api/enrollment/cancel"
                and self._cancel_enrollment is not None
            ):
                await self._respond(writer, 200, self._cancel_enrollment())
            elif method not in {"GET", "PUT", "POST"}:
                await self._respond(writer, 405, {"error": "method_not_allowed"})
            else:
                await self._respond(writer, 404, {"error": "not_found"})
        except (
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
        ):
            await self._respond(writer, 400, {"error": "bad_request"})
        finally:
            writer.close()
            await writer.wait_closed()

    async def _respond(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        document: dict[str, Any],
    ) -> None:
        reason = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}[status]
        body = json.dumps(document, separators=(",", ":")).encode("utf-8")
        headers = (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(headers + body)
        await writer.drain()


def _content_length(header_lines: list[str]) -> int:
    for line in header_lines:
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() == "content-length":
            return int(value.strip())
    return 0
