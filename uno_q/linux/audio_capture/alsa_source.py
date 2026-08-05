"""Live ALSA microphone capture for the Uno Q Linux side.

Audio is read from ``arecord`` over a pipe and is never written to disk. The
source deliberately emits the same ``AudioChunk`` contract as WAV replay so the
transport and inference layers do not need microphone-specific behavior.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable, Iterator
from typing import BinaryIO

from backend.audio.wav_source import (
    CHANNELS,
    DEFAULT_CHUNK_MS,
    SAMPLE_RATE,
    SAMPLE_WIDTH_BYTES,
    AudioChunk,
)


DEFAULT_ALSA_DEVICE = "plughw:CARD=Microphone,DEV=0"


class AlsaCaptureError(RuntimeError):
    """Raised when the microphone cannot provide a complete PCM chunk."""


class AlsaPcmSource:
    """Continuously capture transport-ready mono PCM16 chunks with ``arecord``."""

    def __init__(
        self,
        device: str = DEFAULT_ALSA_DEVICE,
        *,
        sample_rate: int = SAMPLE_RATE,
        chunk_ms: int = DEFAULT_CHUNK_MS,
        executable: str = "arecord",
        process_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    ) -> None:
        if not device.strip():
            raise ValueError("ALSA device cannot be blank")
        if sample_rate < 8_000 or sample_rate > 48_000:
            raise ValueError("sample_rate must be between 8000 and 48000 Hz")
        if chunk_ms < 20 or chunk_ms > 1_000:
            raise ValueError("chunk_ms must be between 20 and 1000")
        self.device = device
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.executable = executable
        self._process_factory = process_factory
        self._process: subprocess.Popen[bytes] | None = None
        self._sequence = 0

    @property
    def command(self) -> tuple[str, ...]:
        return (
            self.executable,
            "-q",
            "-D",
            self.device,
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-c",
            str(CHANNELS),
            "-r",
            str(self.sample_rate),
        )

    @property
    def bytes_per_chunk(self) -> int:
        frames = round(self.sample_rate * self.chunk_ms / 1_000)
        return frames * CHANNELS * SAMPLE_WIDTH_BYTES

    def start(self) -> None:
        if self._process is not None:
            raise AlsaCaptureError("Microphone capture is already running")
        if self._process_factory is subprocess.Popen and shutil.which(self.executable) is None:
            raise AlsaCaptureError(f"{self.executable} is not installed; install alsa-utils on the Uno Q")
        self._process = self._process_factory(
            self.command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if self._process.stdout is None:
            self.close()
            raise AlsaCaptureError("arecord did not expose an audio pipe")

    def read_chunk(self) -> AudioChunk:
        process = self._process
        if process is None or process.stdout is None:
            raise AlsaCaptureError("Microphone capture has not been started")
        pcm = _read_exact(process.stdout, self.bytes_per_chunk)
        if len(pcm) != self.bytes_per_chunk:
            detail = _process_error(process)
            raise AlsaCaptureError(
                f"Microphone stopped after {len(pcm)} of {self.bytes_per_chunk} bytes"
                + (f": {detail}" if detail else "")
            )
        chunk = AudioChunk(
            sequence=self._sequence,
            captured_at_ms=int(time.time() * 1_000),
            pcm=pcm,
            sample_rate=self.sample_rate,
        )
        self._sequence += 1
        return chunk

    def iter_chunks(self, max_chunks: int | None = None) -> Iterator[AudioChunk]:
        if max_chunks is not None and max_chunks < 1:
            raise ValueError("max_chunks must be positive")
        emitted = 0
        while max_chunks is None or emitted < max_chunks:
            yield self.read_chunk()
            emitted += 1

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    def __enter__(self) -> "AlsaPcmSource":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def list_capture_hardware(executable: str = "arecord") -> str:
    """Return ALSA's capture-device listing for setup diagnostics."""
    if shutil.which(executable) is None:
        raise AlsaCaptureError(f"{executable} is not installed; install alsa-utils on the Uno Q")
    result = subprocess.run(
        [executable, "-l"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise AlsaCaptureError(output or "Could not enumerate ALSA capture devices")
    return output


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _process_error(process: subprocess.Popen[bytes]) -> str:
    if process.stderr is None or process.poll() is None:
        return ""
    return process.stderr.read().decode("utf-8", errors="replace").strip()
