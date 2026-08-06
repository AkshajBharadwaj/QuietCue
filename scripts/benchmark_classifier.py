"""Benchmark the QuietCue environmental classifier on chunk-sized audio.

Measures exactly what the live pipeline pays per streamed chunk: PCM16 in,
predictions out (mel frontend + ONNX inference), for each model/target
combination that is runnable on this machine. Reports per-run latency
percentiles, the mel-frontend share, process RSS, and the active ONNX Runtime
provider (so NPU claims are backed by evidence, per AGENTS.md).

Usage (from the repo root, inside the project venv):
    python scripts/benchmark_classifier.py --json docs/benchmarks/results.json
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _chunk_pcm16(seconds: float = 1.0, sample_rate: int = 16_000) -> bytes:
    """Synthesize a deterministic 1 kHz tone chunk like the demo audio uses."""
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = (0.4 * np.sin(2 * np.pi * 1000.0 * t) * 32767).astype("<i2")
    return tone.tobytes()


def _measure(classifier, pcm: bytes, runs: int, warmup: int) -> dict:
    for _ in range(warmup):
        classifier.classify_pcm16(pcm, 16_000, top_k=5)
    latencies = []
    for _ in range(runs):
        started = time.perf_counter()
        predictions = classifier.classify_pcm16(pcm, 16_000, top_k=5)
        latencies.append((time.perf_counter() - started) * 1_000)
    latencies.sort()
    return {
        "runs": runs,
        "mean_ms": round(statistics.fmean(latencies), 2),
        "p50_ms": round(latencies[len(latencies) // 2], 2),
        "p95_ms": round(latencies[int(len(latencies) * 0.95) - 1], 2),
        "min_ms": round(latencies[0], 2),
        "max_ms": round(latencies[-1], 2),
        "top_prediction": {
            "label": predictions[0].label,
            "confidence": round(predictions[0].confidence, 4),
        },
    }


def _frontend_ms(pcm: bytes, runs: int) -> float:
    from backend.inference.audio_features import waveform_to_patches

    waveform = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    waveform_to_patches(waveform)  # prime caches
    started = time.perf_counter()
    for _ in range(runs):
        waveform_to_patches(waveform)
    return round((time.perf_counter() - started) * 1_000 / runs, 3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument(
        "--variant",
        action="append",
        dest="variants",
        metavar="NAME=MODEL_PATH:TARGET",
        help=(
            "Model variant to measure, e.g. fp32-cpu=models/source/.../yamnet.onnx:cpu. "
            "Repeatable; default measures the float model on cpu and npu."
        ),
    )
    parser.add_argument("--json", type=Path, help="Write full results to this JSON file")
    args = parser.parse_args()

    from backend.inference.onnx_sound_classifier import DEFAULT_MODEL_PATH, OnnxSoundClassifier

    variants = []
    for spec in args.variants or [
        f"fp32-cpu={DEFAULT_MODEL_PATH}:cpu",
        f"fp32-npu={DEFAULT_MODEL_PATH}:npu",
    ]:
        name, _, rest = spec.partition("=")
        model_path, _, target = rest.rpartition(":")
        variants.append((name, Path(model_path), target))

    pcm = _chunk_pcm16()
    results: dict = {
        "host": {
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "chunk": {"seconds": 1.0, "sample_rate": 16_000, "content": "1 kHz sine"},
        "frontend_ms_per_chunk": _frontend_ms(pcm, args.runs),
        "variants": {},
    }

    try:
        import psutil

        process = psutil.Process()
    except ImportError:
        process = None

    for name, model_path, target in variants:
        print(f"[{name}] loading {model_path.name} target={target} ...")
        try:
            classifier = OnnxSoundClassifier(model_path=model_path, target=target)
        except Exception as exc:  # noqa: BLE001 — record the failure, keep measuring others
            print(f"[{name}] SKIPPED: {exc}")
            results["variants"][name] = {"error": str(exc)}
            continue
        measurement = _measure(classifier, pcm, args.runs, args.warmup)
        measurement["active_provider"] = classifier.active_provider
        measurement["model"] = str(model_path.relative_to(REPO_ROOT)) if model_path.is_relative_to(
            REPO_ROOT
        ) else str(model_path)
        if process is not None:
            measurement["rss_mb"] = round(process.memory_info().rss / (1024 * 1024), 1)
        results["variants"][name] = measurement
        print(
            f"[{name}] provider={measurement['active_provider']} "
            f"mean={measurement['mean_ms']}ms p95={measurement['p95_ms']}ms "
            f"top={measurement['top_prediction']['label']!r}"
        )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")


if __name__ == "__main__":
    main()
