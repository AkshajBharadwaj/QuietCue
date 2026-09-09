"""User-approved identity and manual context for local speech recognition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SpeechModel(str, Enum):
    TINY_EN = "tiny_en"
    BASE_EN = "base_en"
    SMALL_EN = "small_en"


class SpeechMode(str, Enum):
    INHERIT = "inherit"
    ALWAYS_ON = "always_on"
    OFF = "off"


@dataclass(frozen=True)
class SpeechSettings:
    enabled: bool = True
    model: SpeechModel = SpeechModel.BASE_EN
    sensitivity: float = 0.6
    listen_for_identity: bool = True
    listen_for_people: bool = False
    global_phrases: tuple[str, ...] = ()


@dataclass(frozen=True)
class UserIdentity:
    name: str
    pronunciation: str = ""
    aliases: tuple[str, ...] = ()
    # Spellings the hub's own Whisper model produced for this name during
    # enrollment ("Rowan" for Rohan). Matched like aliases, never used as prompt.
    recognition_phrases: tuple[str, ...] = ()

    def trigger_phrases(self) -> tuple[str, ...]:
        # The pronunciation guide ("Ro-han") is for humans; Whisper never emits it.
        return _unique((self.name, *self.aliases, *self.recognition_phrases))

    def spellings(self) -> tuple[str, ...]:
        return _unique((self.name, *self.aliases))


@dataclass(frozen=True)
class KnownPerson:
    name: str
    relationship: str = ""
    pronunciation: str = ""
    aliases: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ManualContext:
    title: str
    details: str


@dataclass(frozen=True)
class SpeechContext:
    identity: UserIdentity | None = None
    people: tuple[KnownPerson, ...] = ()
    contexts: tuple[ManualContext, ...] = ()
    settings: SpeechSettings = SpeechSettings()

    def identity_triggers(self) -> tuple[str, ...]:
        return self.identity.trigger_phrases() if self.identity is not None else ()

    def people_triggers(self) -> tuple[str, ...]:
        values: list[str] = []
        for person in self.people:
            values.extend((person.name, *person.aliases))
        return _unique(values)

    def trigger_phrases(
        self,
        profile_phrases: tuple[str, ...] | list[str] = (),
        additional_phrases: tuple[str, ...] | list[str] = (),
    ) -> tuple[str, ...]:
        values: list[str] = [*self.settings.global_phrases]
        if self.settings.listen_for_identity:
            values.extend(self.identity_triggers())
        if self.settings.listen_for_people:
            values.extend(self.people_triggers())
        values.extend(profile_phrases)
        values.extend(additional_phrases)
        return _unique(values)

    def hotwords(self) -> tuple[str, ...]:
        """Short spellings Whisper should be biased towards; no pronunciation guides."""
        values: list[str] = []
        if self.identity is not None:
            values.extend(self.identity.spellings())
        for person in self.people:
            values.extend((person.name, *person.aliases))
        values.extend(self.settings.global_phrases)
        values.extend(context.title for context in self.contexts)
        return _unique(values)

    def prompt(self, maximum_length: int = 400) -> str:
        """Build a transcript-style prompt for Whisper without storing transcripts.

        Whisper treats ``initial_prompt`` as preceding transcript, so a list of
        the names as they would be spoken biases decoding far better than prose
        ("The user's name is ...") and leaves no room for hallucinated context.
        """
        parts: list[str] = []
        if self.identity is not None:
            parts.append(f"{self.identity.name}.")
            parts.append(f"Hey {self.identity.name}.")
            parts.extend(f"{alias}." for alias in self.identity.aliases)
        for person in self.people:
            parts.append(f"{person.name}.")
            parts.extend(f"{alias}." for alias in person.aliases)
        parts.extend(f"{phrase[:1].upper()}{phrase[1:]}." for phrase in self.settings.global_phrases)
        parts.extend(f"{context.title}." for context in self.contexts)
        prompt = " ".join(_unique(parts))
        if len(prompt) > maximum_length:
            prompt = prompt[:maximum_length].rsplit(" ", 1)[0]
        return prompt.strip()


def _unique(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)
