"""User-approved identity and manual context for local speech recognition."""

from __future__ import annotations

from dataclasses import dataclass


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

    def identity_triggers(self) -> tuple[str, ...]:
        return self.identity.trigger_phrases() if self.identity is not None else ()

    def hotwords(self) -> tuple[str, ...]:
        values: list[str] = []
        if self.identity is not None:
            values.extend((self.identity.name, self.identity.pronunciation, *self.identity.aliases))
        for person in self.people:
            values.extend((person.name, person.pronunciation, *person.aliases))
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
