"""Metadata-only discovery of recurring classifier labels QuietCue does not map yet."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


DEFAULT_MINIMUM_CONFIDENCE = 0.35
DEFAULT_EPISODE_GAP_MS = 3_000
DEFAULT_MINIMUM_EPISODES = 3
LOGGER = logging.getLogger("quietcue.sound_discovery")


_GENERIC_LABEL_TERMS = (
    "conversation",
    "field recording",
    "inside,",
    "music",
    "narration",
    "noise",
    "outside,",
    "silence",
    "sound effect",
    "speech",
)


@dataclass
class _CandidateState:
    candidate_id: str
    label: str
    normalized_label: str
    first_seen_ms: int
    last_seen_ms: int
    last_episode_started_ms: int
    episodes: int
    episode_confidence_total: float
    current_episode_peak: float
    max_confidence: float
    profile_names: set[str] = field(default_factory=set)

    def observe(self, confidence: float, observed_at_ms: int, profile_name: str, gap_ms: int) -> bool:
        new_episode = False
        if observed_at_ms - self.last_seen_ms > gap_ms:
            self.episodes += 1
            self.episode_confidence_total += confidence
            self.current_episode_peak = confidence
            self.last_episode_started_ms = observed_at_ms
            new_episode = True
        elif confidence > self.current_episode_peak:
            self.episode_confidence_total += confidence - self.current_episode_peak
            self.current_episode_peak = confidence
        self.last_seen_ms = max(self.last_seen_ms, observed_at_ms)
        self.max_confidence = max(self.max_confidence, confidence)
        if profile_name:
            self.profile_names.add(profile_name)
        return new_episode


class SoundDiscoveryTracker:
    """Group consecutive unknown predictions into reviewable sound episodes.

    The tracker receives classifier metadata only. It never receives or retains
    PCM, and it deliberately ignores broad labels that would create noisy or
    privacy-sensitive suggestions such as Speech, Music, and generic Noise.
    """

    def __init__(
        self,
        *,
        minimum_confidence: float = DEFAULT_MINIMUM_CONFIDENCE,
        episode_gap_ms: int = DEFAULT_EPISODE_GAP_MS,
        minimum_episodes: int = DEFAULT_MINIMUM_EPISODES,
        state_path: str | Path | None = None,
    ) -> None:
        if not 0.0 <= minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if episode_gap_ms < 1:
            raise ValueError("episode_gap_ms must be positive")
        if minimum_episodes < 1:
            raise ValueError("minimum_episodes must be positive")
        self.minimum_confidence = minimum_confidence
        self.episode_gap_ms = episode_gap_ms
        self.minimum_episodes = minimum_episodes
        self.state_path = Path(state_path) if state_path is not None else None
        self._candidates: dict[str, _CandidateState] = {}
        self._dismissed_ids: set[str] = set()
        self._load()

    def observe(
        self,
        predictions: Sequence[Mapping[str, object]],
        *,
        mapped_source_labels: Iterable[str] = (),
        profile_name: str,
        observed_at_ms: int,
        custom_sound_matched: bool = False,
    ) -> None:
        if custom_sound_matched:
            return
        mapped = {_normalize_label(label) for label in mapped_source_labels}
        seen_in_window: set[str] = set()
        should_persist = False
        for prediction in predictions:
            label_value = prediction.get("label")
            confidence_value = prediction.get("confidence")
            if not isinstance(label_value, str) or isinstance(confidence_value, bool):
                continue
            if not isinstance(confidence_value, (int, float)):
                continue
            label = label_value.strip()
            normalized = _normalize_label(label)
            confidence = float(confidence_value)
            if (
                not normalized
                or normalized in seen_in_window
                or normalized in mapped
                or not math.isfinite(confidence)
                or confidence < self.minimum_confidence
                or _is_generic_label(normalized)
            ):
                continue
            seen_in_window.add(normalized)
            candidate_id = _candidate_id(normalized)
            if candidate_id in self._dismissed_ids:
                continue
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                self._candidates[candidate_id] = _CandidateState(
                    candidate_id=candidate_id,
                    label=label,
                    normalized_label=normalized,
                    first_seen_ms=observed_at_ms,
                    last_seen_ms=observed_at_ms,
                    last_episode_started_ms=observed_at_ms,
                    episodes=1,
                    episode_confidence_total=confidence,
                    current_episode_peak=confidence,
                    max_confidence=confidence,
                    profile_names={profile_name} if profile_name else set(),
                )
                should_persist = True
            else:
                should_persist = candidate.observe(
                    confidence,
                    observed_at_ms,
                    profile_name,
                    self.episode_gap_ms,
                ) or should_persist
        if should_persist:
            self._save()

    def dismiss(self, candidate_id: str) -> bool:
        candidate = self._candidates.pop(candidate_id, None)
        if candidate is None:
            return False
        self._dismissed_ids.add(candidate_id)
        self._save()
        return True

    def candidates(self) -> list[dict[str, object]]:
        ready = [
            candidate
            for candidate in self._candidates.values()
            if candidate.episodes >= self.minimum_episodes
        ]
        ready.sort(key=lambda item: (item.episodes, item.last_seen_ms), reverse=True)
        return [self._to_wire(candidate) for candidate in ready]

    def pending_count(self) -> int:
        return sum(
            candidate.episodes < self.minimum_episodes
            for candidate in self._candidates.values()
        )

    def _to_wire(self, candidate: _CandidateState) -> dict[str, object]:
        return {
            "id": candidate.candidate_id,
            "label": candidate.label,
            "episodes": candidate.episodes,
            "first_seen_ms": candidate.first_seen_ms,
            "last_seen_ms": candidate.last_seen_ms,
            "mean_confidence": round(
                candidate.episode_confidence_total / candidate.episodes,
                4,
            ),
            "max_confidence": round(candidate.max_confidence, 4),
            "profile_names": sorted(candidate.profile_names),
            "suggested_action": "enroll",
        }

    def _load(self) -> None:
        if self.state_path is None or not self.state_path.is_file():
            return
        try:
            document = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(document, dict) or document.get("version") != 1:
                raise ValueError("Unsupported discovery-state version")
            dismissed = document.get("dismissed_ids", [])
            candidates = document.get("candidates", [])
            if not isinstance(dismissed, list) or not isinstance(candidates, list):
                raise ValueError("Invalid discovery-state document")
            self._dismissed_ids = {
                item for item in dismissed if isinstance(item, str) and item.startswith("disc_")
            }
            for item in candidates:
                candidate = _decode_candidate(item)
                if candidate is not None and candidate.candidate_id not in self._dismissed_ids:
                    self._candidates[candidate.candidate_id] = candidate
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.warning("Ignoring invalid Sound Scout state at %s: %s", self.state_path, exc)

    def _save(self) -> None:
        if self.state_path is None:
            return
        document = {
            "version": 1,
            "candidates": [_encode_candidate(candidate) for candidate in self._candidates.values()],
            "dismissed_ids": sorted(self._dismissed_ids),
        }
        temporary_path = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(
                json.dumps(document, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(self.state_path)
        except OSError as exc:
            LOGGER.warning("Could not persist Sound Scout state at %s: %s", self.state_path, exc)


def _encode_candidate(candidate: _CandidateState) -> dict[str, object]:
    return {
        "id": candidate.candidate_id,
        "label": candidate.label,
        "normalized_label": candidate.normalized_label,
        "first_seen_ms": candidate.first_seen_ms,
        "last_seen_ms": candidate.last_seen_ms,
        "last_episode_started_ms": candidate.last_episode_started_ms,
        "episodes": candidate.episodes,
        "episode_confidence_total": candidate.episode_confidence_total,
        "current_episode_peak": candidate.current_episode_peak,
        "max_confidence": candidate.max_confidence,
        "profile_names": sorted(candidate.profile_names),
    }


def _decode_candidate(value: object) -> _CandidateState | None:
    if not isinstance(value, dict):
        return None
    try:
        label = value["label"]
        normalized = value["normalized_label"]
        profile_names = value.get("profile_names", [])
        if (
            not isinstance(label, str)
            or not isinstance(normalized, str)
            or _normalize_label(label) != normalized
            or not isinstance(profile_names, list)
        ):
            return None
        candidate_id = _candidate_id(normalized)
        if value.get("id") != candidate_id:
            return None
        episodes = int(value["episodes"])
        confidences = (
            float(value["episode_confidence_total"]),
            float(value["current_episode_peak"]),
            float(value["max_confidence"]),
        )
        if episodes < 1 or not all(math.isfinite(item) and item >= 0.0 for item in confidences):
            return None
        return _CandidateState(
            candidate_id=candidate_id,
            label=label,
            normalized_label=normalized,
            first_seen_ms=int(value["first_seen_ms"]),
            last_seen_ms=int(value["last_seen_ms"]),
            last_episode_started_ms=int(value["last_episode_started_ms"]),
            episodes=episodes,
            episode_confidence_total=confidences[0],
            current_episode_peak=confidences[1],
            max_confidence=confidences[2],
            profile_names={
                item for item in profile_names if isinstance(item, str) and 0 < len(item) <= 40
            },
        )
    except (KeyError, TypeError, ValueError):
        return None


def _normalize_label(label: str) -> str:
    return " ".join(label.strip().lower().split())


def _candidate_id(normalized_label: str) -> str:
    digest = hashlib.sha256(normalized_label.encode("utf-8")).hexdigest()[:12]
    return f"disc_{digest}"


def _is_generic_label(normalized_label: str) -> bool:
    return any(term in normalized_label for term in _GENERIC_LABEL_TERMS)
