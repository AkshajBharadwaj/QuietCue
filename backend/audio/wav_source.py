"""Validated WAV replay source that mirrors future Uno Q microphone chunks."""

from __future__ import annotations

import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
ENCODING = "pcm_s16le"
DEFAULT_CHUNK_MS = 500


@dataclass(frozen=True)
class AudioChunk:
    sequence: int
    captured_at_ms: int
    pcm: bytes
    sample_rate: int = SAMPLE_RATE
    channels: int = CHANNELS
    encoding: str = ENCODING

    @property
    def duration_ms(self) -> int:
        sample_count = len(self.pcm) // SAMPLE_WIDTH_BYTES
        return round(sample_count * 1_000 / self.sample_rate)

    def to_wire(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "captured_at_ms": self.captured_at_ms,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "encoding": self.encoding,
            "duration_ms": self.duration_ms,
        }


def iter_wav_chunks(
    path: str | Path,
    chunk_ms: int = DEFAULT_CHUNK_MS,
    *,
    realtime: bool = False,
) -> Iterator[AudioChunk]:
    """Yield transport-ready chunks from a WAV file.

    The strict format is intentional: replay and the future microphone adapter
    must present exactly the same bytes to the rest of the system.
    """
    if chunk_ms < 20 or chunk_ms > 1_000:
        raise ValueError("chunk_ms must be between 20 and 1000")
    frames_per_chunk = round(SAMPLE_RATE * chunk_ms / 1_000)

    try:
        wav_file = wave.open(str(path), "rb")
    except wave.Error as exc:
        raise ValueError(f"Could not read {path} as PCM WAV: {exc}") from exc

    with wav_file:
        if wav_file.getcomptype() != "NONE":
            raise ValueError("WAV must contain uncompressed PCM")
        if wav_file.getnchannels() != CHANNELS:
            raise ValueError("WAV must be mono")
        if wav_file.getsampwidth() != SAMPLE_WIDTH_BYTES:
            raise ValueError("WAV must use signed 16-bit PCM")
        if wav_file.getframerate() != SAMPLE_RATE:
            raise ValueError(f"WAV must use a {SAMPLE_RATE} Hz sample rate")

        sequence = 0
        next_send_at = time.monotonic()
        while pcm := wav_file.readframes(frames_per_chunk):
            if realtime:
                delay = next_send_at - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
            yield AudioChunk(
                sequence=sequence,
                captured_at_ms=int(time.time() * 1_000),
                pcm=pcm,
            )
            sequence += 1
            next_send_at += chunk_ms / 1_000
