from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.audio.demo_audio import write_demo_wav
from backend.audio.wav_source import iter_wav_chunks


class WavSourceTest(unittest.TestCase):
    def test_replay_uses_fixed_contract_and_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_demo_wav(Path(directory) / "alarm.wav", "alarm", 1.0)
            chunks = list(iter_wav_chunks(path, chunk_ms=500))

        self.assertEqual([chunk.sequence for chunk in chunks], [0, 1])
        self.assertTrue(all(chunk.sample_rate == 16_000 for chunk in chunks))
        self.assertTrue(all(chunk.channels == 1 for chunk in chunks))
        self.assertTrue(all(chunk.duration_ms == 500 for chunk in chunks))
