"""Classify environmental sounds with Google's pretrained YAMNet model."""

from __future__ import annotations

import argparse
import csv
import wave
from pathlib import Path

import numpy as np
import tensorflow_hub as hub

from backend.inference.models import SoundPrediction


MODEL_URL = "https://tfhub.dev/google/yamnet/1"
TARGET_SAMPLE_RATE = 16_000


def _decode_pcm(samples: bytes, sample_width: int) -> np.ndarray:
    """Decode little-endian PCM samples and normalize them to [-1, 1]."""
    if sample_width == 1:
        # Eight-bit WAV PCM is unsigned.
        return (np.frombuffer(samples, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if sample_width == 2:
        return np.frombuffer(samples, dtype="<i2").astype(np.float32) / 32768.0
    if sample_width == 3:
        raw = np.frombuffer(samples, dtype=np.uint8).reshape(-1, 3)
        values = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values - 0x1000000, values)
        return values.astype(np.float32) / 8388608.0
    if sample_width == 4:
        return np.frombuffer(samples, dtype="<i4").astype(np.float32) / 2147483648.0
    raise ValueError(f"Unsupported PCM sample width: {sample_width} bytes")


def _resample(waveform: np.ndarray, source_rate: int) -> np.ndarray:
    """Linearly resample a mono waveform to YAMNet's required sample rate."""
    if source_rate == TARGET_SAMPLE_RATE or waveform.size == 0:
        return waveform.astype(np.float32, copy=False)

    target_length = round(waveform.size * TARGET_SAMPLE_RATE / source_rate)
    source_positions = np.arange(waveform.size, dtype=np.float64)
    target_positions = np.linspace(0, waveform.size - 1, target_length)
    return np.interp(target_positions, source_positions, waveform).astype(np.float32)


def load_wav(path: str | Path) -> np.ndarray:
    """Load an uncompressed PCM WAV as a mono, 16 kHz float waveform."""
    audio_path = Path(path)
    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            if wav_file.getcomptype() != "NONE":
                raise ValueError("Compressed WAV files are not supported")
            channel_count = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            samples = wav_file.readframes(frame_count)
    except wave.Error as exc:
        raise ValueError(f"Could not read {audio_path} as a PCM WAV file: {exc}") from exc

    if channel_count < 1 or sample_rate < 1:
        raise ValueError("WAV file has invalid channel or sample-rate metadata")

    waveform = _decode_pcm(samples, sample_width)
    if waveform.size % channel_count:
        raise ValueError("WAV sample data does not align with its channel count")
    if channel_count > 1:
        waveform = waveform.reshape(-1, channel_count).mean(axis=1)

    return _resample(waveform, sample_rate)


class YamnetSoundClassifier:
    """Reusable YAMNet model wrapper for environmental sound classification."""

    def __init__(self, model_url: str = MODEL_URL) -> None:
        self._model = hub.load(model_url)
        self._class_names = self._load_class_names()

    def _load_class_names(self) -> list[str]:
        class_map_path = self._model.class_map_path().numpy().decode("utf-8")
        with open(class_map_path, newline="", encoding="utf-8") as class_map:
            return [row["display_name"] for row in csv.DictReader(class_map)]

    def classify(self, waveform: np.ndarray, top_k: int = 5) -> list[SoundPrediction]:
        """Return the highest mean-confidence classes across all audio frames."""
        if waveform.ndim != 1:
            raise ValueError("Expected a one-dimensional mono waveform")
        if waveform.size == 0:
            raise ValueError("Cannot classify empty audio")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        scores, _, _ = self._model(waveform.astype(np.float32, copy=False))
        mean_scores = np.asarray(scores).mean(axis=0)
        class_indexes = np.argsort(mean_scores)[::-1][:top_k]
        return [
            SoundPrediction(
                label=self._class_names[index],
                confidence=float(mean_scores[index]),
            )
            for index in class_indexes
        ]

    def classify_pcm16(
        self,
        pcm: bytes,
        sample_rate: int,
        top_k: int = 5,
    ) -> list[SoundPrediction]:
        """Classify mono PCM16 from the streaming transport."""
        if sample_rate != TARGET_SAMPLE_RATE:
            raise ValueError(f"YAMNet streaming requires {TARGET_SAMPLE_RATE} Hz audio")
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM16 payload must contain complete samples")
        waveform = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        return self.classify(waveform, top_k=top_k)

    def classify_wav(self, path: str | Path, top_k: int = 5) -> list[SoundPrediction]:
        """Load and classify a WAV file."""
        return self.classify(load_wav(path), top_k=top_k)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify environmental sounds in a PCM WAV file with YAMNet."
    )
    parser.add_argument("wav_file", type=Path, help="Path to an uncompressed PCM WAV file")
    parser.add_argument("--top-k", type=int, default=5, help="Number of predictions to show")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    classifier = YamnetSoundClassifier()
    predictions = classifier.classify_wav(args.wav_file, top_k=args.top_k)

    print(f"Predictions for {args.wav_file}:")
    for rank, prediction in enumerate(predictions, start=1):
        print(f"{rank:>2}. {prediction.label:<35} {prediction.confidence:.3f}")


if __name__ == "__main__":
    main()
