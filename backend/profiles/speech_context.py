"""User-approved identity and manual context for local speech recognition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SpeechModel(str, Enum):
    TINY_EN = "tiny_en"
    BASE_EN = "base_en"


class SpeechMode(str, Enum):
    INHERIT = "inherit"
    ALWAYS_ON = "always_on"
    OFF = "off"


@dataclass(frozen=True)
class SpeechSettings:
    enabled: bool = True
    model: SpeechModel = SpeechModel.TINY_EN
    sensitivity: float = 0.6
    listen_for_identity: bool = True
    listen_for_people: bool = False
    global_phrases: tuple[str, ...] = ()


@dataclass(frozen=True)
class UserIdentity:
    name: str
    pronunciation: str = ""
    aliases: tuple[str, ...] = ()
    recognition_phrases: tuple[str, ...] = ()

    def trigger_phrases(self) -> tuple[str, ...]:
        return _unique((self.name, self.pronunciation, *self.aliases, *self.recognition_phrases))


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
        values: list[str] = []
        if self.identity is not None:
            values.extend((self.identity.name, self.identity.pronunciation, *self.identity.aliases))
        for person in self.people:
            values.extend((person.name, person.pronunciation, *person.aliases))
        values.extend(self.settings.global_phrases)
        values.extend(context.title for context in self.contexts)
        return _unique(values)

    def prompt(self, maximum_length: int = 800) -> str:
        """Build bounded local-only context for Whisper without storing transcripts."""
        parts: list[str] = []
        if self.identity is not None:
            identity = f"The user's name is {self.identity.name}."
            if self.identity.pronunciation:
                identity += f" It is pronounced {self.identity.pronunciation}."
            parts.append(identity)
        if self.people:
            people = []
            for person in self.people:
                description = person.name
                if person.relationship:
                    description += f" ({person.relationship})"
                if person.pronunciation:
                    description += f", pronounced {person.pronunciation}"
                if person.notes:
                    description += f", {person.notes}"
                people.append(description)
            parts.append("Known people: " + "; ".join(people) + ".")
        if self.contexts:
            parts.append(
                "User-provided context: "
                + "; ".join(f"{context.title}: {context.details}" for context in self.contexts)
                + "."
            )
        return " ".join(parts)[:maximum_length].strip()


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
