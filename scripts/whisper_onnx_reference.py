#!/usr/bin/env python3
"""CPU oracle for QuietCue's Qualcomm AI Hub-style Whisper ONNX pair.

The script uses the same 80x3000 mel frontend and explicit decoder-cache
contract as the Android implementation. Diagnostic dumps never include raw
audio or decoded transcript text.
"""

from __future__ import annotations

import argparse
import json
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np


SAMPLE_RATE = 16_000
MAX_AUDIO_SAMPLES = 30 * SAMPLE_RATE
N_FFT = 400
HOP_LENGTH = 160
MEL_BANDS = 80
MEL_FRAMES = 3_000
MAX_DECODE_LENGTH = 200


def pcm16_to_log_mel(pcm: bytes) -> np.ndarray:
    if not pcm or len(pcm) % 2:
        raise ValueError("PCM16 must contain complete samples")
    source = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    waveform = np.zeros(MAX_AUDIO_SAMPLES, dtype=np.float32)
    waveform[: min(source.size, waveform.size)] = source[: waveform.size]
    padded = np.pad(waveform, (N_FFT // 2, N_FFT // 2), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP_LENGTH][:MEL_FRAMES]
    periodic_hann = np.hanning(N_FFT + 1)[:-1]
    power = np.abs(np.fft.rfft(frames * periodic_hann, n=N_FFT, axis=1)) ** 2
    mel = power @ _slaney_filter_bank().T
    log_mel = np.log10(np.maximum(mel, 1e-10)).T
    log_mel = np.maximum(log_mel, log_mel.max() - 8.0)
    return ((log_mel + 4.0) / 4.0).astype(np.float32)


def _slaney_filter_bank() -> np.ndarray:
    linear_spacing = 200.0 / 3.0
    log_threshold_hz = 1_000.0
    log_threshold_mel = 15.0
    log_step = np.log(6.4) / 27.0

    def hertz_to_mel(frequencies: np.ndarray) -> np.ndarray:
        return np.where(
            frequencies < log_threshold_hz,
            frequencies / linear_spacing,
            log_threshold_mel
            + np.log(np.maximum(frequencies, 1e-30) / log_threshold_hz) / log_step,
        )

    def mel_to_hertz(mels: np.ndarray) -> np.ndarray:
        return np.where(
            mels < log_threshold_mel,
            mels * linear_spacing,
            log_threshold_hz * np.exp(log_step * (mels - log_threshold_mel)),
        )

    bins = np.linspace(0.0, SAMPLE_RATE / 2.0, N_FFT // 2 + 1)
    mel_edges = np.linspace(
        hertz_to_mel(np.array(0.0)),
        hertz_to_mel(np.array(SAMPLE_RATE / 2.0)),
        MEL_BANDS + 2,
    )
    edges = mel_to_hertz(mel_edges)
    weights = np.zeros((MEL_BANDS, bins.size), dtype=np.float64)
    for band in range(MEL_BANDS):
        rising = (bins - edges[band]) / (edges[band + 1] - edges[band])
        falling = (edges[band + 2] - bins) / (edges[band + 2] - edges[band + 1])
        weights[band] = (
            np.maximum(0.0, np.minimum(rising, falling))
            * 2.0
            / (edges[band + 2] - edges[band])
        )
    return weights


def run_reference(
    encoder_path: Path,
    decoder_path: Path,
    vocabulary_path: Path,
    pcm: bytes,
    *,
    max_tokens: int = MAX_DECODE_LENGTH - 1,
    dump_dir: Path | None = None,
) -> dict[str, Any]:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("Install backend/requirements-whisper-onnx.txt") from exc

    vocabulary = json.loads(vocabulary_path.read_text(encoding="utf-8"))
    token_bytes = vocabulary["token_bytes"]
    encoder = ort.InferenceSession(str(encoder_path), providers=["CPUExecutionProvider"])
    decoder = ort.InferenceSession(str(decoder_path), providers=["CPUExecutionProvider"])
    contract = validate_contract(encoder, decoder, len(token_bytes))

    mel_started = time.perf_counter()
    mel = pcm16_to_log_mel(pcm)
    mel_ms = (time.perf_counter() - mel_started) * 1_000
    encoder_started = time.perf_counter()
    encoder_values = encoder.run(None, {"input_features": mel[np.newaxis, ...]})
    encoder_ms = (time.perf_counter() - encoder_started) * 1_000
    cross_cache = dict(zip((item.name for item in encoder.get_outputs()), encoder_values, strict=True))

    layers = contract["layers"]
    decode_length = contract["decode_length"]
    attention_mask = np.full((1, 1, 1, decode_length), -100.0, dtype=np.float32)
    self_cache = {
        item.name: np.zeros(tuple(item.shape), dtype=np.float32)
        for item in decoder.get_inputs()
        if item.name.startswith(("k_cache_self_", "v_cache_self_"))
    }
    output_tokens = [int(vocabulary["sot"])]
    current_token = int(vocabulary["sot"])
    first_logits: list[np.ndarray] = []
    decoder_ms = 0.0
    limit = min(max_tokens, decode_length - 1)
    for position in range(limit):
        attention_mask[..., decode_length - position - 1] = 0.0
        inputs: dict[str, np.ndarray] = {
            "input_ids": np.array([[current_token]], dtype=np.int32),
            "attention_mask": attention_mask,
            "position_ids": np.array([position], dtype=np.int32),
        }
        for layer in layers:
            inputs[f"k_cache_self_{layer}_in"] = self_cache[f"k_cache_self_{layer}_in"]
            inputs[f"v_cache_self_{layer}_in"] = self_cache[f"v_cache_self_{layer}_in"]
            inputs[f"k_cache_cross_{layer}"] = cross_cache[f"k_cache_cross_{layer}"]
            inputs[f"v_cache_cross_{layer}"] = cross_cache[f"v_cache_cross_{layer}"]
        decoder_started = time.perf_counter()
        output_values = decoder.run(None, inputs)
        decoder_ms += (time.perf_counter() - decoder_started) * 1_000
        outputs = dict(zip((item.name for item in decoder.get_outputs()), output_values, strict=True))
        logits = outputs["logits"].reshape(-1)
        if len(first_logits) < 8:
            first_logits.append(logits.copy())
        for layer in layers:
            self_cache[f"k_cache_self_{layer}_in"] = outputs[f"k_cache_self_{layer}_out"]
            self_cache[f"v_cache_self_{layer}_in"] = outputs[f"v_cache_self_{layer}_out"]
        greedy_token = int(np.argmax(logits))
        next_token = select_decoder_token(position, greedy_token, vocabulary)
        if next_token is None:
            break
        output_tokens.append(next_token)
        current_token = next_token

    transcript = decode_tokens(output_tokens, token_bytes)
    if dump_dir is not None:
        dump_dir.mkdir(parents=True, exist_ok=True)
        np.save(dump_dir / "mel.npy", mel)
        for name, value in cross_cache.items():
            np.save(dump_dir / f"encoder_{name}.npy", value)
        np.save(
            dump_dir / "decoder_logits_first_8.npy",
            np.stack(first_logits) if first_logits else np.empty((0, len(token_bytes)), dtype=np.float32),
        )
        (dump_dir / "token_ids.json").write_text(json.dumps(output_tokens), encoding="utf-8")
        (dump_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "encoder": str(encoder_path),
                    "decoder": str(decoder_path),
                    "contract": contract,
                    "mel_ms": round(mel_ms, 2),
                    "encoder_ms": round(encoder_ms, 2),
                    "decoder_ms": round(decoder_ms, 2),
                    "raw_audio_saved": False,
                    "transcript_saved": False,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    return {
        "transcript": transcript,
        "token_ids": output_tokens,
        "mel_ms": round(mel_ms, 2),
        "encoder_ms": round(encoder_ms, 2),
        "decoder_ms": round(decoder_ms, 2),
        "contract": contract,
    }


def validate_contract(encoder: Any, decoder: Any, vocabulary_size: int) -> dict[str, Any]:
    encoder_inputs = {item.name: item for item in encoder.get_inputs()}
    if set(encoder_inputs) != {"input_features"}:
        raise ValueError("Encoder must expose only input_features")
    mel_input = encoder_inputs["input_features"]
    if mel_input.type != "tensor(float)" or list(mel_input.shape) != [1, 80, 3_000]:
        raise ValueError("Encoder input must be float32[1,80,3000]")
    decoder_inputs = {item.name: item for item in decoder.get_inputs()}
    decoder_outputs = {item.name: item for item in decoder.get_outputs()}
    for name in ("input_ids", "attention_mask", "position_ids"):
        if name not in decoder_inputs:
            raise ValueError(f"Decoder input {name} is missing")
    if decoder_inputs["input_ids"].type != "tensor(int32)" or decoder_inputs["position_ids"].type != "tensor(int32)":
        raise ValueError("Decoder token and position inputs must be int32")
    if decoder_inputs["attention_mask"].type != "tensor(float)":
        raise ValueError("Decoder attention mask must be float32")
    decode_length = int(decoder_inputs["attention_mask"].shape[-1])
    layers = sorted(
        int(name.removeprefix("k_cache_self_").removesuffix("_in"))
        for name in decoder_inputs
        if name.startswith("k_cache_self_") and name.endswith("_in")
    )
    if not layers or layers != list(range(len(layers))):
        raise ValueError("Decoder self-cache layers are incomplete")
    encoder_outputs = {item.name: item for item in encoder.get_outputs()}
    for layer in layers:
        required_inputs = (
            f"k_cache_self_{layer}_in",
            f"v_cache_self_{layer}_in",
            f"k_cache_cross_{layer}",
            f"v_cache_cross_{layer}",
        )
        required_outputs = (f"k_cache_self_{layer}_out", f"v_cache_self_{layer}_out")
        if any(name not in decoder_inputs for name in required_inputs):
            raise ValueError(f"Decoder cache contract is incomplete at layer {layer}")
        if any(name not in decoder_outputs for name in required_outputs):
            raise ValueError(f"Decoder self-cache output is incomplete at layer {layer}")
        if any(name not in encoder_outputs for name in required_inputs[2:]):
            raise ValueError(f"Encoder cross-cache output is incomplete at layer {layer}")
    logits = decoder_outputs.get("logits")
    if logits is None or logits.type != "tensor(float)" or list(logits.shape) != [1, vocabulary_size, 1, 1]:
        raise ValueError("Decoder logits must be float32[1,vocabulary,1,1]")
    float_tensors = [
        *[item for name, item in decoder_inputs.items() if name not in {"input_ids", "position_ids"}],
        *decoder_outputs.values(),
        *encoder_outputs.values(),
    ]
    if any(item.type != "tensor(float)" for item in float_tensors):
        raise ValueError("All cache and logits tensors must use float32 I/O")
    return {"layers": layers, "decode_length": decode_length, "vocabulary_size": vocabulary_size}


def select_decoder_token(
    position: int,
    greedy_token: int,
    vocabulary: dict[str, Any],
) -> int | None:
    stop_tokens = {int(vocabulary["eot"]), int(vocabulary["no_speech"])}
    if position == 0 and greedy_token in stop_tokens:
        return None
    if position >= 3 and greedy_token in stop_tokens:
        return None
    return {
        0: int(vocabulary["english"]),
        1: int(vocabulary["transcribe"]),
        2: int(vocabulary["no_timestamps"]),
    }.get(position, greedy_token)


def decode_tokens(token_ids: list[int], token_bytes: list[list[int]]) -> str:
    payload = b"".join(bytes(token_bytes[token]) for token in token_ids if 0 <= token < len(token_bytes))
    return payload.decode("utf-8", errors="replace").strip()


def read_pcm16_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != SAMPLE_RATE:
            raise ValueError("Reference WAV must be mono 16 kHz PCM16")
        return source.readframes(source.getnframes())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", type=Path, required=True)
    parser.add_argument("--decoder", type=Path, required=True)
    parser.add_argument("--vocabulary", type=Path, required=True)
    parser.add_argument("--wav", type=Path, required=True, help="Mono 16 kHz PCM16 diagnostic WAV")
    parser.add_argument("--max-tokens", type=int, default=MAX_DECODE_LENGTH - 1)
    parser.add_argument("--dump-dir", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_reference(
        args.encoder,
        args.decoder,
        args.vocabulary,
        read_pcm16_wav(args.wav),
        max_tokens=args.max_tokens,
        dump_dir=args.dump_dir,
    )
    print(f"Transcript: {result['transcript']}")
    print(
        "Timing: "
        f"mel={result['mel_ms']} ms encoder={result['encoder_ms']} ms decoder={result['decoder_ms']} ms"
    )


if __name__ == "__main__":
    main()
