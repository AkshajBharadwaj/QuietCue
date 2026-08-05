"""Choose exactly one capable inference hub and hold a short route lease."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


SOUND_CONFIRMATION = "sound_confirmation"


class HubKind(str, Enum):
    COPILOT_PC = "copilot_pc"
    SAMSUNG_PHONE = "samsung_phone"


class RoutingPreference(str, Enum):
    AUTO = "auto"
    COPILOT_PC = "copilot_pc"
    SAMSUNG_PHONE = "samsung_phone"


@dataclass(frozen=True)
class HubCandidate:
    node_id: str
    kind: HubKind
    host: str
    port: int
    capabilities: frozenset[str]
    last_seen_ms: int
    round_trip_ms: int = 0

    @property
    def endpoint(self) -> tuple[str, int]:
        return self.host, self.port


@dataclass(frozen=True)
class HubLease:
    candidate: HubCandidate
    generation: int
    expires_at_ms: int


class HubSelector:
    """Prefer PC, fall back to phone, and prevent duplicate active hubs."""

    def __init__(self, heartbeat_timeout_ms: int = 6_000, lease_ms: int = 5_000) -> None:
        self.heartbeat_timeout_ms = heartbeat_timeout_ms
        self.lease_ms = lease_ms
        self._candidates: dict[str, HubCandidate] = {}
        self._lease: HubLease | None = None
        self._generation = 0

    def update(self, candidate: HubCandidate) -> None:
        self._candidates[candidate.node_id] = candidate

    def remove(self, node_id: str) -> None:
        self._candidates.pop(node_id, None)
        if self._lease and self._lease.candidate.node_id == node_id:
            self._lease = None

    def select(
        self,
        now_ms: int,
        preference: RoutingPreference = RoutingPreference.AUTO,
    ) -> HubLease | None:
        """Return a leased hub or None for Uno-Q-only fallback."""
        eligible = [
            candidate
            for candidate in self._candidates.values()
            if now_ms - candidate.last_seen_ms <= self.heartbeat_timeout_ms
            and SOUND_CONFIRMATION in candidate.capabilities
            and _matches_preference(candidate, preference)
        ]

        if self._lease and now_ms < self._lease.expires_at_ms:
            current = next(
                (candidate for candidate in eligible if candidate.node_id == self._lease.candidate.node_id),
                None,
            )
            if current is not None:
                self._lease = HubLease(current, self._lease.generation, now_ms + self.lease_ms)
                return self._lease

        if not eligible:
            self._lease = None
            return None

        selected = min(eligible, key=_rank)
        self._generation += 1
        self._lease = HubLease(
            candidate=selected,
            generation=self._generation,
            expires_at_ms=now_ms + self.lease_ms,
        )
        return self._lease


def _matches_preference(candidate: HubCandidate, preference: RoutingPreference) -> bool:
    if preference == RoutingPreference.AUTO:
        return True
    return candidate.kind.value == preference.value


def _rank(candidate: HubCandidate) -> tuple[int, int, str]:
    kind_priority = 0 if candidate.kind == HubKind.COPILOT_PC else 1
    return kind_priority, candidate.round_trip_ms, candidate.node_id
