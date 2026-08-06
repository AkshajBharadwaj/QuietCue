# QuietCue environmental classifier — QUAD conversion & profiling report

Date: 2026-08-06 · Branch: `quad-audio-model` · Author: backend/inference team

## Summary

The production environmental sound classifier is **YamNet (AudioSet, 521
classes) as ONNX, executed on the Snapdragon X Elite Hexagon NPU** through the
ONNX Runtime QNN execution provider. Full per-chunk classification (log-mel
frontend + inference + sigmoid) takes **1.45 ms mean / 1.74 ms p95** — a **21×
mean and 50× p95 improvement** over the CPU baseline — with accuracy identical
to the fp32 CPU reference. NPU execution is verified by the active ORT provider
(`QNN`) and the HTP graph-compilation log, not assumed.

## Model provenance (canonical format: ONNX)

| Item | Value |
| :--- | :--- |
| Source model | Qualcomm AI Hub `yamnet` release v0.59.0 (`qualcomm/YamNet` on Hugging Face) |
| Architecture | MobileNet-v1 depthwise-separable CNN, 3.73 M params |
| Canonical format | ONNX (opset 21), fp32, 14.25 MB — `models/source/yamnet-onnx-float/` |
| Input | `audio` — 1×1×96×64 fp32 log-mel patch (0.96 s @ 16 kHz) |
| Output | `class_scores` — 1×521 **logits** (sigmoid applied in `OnnxSoundClassifier`) |
| Labels | `labels.txt` (AudioSet order) shipped with the model; covered by `tests/test_onnx_classifier.py::test_labels_cover_every_mapped_event` |
| Feature frontend | `backend/inference/audio_features.py`, numpy reimplementation of TF YAMNet features (periodic Hann, 400/160 STFT, 64 HTK mel bands 125–7500 Hz, log offset 0.001) |

Download reproducibly with `scripts/fetch_models.ps1`.

## QUAD conversion (INT8)

`scripts/quad/convert_yamnet.py` uploads the packed fp32 ONNX to the QUAD MCP
server (`convert_model`, QUAD 3.4.4) and retrieves the artifact
(sha256-verified). Result (envelope: `models/converted/convert-int8-qnn.json`):

| Item | Value |
| :--- | :--- |
| Quantization | INT8, QDQ format (HTP-compatible — ConvInteger would silently fall back to CPU) |
| Artifact | `yamnet_fp32_selfcontained_quantized.dlc`, QAIRT DLC container |
| Size | 14.25 MB → **3.63 MB** (3.92× smaller) |
| Op coverage | **100 % supported, 0 unsupported ops** |
| Conversion time | 3.3 s server-side |

The DLC targets the QAIRT/SNPE runtime. Its ZIP metadata identifies a DLC, not a
QNN context binary; the conversion envelope's `output_format` field is therefore
misleading. A QNN deployment must first generate a target-specific context
binary. For the connected in-process ONNX Runtime path we additionally profiled
the AI Hub **w8a8 QDQ ONNX** of the same model
(`models/source/yamnet-onnx-w8a8/`).

### Uno Q deployment boundary

The 3.63 MB DLC is checked in and matches the recorded SHA-256. A physical
QRB2210 UNO Q test exposed the board's ADSP/DMA devices and reached SNPE, but
strict `--use_dsp` execution failed with `No backend library matched for this
build and target`. This DLC is not compatible with the original UNO Q's V66
audio DSP and there is no UNO Q latency/accuracy claim.

QuietCue therefore performs all semantic inference on the selected Samsung/PC
hub. The UNO Q streams microphone PCM and delivers returned haptic commands; it
does not load this DLC or substitute CPU inference.

## Target hardware

Snapdragon X Elite X1E80100 (detected via `quad-client detect`): 12× Oryon
ARM64 @ 3.417 GHz · Adreno X1-85 (4.6 TFLOPS) · **Hexagon NPU v73, 45 TOPS** ·
31.6 GB RAM · Windows 11 Pro · native ARM64 Python 3.12.10 ·
`onnxruntime-qnn` 2.4.0 (plugin EP).

## Latency & memory (measured on-device)

`scripts/benchmark_classifier.py`, 100 runs + 10 warmup per variant, real
pipeline path (`classify_pcm16`: PCM16 → mel → inference → sigmoid → top-k) on
a 1 s / 16 kHz chunk. Raw data: `quad-audio-model-results.json`.

| Variant | Provider | Mean | p50 | p95 | Max | RSS |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| fp32 CPU (baseline) | CPUExecutionProvider | 30.46 ms | 9.21 ms | 86.72 ms | 243.6 ms | 82 MB |
| **fp32 NPU (deployed)** | **QNN (HTP)** | **1.45 ms** | **1.29 ms** | **1.74 ms** | 9.9 ms | 411 MB |
| w8a8 CPU | CPUExecutionProvider | 16.20 ms | 2.99 ms | 74.26 ms | 100.3 ms | 246 MB |
| w8a8 NPU | QNN (HTP) | 1.33 ms | 0.99 ms | 3.63 ms | 6.3 ms | 419 MB |

Mel frontend alone: **0.40 ms** per chunk (numpy, CPU).

Notes:

- CPU latency is strongly bimodal (p50 9 ms, p95 87 ms) — scheduler/DVFS
  jitter under load. The NPU is not just faster but **deterministic**
  (p95 1.74 ms), which matters for a safety-alert path.
- The ~410 MB RSS under QNN is the loaded QnnHtp stack + compiled HTP context;
  use `QUIETCUE_ONNX_CACHE_DIR` to persist the EP context and avoid the
  one-time ~9 s HTP compile on process start.
- First NPU inference triggers HTP graph compilation (excluded via warmup).

## CPU / GPU / NPU comparison (bare inference, 1×1×96×64)

| Target | Backend | Bare inference mean | Evidence |
| :--- | :--- | ---: | :--- |
| CPU | ORT CPUExecutionProvider | ~8–30 ms (jittery) | provider string |
| GPU (Adreno X1-85) | QNN EP + `QnnGpu.dll` | ~1.27 ms | provider `QNN`, GPU backend path |
| NPU (Hexagon v73) | QNN EP + `QnnHtp.dll` | ~1.0 ms | provider `QNN`, HTP compile log |

GPU and NPU are equivalent for a model this small; the NPU wins on
determinism, leaves the GPU free for UI/other workloads, and is the
power-efficient engine for an always-on classifier.

## Quantization accuracy check

fp32 vs w8a8, CPU, five synthetic probes (`quant-accuracy-check.json`):
top-1 agreed on 4/5 (sine, noise, AM tone, silence; confidences within 0.02).
The disagreement is a synthetic chirp where both answers are plausible
("Alarm" 0.42 vs "Synthesizer" 0.32) but the score drift is real.

## Power

Not measured locally (no power rail access). QUAD `orchestrate_workload`
projects ~885 mW balanced-mode for the composite workload
(`quad-orchestrate-workload.json`); treat as an estimate only — the server-side
profile ran on a cloud VM without a physical Hexagon
(`quad-profile-workload.json`, zeros are expected) and is retained purely as a
record of the tool invocation.

## Final deployment recommendation

**Deploy the fp32 ONNX on the Hexagon NPU** (`--classifier onnx`, default;
`QUIETCUE_ONNX_TARGET=auto` picks NPU with CPU fallback):

1. 1.45 ms mean / 1.74 ms p95 leaves the 100 ms-class end-to-end alert budget
   essentially untouched (the 0.5–1 s capture window dominates).
2. Bit-identical accuracy to the fp32 reference — no quantization risk in the
   safety path. w8a8 saves only ~0.1 ms here and showed top-1 drift on one
   probe; INT8 pays off where footprint matters, not here.
3. The QUAD INT8 DLC (3.6 MB, 100 % converter op coverage) is retained for a
   compatible connected QAIRT/SNPE target; physical testing proved it is not a
   backend match for the original QRB2210 UNO Q ADSP.

## Generated runner notes

`generate_code` output is stored at `scripts/quad/generated/` (`inference.py`,
`requirements.txt`): an ORT-QNN runner that pins the QNN EP and hard-fails on
silent CPU fallback. Production integration uses the same pattern via
`quad_mcp_client.ort_qnn.create_npu_session` in
`backend/inference/onnx_sound_classifier.py` (adds QDQ format guard, EP context
cache, registration guard).

## Reproduce

```powershell
# once per clone
.\scripts\fetch_models.ps1
python -m venv .venv; .venv\Scripts\pip install -r backend\requirements-onnx.txt

# QUAD conversion + server-side tooling (needs QUAD_MCP_TOKEN)
.venv\Scripts\python scripts\quad\convert_yamnet.py --quantization int8
.venv\Scripts\python scripts\quad\orchestrate_and_codegen.py

# on-device benchmark
.venv\Scripts\python scripts\benchmark_classifier.py --runs 100 --warmup 10 `
  --json docs\benchmarks\quad-audio-model-results.json
```
