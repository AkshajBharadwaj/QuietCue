"""The built-in sound vocabulary, defined by what YAMNet reliably detects.

September 2026: the catalog was rebuilt from measurements on real recordings
(ESC-50 and Wikimedia Commons clips through the float YAMNet export, 1 s
chunks). Each entry lists the AudioSet labels it is confirmed from:

* ``labels`` are matched as substrings of the lowercased YAMNet label, so
  "siren" also covers "Police car (siren)". They need the low specific floor.
* ``exact_labels`` are generic parents the model often emits instead of the
  child ("Alarm", "Telephone", "Door"). Matched on the whole label only and
  gated by a higher floor.
* ``excluded_labels`` are substring hits that must not count ("Engine
  knocking" for the knock).

The iOS ``SoundType`` enum mirrors this table; ids must match exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SoundEvent:
    event: str
    display_name: str
    description: str
    # "emergency" (urgent repeat, acknowledge), "attention" (long pulse) or
    # "informational" (two short) by default; profiles may override.
    category: str
    safety_critical: bool = False
    labels: tuple[str, ...] = ()
    exact_labels: tuple[str, ...] = ()
    excluded_labels: tuple[str, ...] = ()


CATALOG: tuple[SoundEvent, ...] = (
    SoundEvent(
        "alarm",
        "Alarm",
        "Smoke and fire alarms, alarm clocks, buzzers and other alarm tones",
        "emergency",
        safety_critical=True,
        labels=("fire alarm", "smoke detector", "alarm clock"),
        exact_labels=("alarm", "buzzer"),
    ),
    SoundEvent(
        "siren",
        "Siren",
        "Police, ambulance, fire-engine and civil-defense sirens",
        "emergency",
        safety_critical=True,
        # "Emergency vehicle" scored 0.64-0.70 on plain car horns; left out.
        labels=("siren",),
    ),
    SoundEvent(
        "loud_bang",
        "Loud bang",
        "Explosions, gunshots, fireworks and firecrackers",
        "attention",
        safety_critical=True,
        labels=("explosion", "gunshot", "fireworks", "firecracker"),
        exact_labels=("bang",),
    ),
    SoundEvent(
        "glass_breaking",
        "Glass breaking",
        "Shattering or breaking glass",
        "attention",
        safety_critical=True,
        labels=("shatter",),
        exact_labels=("glass", "breaking"),
    ),
    SoundEvent(
        "car_horn",
        "Car horn",
        "Nearby vehicle horns and warning honks",
        "attention",
        safety_critical=True,
        labels=("vehicle horn", "car horn", "honking", "air horn", "truck horn", "toot"),
    ),
    SoundEvent(
        "doorbell_knock",
        "Doorbell or knock",
        "Door chimes, apartment buzzers and knocking at a nearby door",
        "attention",
        labels=("doorbell", "ding-dong", "knock"),
        exact_labels=("door",),
        excluded_labels=("engine knocking",),
    ),
    SoundEvent(
        "bell",
        "Bell or chime",
        "Church bells, hand bells and chimes, including bell-type doorbells",
        "attention",
        labels=("church bell",),
        exact_labels=("bell", "chime"),
    ),
    SoundEvent(
        "phone_ringing",
        "Phone ringing",
        "Classic phone rings and ringtones (musical ringtones are often missed)",
        "attention",
        labels=("telephone bell ringing", "ringtone"),
        exact_labels=("telephone",),
    ),
    SoundEvent(
        "baby_crying",
        "Baby crying",
        "Infant crying and sobbing nearby",
        "attention",
        labels=("baby cry", "infant cry", "crying, sobbing"),
        exact_labels=("whimper",),
    ),
    SoundEvent(
        "name_called",
        "Name or phrase called",
        "Speech containing one of your configured phrases",
        "attention",
    ),
    SoundEvent(
        "dog_bark",
        "Dog barking",
        "Barking, howling and growling dogs",
        "attention",
        labels=("bark", "howl", "growling", "bow-wow", "yip"),
        exact_labels=("dog",),
    ),
    SoundEvent(
        "cat",
        "Cat",
        "Meowing, purring and caterwauling cats",
        "attention",
        labels=("meow", "purr", "caterwaul"),
        exact_labels=("cat",),
    ),
    SoundEvent(
        "appliance_beep",
        "Appliance beeps",
        "Microwave, timer, washer and other appliance beeps",
        "informational",
        labels=("beep, bleep",),
    ),
    SoundEvent(
        "thunder",
        "Thunder",
        "Thunder and thunderstorms",
        "attention",
        labels=("thunder",),
    ),
    SoundEvent(
        "train",
        "Train",
        "Trains, train horns and whistles, rail transport",
        "attention",
        labels=("train", "rail transport"),
    ),
    SoundEvent(
        "clapping",
        "Clapping or applause",
        "Hand clapping and applause, often used to get attention",
        "informational",
        labels=("clapping", "applause"),
    ),
    SoundEvent(
        "cough",
        "Coughing",
        "Coughing and throat clearing nearby",
        "informational",
        labels=("cough", "throat clearing"),
    ),
    SoundEvent(
        "toilet_flush",
        "Toilet flush",
        "A toilet flushing",
        "informational",
        labels=("toilet flush",),
    ),
    SoundEvent(
        "typing",
        "Typing",
        "Keyboard typing",
        "informational",
        labels=("typing", "computer keyboard"),
    ),
    SoundEvent(
        "snoring",
        "Snoring",
        "Snoring nearby",
        "informational",
        labels=("snoring",),
    ),
    SoundEvent(
        "chainsaw",
        "Chainsaw",
        "Chainsaws and similar power tools",
        "attention",
        labels=("chainsaw",),
    ),
)

# Ids used before the rebuild; profiles synced by older clients still carry them.
LEGACY_EVENT_ALIASES: dict[str, str] = {
    "fire_alarm": "alarm",
    "kitchen_timer": "appliance_beep",
}

_BY_EVENT: dict[str, SoundEvent] = {entry.event: entry for entry in CATALOG}
EVENT_IDS: tuple[str, ...] = tuple(entry.event for entry in CATALOG)


def sound_event(event: str) -> SoundEvent | None:
    return _BY_EVENT.get(event)


def canonical_event(event: str) -> str:
    """Translate a legacy event id into the current one (identity otherwise)."""
    return LEGACY_EVENT_ALIASES.get(event, event)


def default_category(event: str) -> str:
    entry = _BY_EVENT.get(event)
    return entry.category if entry is not None else "informational"


def is_safety_critical(event: str) -> bool:
    entry = _BY_EVENT.get(event)
    return entry.safety_critical if entry is not None else False
