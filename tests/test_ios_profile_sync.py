"""The iPhone app's profile-sync document must satisfy the hub's strict schema.

The fixture is produced by the Swift codec (`ProfileSyncCodecTests
.testWritesFixtureForHubDecoder` in `frontend/ios/QuietCueTests`), so this test
catches any drift between the Swift encoder and `backend/profiles/wire_codec.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.profiles.speech_context import SpeechMode
from backend.profiles.wire_codec import decode_profile


FIXTURE = Path(__file__).parent / "fixtures" / "ios_profile_sync.json"


def test_ios_profile_document_decodes_with_hub_codec() -> None:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    profile = decode_profile(document)

    assert profile.profile_id == "custom-test"
    assert profile.name == "Library visit"
    assert profile.speech_mode is SpeechMode.INHERIT
    assert profile.phrase_triggers == ("front desk", "Akshaj")
    assert len(profile.sound_rules) == 8

    fire_alarm = profile.rule_for("fire_alarm")
    assert fire_alarm is not None
    assert fire_alarm.pattern == "custom"
    assert fire_alarm.custom_pattern == "180,120;420,300"
    assert fire_alarm.category == "emergency"
    assert fire_alarm.requires_ack is True

    doorbell = profile.rule_for("doorbell_knock")
    assert doorbell is not None
    assert doorbell.confidence_threshold == 0.55

    context = profile.speech_context
    assert context.identity is not None and context.identity.name == "Akshaj"
    assert [person.name for person in context.people] == ["Maya"]
    assert [item.title for item in context.contexts] == ["Tuesday class"]
    assert context.settings.sensitivity == 0.65
    assert context.settings.global_phrases == ("excuse me",)
