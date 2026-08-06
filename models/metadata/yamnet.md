# YAMNet (fixed-shape TFLite)

- **File:** `models/source/yamnet.tflite`
- **Provenance:** https://tfhub.dev/google/lite-model/yamnet/tflite/1 (downloaded 2026-08-05 via the
  `?lite-format=tflite` redirect; the raw GCS bucket link is no longer anonymously accessible)
- **Size:** 16,096,668 bytes
- **SHA-256:** `141fba1cdaae842c816f28edc4937e8b4f0af4c8df21862ccc6b52dc567993c3`
- **License:** Apache 2.0 (Google)

## Input spec

- Single input tensor: `float32[15600]` — a raw mono waveform.
- 15,600 samples at 16 kHz = **0.975 s** analysis window.
- Samples normalized to `[-1.0, 1.0]` (same normalization `backend/inference/sound_classifier.py`
  already applies to PCM16: `sample / 32768.0`).
- No spectrogram preprocessing required — the model computes its own mel features internally.

## Output spec

- `scores`: `float32[N, 521]` — per-frame scores over the 521 AudioSet classes
  (same class map the TF Hub SavedModel uses; class CSV ships inside the TFLite as an
  associated file).
- `embeddings`: `float32[N, 1024]`
- `log_mel_spectrogram`: `float32[M, 64]`

For QuietCue only `scores` matters; mean over frames then map via
`backend/inference/event_mapper.py`, identical to the hub path.

## Why this artifact

The TF Hub SavedModel used by the hub has a dynamic-length input, which QNN/SNPE converters
cannot bind. This TFLite export has the concrete `[15600]` shape required for INT8 conversion
targeting the Uno Q's Hexagon V66 (SNPE DLC) or the Snapdragon X Elite NPU (QNN, Hexagon v73).

Feeding it from the live pipeline: one 0.975 s window = 15,600 samples = 31,200 bytes of the
16 kHz mono PCM16 stream the transport already delivers.
