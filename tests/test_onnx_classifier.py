"""Tests for the ONNX environmental classifier and its event-mapper contract."""

import importlib.util
import sys
import unittest
from types import SimpleNamespace

try:
    import numpy as np
    import pytest
except ModuleNotFoundError as exc:
    raise unittest.SkipTest("numpy and pytest are optional ONNX test dependencies") from exc

from backend.inference.event_mapper import _EVENT_TERMS, _GENERIC_EVENT_TERMS, _SPEECH_TERMS
from backend.inference.onnx_sound_classifier import (
    DEFAULT_LABELS_PATH,
    DEFAULT_MODEL_PATH,
    FLOAT_MODEL_DIR,
    OnnxSoundClassifier,
    resolve_model_paths,
)

requires_runtime_and_model = pytest.mark.skipif(
    importlib.util.find_spec("onnxruntime") is None or not DEFAULT_MODEL_PATH.is_file(),
    reason="ONNX Runtime or model unavailable (run scripts/fetch_models.ps1)",
)


@pytest.fixture(scope="module")
def classifier() -> OnnxSoundClassifier:
    return OnnxSoundClassifier(target="cpu")


def test_labels_cover_every_mapped_event():
    """Every QuietCue event must be reachable from the model's label set."""
    labels = [
        line.strip().lower()
        for line in DEFAULT_LABELS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(labels) == 521
    for event, terms in _EVENT_TERMS.items():
        assert any(
            term in label for term in terms for label in labels
        ), f"no model label matches event {event!r}"
    assert any(term in label for term in _SPEECH_TERMS for label in labels)
    for event, terms in _GENERIC_EVENT_TERMS.items():
        for term in terms:
            assert term in labels, f"generic term {term!r} for {event!r} is not an exact model label"


def test_resolve_model_paths_prefers_float_when_present():
    model, labels, precision = resolve_model_paths("w8a8")
    assert (model, labels, precision) == (DEFAULT_MODEL_PATH, DEFAULT_LABELS_PATH, "w8a8")
    model, labels, precision = resolve_model_paths("float")
    assert (model, labels, precision) == (
        FLOAT_MODEL_DIR / "yamnet.onnx",
        FLOAT_MODEL_DIR / "labels.txt",
        "float",
    )
    auto = resolve_model_paths("auto")
    assert auto[2] == ("float" if (FLOAT_MODEL_DIR / "yamnet.onnx").is_file() else "w8a8")
    with pytest.raises(ValueError, match="precision"):
        resolve_model_paths("int4")


@requires_runtime_and_model
def test_float_export_produces_continuous_confidences():
    """The w8a8 export collapses scores onto a ladder; float must not."""
    if not (FLOAT_MODEL_DIR / "yamnet.onnx").is_file():
        pytest.skip("float model not downloaded (run scripts/fetch_models.sh)")
    classifier = OnnxSoundClassifier(
        FLOAT_MODEL_DIR / "yamnet.onnx", FLOAT_MODEL_DIR / "labels.txt", target="cpu"
    )
    assert classifier._input_quant is None and classifier._output_quant is None
    rng = np.random.default_rng(0)
    seen = set()
    for _ in range(3):
        pcm = (rng.standard_normal(16_000) * 2_000).astype("<i2").tobytes()
        seen.update(round(p.confidence, 3) for p in classifier.classify_pcm16(pcm, 16_000, top_k=10))
    ladder = {0.0104, 0.022, 0.0459, 0.0931, 0.1798, 0.3189, 0.5, 0.6811, 0.8202}
    assert len(seen - ladder) > len(seen) // 2


def test_cpu_target_does_not_require_quad_client(monkeypatch, tmp_path):
    expected_session = object()
    runtime = SimpleNamespace(
        InferenceSession=lambda path, providers: (
            expected_session
            if path == str(tmp_path / "model.onnx") and providers == ["CPUExecutionProvider"]
            else None
        )
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", runtime)

    classifier = object.__new__(OnnxSoundClassifier)
    classifier.model_path = tmp_path / "model.onnx"

    assert classifier._create_session("cpu", cache_dir=None) is expected_session


@requires_runtime_and_model
class TestOnnxSoundClassifier:
    def test_rejects_wrong_sample_rate(self, classifier):
        with pytest.raises(ValueError, match="16000"):
            classifier.classify_pcm16(b"\x00\x00", 44_100)

    def test_rejects_partial_samples(self, classifier):
        with pytest.raises(ValueError, match="complete samples"):
            classifier.classify_pcm16(b"\x00\x00\x00", 16_000)

    def test_rejects_empty_waveform(self, classifier):
        with pytest.raises(ValueError, match="empty"):
            classifier.classify(np.array([], dtype=np.float32))

    def test_classifies_one_second_chunk(self, classifier):
        t = np.arange(16_000) / 16_000.0
        tone = (0.4 * np.sin(2 * np.pi * 1_000.0 * t) * 32767).astype("<i2")
        predictions = classifier.classify_pcm16(tone.tobytes(), 16_000, top_k=5)
        assert len(predictions) == 5
        confidences = [prediction.confidence for prediction in predictions]
        assert confidences == sorted(confidences, reverse=True)
        assert all(0.0 <= confidence <= 1.0 for confidence in confidences)
        assert all(prediction.label for prediction in predictions)

    def test_silence_is_not_an_alert_class(self, classifier):
        silence = np.zeros(16_000, dtype="<i2").tobytes()
        top = classifier.classify_pcm16(silence, 16_000, top_k=1)[0]
        alert_labels = {
            "fire alarm",
            "smoke detector, smoke alarm",
            "siren",
            "vehicle horn, car horn, honking",
        }
        assert top.label.lower() not in alert_labels

    def test_satisfies_pipeline_protocol(self, classifier):
        from backend.inference.pipeline import HubInferencePipeline

        pipeline = HubInferencePipeline(classifier)
        silence = np.zeros(16_000, dtype="<i2").tobytes()
        result = pipeline.process_pcm16(silence, 16_000)
        assert result.inference_ms >= 0.0
        assert len(result.top_predictions) == 5
