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
        self._latest_haptic_result: dict[str, Any] | None = None
        self._haptic_devices: dict[str, dict[str, Any]] = {}

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

    def record_haptic_result(self, device_id: str, result: dict[str, Any]) -> None:
        """Record hardware delivery metadata and mark delivered alerts as real."""
        now_ms = int(time.time() * 1_000)
        outcomes_value = result.get("outcomes", [])
        outcomes = [item for item in outcomes_value if isinstance(item, dict)] if isinstance(
            outcomes_value, list
        ) else []
        health = result.get("health") if isinstance(result.get("health"), dict) else {}
        document = {
            "device_id": device_id,
            "sequence": result.get("sequence"),
            "outcomes": outcomes,
            "acknowledged": bool(result.get("acknowledged", False)),
            "health": health,
            "received_at_ms": now_ms,
        }
        self._latest_haptic_result = document
        self._haptic_devices[device_id] = document

        delivered_by_id = {
            str(item.get("event_id")): item
            for item in outcomes
            if item.get("delivered") is True and item.get("event_id")
        }
        if not delivered_by_id:
            return
        for alert in self._recent_alerts:
            event_id = str(alert.get("event_id", ""))
            outcome = delivered_by_id.get(event_id)
            if outcome is None:
                continue
            alert["simulated"] = False
            alert["haptic_delivery"] = {
                "device_id": device_id,
                "pattern": outcome.get("pattern"),
                "delivered_at_ms": now_ms,
            }

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
            "haptics": {
                "connected_device_ids": [
                    device_id for device_id in device_ids if device_id in self._haptic_devices
                ],
                "latest_result": self._latest_haptic_result,
                "devices": dict(self._haptic_devices),
            },
        }

    def _append_jsonl(self, document: dict[str, Any]) -> None:
        if self._jsonl_path is None:
            return
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self._jsonl_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(document, sort_keys=True) + "\n")
