"""In-memory, metadata-only state shared with the Android dashboard."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.inference.pipeline import HubInferenceResult
from backend.profiles.engine import AlertProfile, DecisionResult
from backend.telemetry.sound_discovery import SoundDiscoveryTracker


class AlertStateStore:
    """Keep recent event metadata without retaining raw audio."""

    def __init__(
        self,
        profile: AlertProfile,
        jsonl_path: Path | None = None,
        discovery_tracker: SoundDiscoveryTracker | None = None,
    ) -> None:
        self._profile = profile
        self._jsonl_path = jsonl_path
        self._sessions: dict[str, str] = {}
        self._latest_result: dict[str, Any] | None = None
        self._latest_alert: dict[str, Any] | None = None
        self._recent_alerts: list[dict[str, Any]] = []
        self._last_audio_at_ms: int | None = None
        self._latest_haptic_result: dict[str, Any] | None = None
        self._haptic_devices: dict[str, dict[str, Any]] = {}
        self._recent_observations: list[dict[str, Any]] = []
        self._discovery_tracker = discovery_tracker or SoundDiscoveryTracker()

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
        *,
        captured_at_ms: int | None = None,
    ) -> None:
        now_ms = int(time.time() * 1_000)
        observed_at_ms = captured_at_ms if captured_at_ms is not None else now_ms
        self._last_audio_at_ms = now_ms
        self._latest_result = {"sequence": sequence, **inference.to_wire(), "received_at_ms": now_ms}
        observation = {
            "sequence": sequence,
            "captured_at_ms": observed_at_ms,
            "received_at_ms": now_ms,
            "profile": self._profile.summary(),
            "inference_source": inference.inference_source,
            "top_predictions": list(inference.top_predictions),
            "events": [asdict(event) for event in inference.events],
            "alerts": [alert.to_wire() for alert in decisions.alerts],
            "suppressed": [asdict(event) for event in decisions.suppressed],
        }
        self._recent_observations.insert(0, observation)
        del self._recent_observations[100:]
        self._discovery_tracker.observe(
            inference.top_predictions,
            mapped_source_labels=(event.source_label for event in inference.events),
            profile_name=self._profile.name,
            observed_at_ms=observed_at_ms,
            custom_sound_matched=any(event.event.startswith("custom:") for event in inference.events),
        )
        for alert in decisions.alerts:
            document = {
                **alert.to_wire(),
                "haptic_active": alert.requires_ack,
                "acknowledged_at_ms": None,
            }
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

        if document["acknowledged"] and self._latest_alert is not None:
            self._mark_haptic_stopped(
                str(self._latest_alert.get("event_id", "")),
                acknowledged_at_ms=now_ms,
            )

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

    def stop_haptic(self, event_id: str | None = None) -> dict[str, Any]:
        """Acknowledge the current alert and prepare a semantic device stop command."""
        if self._latest_alert is None:
            raise ValueError("There is no active alert to stop")
        current_event_id = str(self._latest_alert.get("event_id", ""))
        if event_id and event_id != current_event_id:
            raise ValueError("The requested alert is no longer active")
        acknowledged_at_ms = int(time.time() * 1_000)
        self._mark_haptic_stopped(current_event_id, acknowledged_at_ms=acknowledged_at_ms)
        self._append_jsonl(
            {
                "kind": "haptic_stopped",
                "event_id": current_event_id,
                "acknowledged_at_ms": acknowledged_at_ms,
            }
        )
        return {
            "event_id": current_event_id,
            "acknowledged_at_ms": acknowledged_at_ms,
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
            "recent_observations": list(self._recent_observations),
            "discoveries": {
                "candidates": self._discovery_tracker.candidates(),
                "pending_count": self._discovery_tracker.pending_count(),
            },
            "haptics": {
                "connected_device_ids": [
                    device_id for device_id in device_ids if device_id in self._haptic_devices
                ],
                "latest_result": self._latest_haptic_result,
                "devices": dict(self._haptic_devices),
            },
        }

    def update_discovery(self, candidate_id: str, action: str) -> dict[str, object]:
        if action not in {"dismiss", "taught"}:
            raise ValueError("Discovery action must be dismiss or taught")
        if not self._discovery_tracker.dismiss(candidate_id):
            raise ValueError("Unknown discovery candidate")
        return {"status": action, "candidate_id": candidate_id}

    def _mark_haptic_stopped(self, event_id: str, *, acknowledged_at_ms: int) -> None:
        if self._latest_alert is not None and self._latest_alert.get("event_id") == event_id:
            self._latest_alert["haptic_active"] = False
            self._latest_alert["acknowledged_at_ms"] = acknowledged_at_ms
        for alert in self._recent_alerts:
            if alert.get("event_id") == event_id:
                alert["haptic_active"] = False
                alert["acknowledged_at_ms"] = acknowledged_at_ms
                break

    def _append_jsonl(self, document: dict[str, Any]) -> None:
        if self._jsonl_path is None:
            return
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self._jsonl_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(document, sort_keys=True) + "\n")
