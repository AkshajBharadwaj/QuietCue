"""Unit tests for the numpy YAMNet feature frontend."""

import numpy as np
import pytest

from backend.inference import audio_features as af


def test_constants_match_yamnet():
    assert af.WINDOW_SAMPLES == 400
    assert af.HOP_SAMPLES == 160
    assert af.FFT_LENGTH == 512
    assert af.PATCH_FRAMES == 96
    assert af.PATCH_HOP_FRAMES == 48
    assert af.MIN_WAVEFORM_SAMPLES == 15_600


def test_mel_matrix_shape_and_dc_bin():
    weights = af._mel_weight_matrix()
    assert weights.shape == (257, 64)
    assert np.all(weights >= 0.0)
    # 0 Hz sits below the 125 Hz lower edge, so DC contributes nothing.
    assert np.all(weights[0] == 0.0)
    # Every mel band collects energy from at least one STFT bin.
    assert np.all(weights.sum(axis=0) > 0.0)


def test_one_second_chunk_yields_one_patch():
    waveform = np.zeros(16_000, dtype=np.float32)
    patches = af.waveform_to_patches(waveform)
    assert patches.shape == (1, 96, 64)
    assert patches.dtype == np.float32


def test_two_second_chunk_yields_three_patches():
    # 32,000 samples pad to cover the first patch plus hops of 0.48 s.
    waveform = np.zeros(32_000, dtype=np.float32)
    patches = af.waveform_to_patches(waveform)
    assert patches.shape[0] == 3
    assert patches.shape[1:] == (96, 64)


def test_short_chunk_padded_to_one_patch():
    waveform = np.zeros(4_000, dtype=np.float32)
    patches = af.waveform_to_patches(waveform)
    assert patches.shape == (1, 96, 64)


def test_silence_hits_log_offset_floor():
    features = af.log_mel_spectrogram(np.zeros(16_000, dtype=np.float32))
    assert features == pytest.approx(np.log(af.LOG_OFFSET), abs=1e-4)


def test_pure_tone_energy_lands_in_expected_mel_band():
    t = np.arange(16_000) / 16_000.0
    tone = (0.5 * np.sin(2 * np.pi * 1_000.0 * t)).astype(np.float32)
    features = af.log_mel_spectrogram(tone)
    hottest_band = int(features.mean(axis=0).argmax())
    # 1 kHz sits in the lower-middle of the 125–7500 Hz 64-band mel range.
    band_edges_hz = 700.0 * (
        np.expm1(
            np.linspace(
                af._hertz_to_mel(np.array(af.MEL_MIN_HZ)),
                af._hertz_to_mel(np.array(af.MEL_MAX_HZ)),
                66,
            )
            / 1127.0
        )
    )
    assert band_edges_hz[hottest_band] <= 1_000.0 <= band_edges_hz[hottest_band + 2]
