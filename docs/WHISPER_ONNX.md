# Whisper ONNX speech and name detection

QuietCue now has two local speech implementations behind the same profile rules:

- the computer hub uses lazy Faster-Whisper (`base.en` by default);
- the Samsung hub uses a lazy ONNX encoder/decoder on a dedicated worker.

Environmental classification never waits for speech decoding. A disabled speech
path does not load a model, and reconnecting an Uno Q clears buffered speech and
invalidates pending results.

## Verified model contract

The implementation follows Qualcomm AI Hub Models' current `whisper_tiny` /
shared Hugging Face Whisper wrapper, verified on August 6, 2026. The published
model is multilingual `openai/whisper-tiny`, not an English-only checkpoint.
QuietCue forces the English, transcribe, and no-timestamps decoder prefix to
provide the `TINY_EN` behavior exposed in settings.

The accepted ONNX pair is deliberately strict:

- encoder input: `input_features`, float32 `[1, 80, 3000]`;
- encoder outputs: `k_cache_cross_N` and `v_cache_cross_N`;
- decoder inputs: one int32 `input_ids` token, float32 `attention_mask`, explicit
  self/cross caches, and int32 `position_ids`;
- decoder outputs: float32 `logits` `[1, vocabulary, 1, 1]` and updated self caches;
- maximum decode length: the fixed attention-mask length (the AI Hub model uses 200).

Both the Python oracle and Android loader reject a mismatched graph before
inference. Cache layer count is derived from the graph, so Tiny and Base do not
share a hard-coded layer count.

The current Qualcomm release advertises `precompiled_qnn_onnx`, QNN context, and
Voice AI artifacts. A precompiled QNN graph is not treated as a drop-in CPU model
for the standard `onnxruntime-android` AAR. QuietCue therefore accepts a vanilla
float32 ONNX export for the phone CPU path and makes no NPU claim. QNN/NPU work
remains a measured optimization step.

Primary references:

- <https://aihub.qualcomm.com/compute/models/whisper_tiny>
- <https://github.com/qualcomm/ai-hub-models/tree/main/qai_hub_models/models/whisper_tiny>
- <https://github.com/qualcomm/ai-hub-models/tree/main/qai_hub_models/models/_shared/hf_whisper>

## Stage model assets

Model weights are intentionally ignored by Git. Obtain or export a float32 ONNX
encoder/decoder pair with the contract above, then run:

```bash
python3 -m venv .venv-whisper-onnx
source .venv-whisper-onnx/bin/activate
python -m pip install -r backend/requirements-whisper-onnx.txt
python scripts/prepare_whisper_assets.py \
  --model tiny \
  --encoder /path/to/encoder.onnx \
  --decoder /path/to/decoder.onnx
```

Use `--model base` for the Base choice. The preparation command validates every
input/output, copies any same-directory ONNX external-data files, generates the
byte-level vocabulary asset from the matching Hugging Face tokenizer, and stages:

```text
models/source/whisper/
  tiny/encoder.onnx
  tiny/decoder.onnx
  tiny/vocabulary.json
  base/...
```

The Android build includes these directories as assets. Missing files do not
break environmental inference; the first gated speech attempt reports an explicit
speech-model error on the dashboard.

## Python oracle and tensor dumps

Before installing on a phone, run the exact ONNX pair on a mono 16 kHz PCM16 WAV:

```bash
python scripts/whisper_onnx_reference.py \
  --encoder models/source/whisper/tiny/encoder.onnx \
  --decoder models/source/whisper/tiny/decoder.onnx \
  --vocabulary models/source/whisper/tiny/vocabulary.json \
  --wav /path/to/approved-diagnostic.wav \
  --dump-dir .quietcue/whisper_reference/tiny
```

The dump contains mel features, encoder cross caches, the first eight decoder
logit tensors, token IDs, model contract, and stage timings. It does not copy raw
audio or write transcript text. Only explicitly approved synthetic fixtures belong
under `tests/fixtures/whisper_reference/`.

## Runtime resolution

Speech runs when the profile is `ALWAYS_ON`, or when it is `INHERIT` and the
global master switch is enabled. `OFF` always wins. Trigger phrases are the
deduplicated union of:

- global phrases;
- identity name, pronunciation, aliases, and approved recognition phrases when enabled;
- known-person names and aliases only when that opt-in is enabled;
- active-profile phrases;
- bounded legacy phrases supplied with an audio chunk.

Work / School defaults to `ALWAYS_ON` with “front desk.” Sleep / Night defaults
to `OFF`. A recognized phrase becomes only a `name_called` attention event and
then passes through the normal per-profile threshold, quiet-hours, and cooldown
rules.

Transcripts remain in worker memory only. Wire responses, dashboard state, event
history, and JSONL output contain no transcript; the matched configured phrase and
confidence are the only speech-derived event metadata.
