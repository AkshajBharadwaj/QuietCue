"""YAMNet log-mel feature frontend implemented with numpy only.

Reproduces the feature pipeline from tensorflow/models research/audioset/yamnet
(features.py + params.py) so the exported ONNX model — which takes 96x64
log-mel patches instead of raw waveform — sees the same inputs it was trained
with. No TensorFlow dependency: TF has no win-arm64 wheels, and the hub runs on
a Snapdragon X Elite.
"""

from __future__ import annotations

import functools

import numpy as np

SAMPLE_RATE = 16_000
STFT_WINDOW_SECONDS = 0.025
STFT_HOP_SECONDS = 0.010
MEL_BANDS = 64
MEL_MIN_HZ = 125.0
MEL_MAX_HZ = 7_500.0
LOG_OFFSET = 0.001
PATCH_WINDOW_SECONDS = 0.96
PATCH_HOP_SECONDS = 0.48

WINDOW_SAMPLES = round(SAMPLE_RATE * STFT_WINDOW_SECONDS)  # 400
HOP_SAMPLES = round(SAMPLE_RATE * STFT_HOP_SECONDS)  # 160
FFT_LENGTH = 2 ** int(np.ceil(np.log2(WINDOW_SAMPLES)))  # 512
PATCH_FRAMES = int(round(PATCH_WINDOW_SECONDS / STFT_HOP_SECONDS))  # 96
PATCH_HOP_FRAMES = int(round(PATCH_HOP_SECONDS / STFT_HOP_SECONDS))  # 48
# Shortest waveform that yields one full 96-frame patch: 15,600 samples.
MIN_WAVEFORM_SAMPLES = round(
    (PATCH_WINDOW_SECONDS + STFT_WINDOW_SECONDS - STFT_HOP_SECONDS) * SAMPLE_RATE
)


def _hertz_to_mel(frequencies_hz: np.ndarray) -> np.ndarray:
    """HTK mel scale, matching tf.signal.linear_to_mel_weight_matrix."""
    return 1127.0 * np.log1p(np.asarray(frequencies_hz, dtype=np.float64) / 700.0)


@functools.lru_cache(maxsize=1)
def _mel_weight_matrix() -> np.ndarray:
    """(257, 64) triangular mel filterbank over the STFT bin frequencies."""
    spectrogram_bins_hz = np.linspace(0.0, SAMPLE_RATE / 2, FFT_LENGTH // 2 + 1)
    spectrogram_bins_mel = _hertz_to_mel(spectrogram_bins_hz)
    band_edges_mel = np.linspace(
        _hertz_to_mel(np.array(MEL_MIN_HZ)),
        _hertz_to_mel(np.array(MEL_MAX_HZ)),
        MEL_BANDS + 2,
    )
    lower = band_edges_mel[:-2]
    center = band_edges_mel[1:-1]
    upper = band_edges_mel[2:]
    up_slope = (spectrogram_bins_mel[:, None] - lower) / (center - lower)
    down_slope = (upper - spectrogram_bins_mel[:, None]) / (upper - center)
    weights = np.maximum(0.0, np.minimum(up_slope, down_slope))
    # The DC bin never contributes (0 Hz sits below the 125 Hz lower edge).
    return weights.astype(np.float32)


@functools.lru_cache(maxsize=1)
def _periodic_hann() -> np.ndarray:
    """Periodic Hann window, matching tf.signal.hann_window(periodic=True)."""
    return (0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(WINDOW_SAMPLES) / WINDOW_SAMPLES)).astype(
        np.float32
    )


def pad_waveform(waveform: np.ndarray) -> np.ndarray:
    """Zero-pad short audio up to one full patch.

    Deliberate divergence from TF YAMNet's pad_waveform: TF pads *longer* audio
    out to an integral number of patches, so a 1 s streaming chunk grows a
    second, half-silent patch that dilutes the score mean. For chunked
    streaming we only pad up to the first patch and otherwise emit the patches
    fully covered by real audio.
    """
    if waveform.size >= MIN_WAVEFORM_SAMPLES:
        return waveform
    return np.concatenate(
        [waveform, np.zeros(MIN_WAVEFORM_SAMPLES - waveform.size, dtype=waveform.dtype)]
    )


def log_mel_spectrogram(waveform: np.ndarray) -> np.ndarray:
    """Compute (num_frames, 64) log-mel features from a mono 16 kHz waveform."""
    if waveform.ndim != 1:
        raise ValueError("Expected a one-dimensional mono waveform")
    waveform = waveform.astype(np.float32, copy=False)
    if waveform.size < WINDOW_SAMPLES:
        waveform = np.concatenate(
            [waveform, np.zeros(WINDOW_SAMPLES - waveform.size, dtype=np.float32)]
        )

    num_frames = 1 + (waveform.size - WINDOW_SAMPLES) // HOP_SAMPLES
    frame_strides = (waveform.strides[0] * HOP_SAMPLES, waveform.strides[0])
    frames = np.lib.stride_tricks.as_strided(
        waveform, shape=(num_frames, WINDOW_SAMPLES), strides=frame_strides
    )
    magnitude = np.abs(np.fft.rfft(frames * _periodic_hann(), n=FFT_LENGTH))
    mel = magnitude.astype(np.float32) @ _mel_weight_matrix()
    return np.log(mel + LOG_OFFSET)


def waveform_to_patches(waveform: np.ndarray) -> np.ndarray:
    """Convert a mono 16 kHz waveform to (num_patches, 96, 64) model inputs."""
    features = log_mel_spectrogram(pad_waveform(waveform))
    num_patches = 1 + (features.shape[0] - PATCH_FRAMES) // PATCH_HOP_FRAMES
    patches = np.stack(
        [
            features[start : start + PATCH_FRAMES]
            for start in range(0, num_patches * PATCH_HOP_FRAMES, PATCH_HOP_FRAMES)
            if start + PATCH_FRAMES <= features.shape[0]
        ]
    )
    return patches.astype(np.float32)
