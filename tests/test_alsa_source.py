from __future__ import annotations

import io
import unittest

from uno_q.linux.audio_capture.alsa_source import AlsaCaptureError, AlsaPcmSource


class _FakeProcess:
    def __init__(self, payload: bytes) -> None:
        self.stdout = io.BytesIO(payload)
        self.stderr = io.BytesIO()
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


class AlsaPcmSourceTest(unittest.TestCase):
    def test_live_source_emits_the_same_pcm_contract_as_wav_replay(self) -> None:
        commands: list[tuple[str, ...]] = []
        expected = bytes(range(256)) * 125

        def create_process(command: tuple[str, ...], **_: object) -> _FakeProcess:
            commands.append(command)
            return _FakeProcess(expected)

        source = AlsaPcmSource(
            "plughw:CARD=Microphone,DEV=0",
            chunk_ms=1_000,
            process_factory=create_process,
        )
        with source:
            chunk = source.read_chunk()

        self.assertEqual(chunk.pcm, expected)
        self.assertEqual(chunk.sample_rate, 16_000)
        self.assertEqual(chunk.channels, 1)
        self.assertEqual(chunk.encoding, "pcm_s16le")
        self.assertEqual(chunk.duration_ms, 1_000)
        self.assertEqual(commands[0][commands[0].index("-D") + 1], "plughw:CARD=Microphone,DEV=0")

    def test_short_read_is_reported_instead_of_sending_partial_audio(self) -> None:
        source = AlsaPcmSource(
            process_factory=lambda *_args, **_kwargs: _FakeProcess(b"\x00\x00"),
        )

        with source, self.assertRaises(AlsaCaptureError):
            source.read_chunk()


if __name__ == "__main__":
    unittest.main()
