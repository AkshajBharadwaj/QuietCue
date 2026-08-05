"""Minimal read-only HTTP state endpoint for the Android development app."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any


class StatusHttpServer:
    def __init__(self, snapshot: Callable[[], dict[str, Any]]) -> None:
        self._snapshot = snapshot

    async def handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2.0)
            request_line = request.split(b"\r\n", 1)[0].decode("ascii", errors="replace")
            method, target, _ = request_line.split(" ", 2)
            if method != "GET":
                await self._respond(writer, 405, {"error": "method_not_allowed"})
            elif target.rstrip("/") == "/api/state":
                await self._respond(writer, 200, self._snapshot())
            elif target.rstrip("/") == "/health":
                await self._respond(writer, 200, {"status": "ok"})
            else:
                await self._respond(writer, 404, {"error": "not_found"})
        except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
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
