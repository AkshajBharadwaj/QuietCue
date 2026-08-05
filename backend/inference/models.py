"""Shared inference value objects with no model-runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoundPrediction:
    """One sound class predicted by an environmental classifier."""

    label: str
    confidence: float
