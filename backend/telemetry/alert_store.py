"""In-memory, metadata-only state shared with the Android dashboard."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.inference.pipeline import HubInferenceResult
from backend.profiles.engine import AlertProfile, DecisionResult


class AlertStateStore:
    """Keep recent event metadata without retaining raw audio."""

    def __init__(self, profile: AlertProfile, jsonl_path: Path | None = None) -> None:
        self._profile = profile
        self._jsonl_path = jsonl_path
        self._sessions: dict[str, str] = {}
        self._latest_result: dict[str, Any] | None = None
        self._latest_alert: dict[str, Any] | None = None
        self._recent_alerts: list[dict[str, Any]] = []
        self._last_audio_at_ms: int | None = None

    def connected(self, session_id: str, device_id: str) -> None:
        self._sessions[session_id] = device_id

    def disconnected(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def set_profile(self, profile: AlertProfile) -> None:
        self._profile = profile

    def record(
        self,
        sequence: int,
        inference: HubInferenceResult,
        decisions: DecisionResult,
    ) -> None:
        now_ms = int(time.time() * 1_000)
        self._last_audio_at_ms = now_ms
        self._latest_result = {"sequence": sequence, **inference.to_wire(), "received_at_ms": now_ms}
        for alert in decisions.alerts:
            document = alert.to_wire()
            self._latest_alert = document
            self._recent_alerts.insert(0, document)
            del self._recent_alerts[20:]
            self._append_jsonl(document)

    def snapshot(self) -> dict[str, Any]:
        device_ids = sorted(set(self._sessions.values()))
        return {
            "status": "ready",
            "server_time_ms": int(time.time() * 1_000),
            "active_profile": self._profile.summary(),
            "hub": {
                "audio_source_connected": bool(self._sessions),
                "device_ids": device_ids,
                "last_audio_at_ms": self._last_audio_at_ms,
            },
            "latest_alert": self._latest_alert,
            "latest_result": self._latest_result,
            "recent_alerts": list(self._recent_alerts),
        }

    def _append_jsonl(self, document: dict[str, Any]) -> None:
        if self._jsonl_path is None:
            return
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self._jsonl_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(document, sort_keys=True) + "\n")
