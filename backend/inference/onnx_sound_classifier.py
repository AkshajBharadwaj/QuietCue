"""Production environmental sound classifier: quantized YamNet on ONNX Runtime.

Runs the Qualcomm AI Hub export of YAMNet (input: 1x1x96x64 log-mel patches,
output: 1x521 AudioSet class scores) through ONNX Runtime. Execution target is
selectable: "cpu" uses the default CPU provider, "npu" pins the session to the
Hexagon NPU through the QNN execution provider and fails loudly if the NPU is
not active, "auto" tries the NPU and falls back to CPU.

The feature frontend lives in backend.inference.audio_features; labels come
from the labels.txt shipped with the model so index order always matches.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np

from backend.inference.audio_features import MIN_WAVEFORM_SAMPLES, waveform_to_patches
from backend.inference.models import SoundPrediction

TARGET_SAMPLE_RATE = 16_000
LOGGER = logging.getLogger("quietcue.onnx_classifier")

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
W8A8_MODEL_DIR = DEFAULT_MODEL_DIR / "source" / "yamnet-onnx-w8a8" / "yamnet-onnx-w8a8"
FLOAT_MODEL_DIR = DEFAULT_MODEL_DIR / "source" / "yamnet-onnx-float" / "yamnet-onnx-float"
# The w8a8 export is checked in; the float export (15 MB) is fetched by
# scripts/fetch_models.sh. Both share the same label order.
DEFAULT_MODEL_PATH = W8A8_MODEL_DIR / "yamnet.onnx"
DEFAULT_LABELS_PATH = W8A8_MODEL_DIR / "labels.txt"
PRECISIONS = ("auto", "float", "w8a8")


def resolve_model_paths(precision: str = "auto") -> tuple[Path, Path, str]:
    """Pick the YAMNet export to load: (model_path, labels_path, precision).

    "float" is preferred on a hub with CPU headroom: the w8a8 export's output
    quantization step (~0.76 logits) collapses post-sigmoid confidences onto a
    ladder (0.32 / 0.50 / 0.68 / 0.82 ...), so profile thresholds in between
    are unreachable. "auto" uses float when it has been downloaded, else w8a8.
    """
    if precision not in PRECISIONS:
        raise ValueError(f"Unknown precision {precision!r}; expected one of {PRECISIONS}")
    float_model = FLOAT_MODEL_DIR / "yamnet.onnx"
    if precision == "float" or (precision == "auto" and float_model.is_file()):
        return float_model, FLOAT_MODEL_DIR / "labels.txt", "float"
    return DEFAULT_MODEL_PATH, DEFAULT_LABELS_PATH, "w8a8"


class OnnxSoundClassifier:
    """YamNet ONNX wrapper satisfying the pipeline's SoundClassifier protocol."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        labels_path: str | Path = DEFAULT_LABELS_PATH,
        target: str = "auto",
        cache_dir: str | Path | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"ONNX model not found: {self.model_path}. "
                "Run scripts/fetch_models.ps1 to download it."
            )
        self._class_names = self._load_labels(Path(labels_path))
        self._warned_short_chunk = False
        self.target = target
        self._session = self._create_session(target, cache_dir)
        self.active_provider = self._session.get_providers()[0]
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name
        # Quantized (QDQ) exports take pre-quantized activations: uint8/int8
        # in, quantized logits out. Read the scale/zero-point pairs once.
        self._input_quant = self._output_quant = None
        input_type = self._session.get_inputs()[0].type
        if input_type in ("tensor(uint8)", "tensor(int8)"):
            self._input_quant, self._output_quant = self._load_quant_params()

    @staticmethod
    def _load_labels(labels_path: Path) -> list[str]:
        labels = [line.strip() for line in labels_path.read_text(encoding="utf-8").splitlines()]
        labels = [label for label in labels if label]
        if len(labels) != 521:
            raise ValueError(f"Expected 521 AudioSet labels, found {len(labels)} in {labels_path}")
        return labels

    def _load_quant_params(self) -> tuple[tuple[float, int, type], tuple[float, int]]:
        """Read input/output (scale, zero_point) from the QDQ graph boundary."""
        import onnx
        from onnx import numpy_helper

        model = onnx.load(str(self.model_path), load_external_data=False)
        graph = model.graph
        initializers = {init.name: init for init in graph.initializer}

        def quant_pair(node) -> tuple[float, int]:
            scale = float(numpy_helper.to_array(initializers[node.input[1]]))
            zero_point = int(numpy_helper.to_array(initializers[node.input[2]]))
            return scale, zero_point

        input_name = graph.input[0].name
        output_name = graph.output[0].name
        input_quant = output_quant = None
        for node in graph.node:
            if node.op_type == "DequantizeLinear" and node.input[0] == input_name:
                scale, zero_point = quant_pair(node)
                dtype = np.uint8 if graph.input[0].type.tensor_type.elem_type == 2 else np.int8
                input_quant = (scale, zero_point, dtype)
            if node.op_type == "QuantizeLinear" and output_name in node.output:
                output_quant = quant_pair(node)
        if input_quant is None:
            raise ValueError(f"Could not find input quantization params in {self.model_path}")
        return input_quant, output_quant

    def _prepare_patch(self, patch: np.ndarray) -> np.ndarray:
        if self._input_quant is None:
            return patch[np.newaxis, np.newaxis]
        scale, zero_point, dtype = self._input_quant
        info = np.iinfo(dtype)
        quantized = np.clip(np.round(patch / scale) + zero_point, info.min, info.max)
        return quantized.astype(dtype)[np.newaxis, np.newaxis]

    def _to_logits(self, raw: np.ndarray) -> np.ndarray:
        if self._output_quant is None:
            return raw.astype(np.float64)
        scale, zero_point = self._output_quant
        return (raw.astype(np.float64) - zero_point) * scale

    def _create_session(self, target: str, cache_dir: str | Path | None):
        if target == "cpu":
            import onnxruntime as ort

            return ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        if target == "npu":
            try:
                from quad_mcp_client.ort_qnn import create_npu_session
            except ImportError as exc:
                raise RuntimeError(
                    "NPU target requires the QUAD client; install quad-mcp-client first"
                ) from exc
            return create_npu_session(self.model_path, cache_dir=cache_dir)
        if target == "auto":
            try:
                from quad_mcp_client.ort_qnn import NPUFallbackError, create_npu_session
            except ImportError as exc:
                LOGGER.info("QUAD NPU runtime unavailable; using ONNX CPU: %s", exc)
            else:
                try:
                    return create_npu_session(self.model_path, cache_dir=cache_dir)
                except (NPUFallbackError, OSError, RuntimeError) as exc:
                    LOGGER.warning("NPU initialization failed; using ONNX CPU: %s", exc)

            import onnxruntime as ort

            return ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
        raise ValueError(f"Unknown execution target: {target} (expected cpu, npu, or auto)")

    def classify(self, waveform: np.ndarray, top_k: int = 5) -> list[SoundPrediction]:
        """Return the highest mean-confidence classes across all 0.96 s patches."""
        if waveform.ndim != 1:
            raise ValueError("Expected a one-dimensional mono waveform")
        if waveform.size == 0:
            raise ValueError("Cannot classify empty audio")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        if waveform.size < MIN_WAVEFORM_SAMPLES and not self._warned_short_chunk:
            self._warned_short_chunk = True
            LOGGER.warning(
                "Chunk of %d samples is shorter than one %d-sample patch; it is zero-padded, "
                "which dilutes confidences. Stream chunks of at least 1 s.",
                waveform.size,
                MIN_WAVEFORM_SAMPLES,
            )
        patches = waveform_to_patches(waveform)
        logits = np.vstack(
            [
                self._to_logits(
                    self._session.run(
                        [self._output_name], {self._input_name: self._prepare_patch(patch)}
                    )[0][0]
                )
                for patch in patches
            ]
        )
        # The AI Hub export ends at the classifier Gemm: outputs are logits.
        # YAMNet's published scores are independent per-class sigmoids, and the
        # event mapper thresholds assume [0, 1] confidences.
        scores = 1.0 / (1.0 + np.exp(-logits))
        mean_scores = scores.mean(axis=0)
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
            raise ValueError(f"YamNet ONNX requires {TARGET_SAMPLE_RATE} Hz audio")
        if len(pcm) < 2 or len(pcm) % 2:
            raise ValueError("PCM16 payload must contain complete samples")
        waveform = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        return self.classify(waveform, top_k=top_k)

    def classify_wav(self, path: str | Path, top_k: int = 5) -> list[SoundPrediction]:
        """Load and classify a WAV file."""
        from backend.inference.sound_classifier import load_wav

        return self.classify(load_wav(path), top_k=top_k)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify environmental sounds in a PCM WAV file with YamNet ONNX."
    )
    parser.add_argument("wav_file", type=Path, help="Path to an uncompressed PCM WAV file")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument("--target", choices=("cpu", "npu", "auto"), default="auto")
    parser.add_argument("--top-k", type=int, default=5, help="Number of predictions to show")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    classifier = OnnxSoundClassifier(args.model, args.labels, target=args.target)
    started = time.perf_counter()
    predictions = classifier.classify_wav(args.wav_file, top_k=args.top_k)
    elapsed_ms = (time.perf_counter() - started) * 1_000

    print(f"Provider: {classifier.active_provider}  ({elapsed_ms:.1f} ms)")
    print(f"Predictions for {args.wav_file}:")
    for rank, prediction in enumerate(predictions, start=1):
        print(f"{rank:>2}. {prediction.label:<35} {prediction.confidence:.3f}")


if __name__ == "__main__":
    main()
