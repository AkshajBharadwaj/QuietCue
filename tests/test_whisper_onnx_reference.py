from __future__ import annotations

import math
import json
import unittest
from pathlib import Path

try:
    import numpy as np
except ImportError as exc:  # Optional Whisper/ONNX verification dependency.
    raise unittest.SkipTest("numpy is an optional Whisper ONNX test dependency") from exc

from scripts.whisper_onnx_reference import (
    MEL_BANDS,
    MEL_FRAMES,
    pcm16_to_log_mel,
    select_decoder_token,
)


class WhisperOnnxReferenceTest(unittest.TestCase):
    def test_silence_has_expected_shape_and_log_floor(self) -> None:
        mel = pcm16_to_log_mel(bytes(16_000 * 2))

        self.assertEqual(mel.shape, (MEL_BANDS, MEL_FRAMES))
        np.testing.assert_allclose(mel, -1.5, atol=1e-6)

    def test_tone_matches_cross_language_reference_points(self) -> None:
        fixture = json.loads(
            Path("tests/fixtures/whisper_reference/mel_points.json").read_text(encoding="utf-8")
        )
        samples = np.array(
            [
                np.int16(
                    math.sin(2 * math.pi * fixture["tone_hz"] * index / fixture["sample_rate"])
                    * fixture["amplitude_pcm16"]
                )
                for index in range(fixture["duration_samples"])
            ],
            dtype="<i2",
        )
        mel = pcm16_to_log_mel(samples.tobytes())

        for point in fixture["points"]:
            self.assertAlmostEqual(
                float(mel[point["band"], point["frame"]]),
                point["value"],
                delta=fixture["tolerance"],
            )

    def test_decoder_prefix_preserves_first_step_silence_stop(self) -> None:
        vocabulary = {
            "eot": 0,
            "sot": 1,
            "english": 2,
            "transcribe": 3,
            "no_speech": 4,
            "no_timestamps": 5,
        }

        self.assertIsNone(select_decoder_token(0, vocabulary["no_speech"], vocabulary))
        self.assertIsNone(select_decoder_token(3, vocabulary["eot"], vocabulary))
        self.assertEqual(select_decoder_token(0, 6, vocabulary), vocabulary["english"])
        self.assertEqual(select_decoder_token(1, 6, vocabulary), vocabulary["transcribe"])
        self.assertEqual(select_decoder_token(2, 6, vocabulary), vocabulary["no_timestamps"])
        self.assertEqual(select_decoder_token(3, 6, vocabulary), 6)


if __name__ == "__main__":
    unittest.main()
