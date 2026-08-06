"""Tests for the ONNX environmental classifier and its event-mapper contract."""

import numpy as np
import pytest

from backend.inference.event_mapper import _EVENT_TERMS, _SPEECH_TERMS
from backend.inference.onnx_sound_classifier import (
    DEFAULT_LABELS_PATH,
    DEFAULT_MODEL_PATH,
    OnnxSoundClassifier,
)

requires_model = pytest.mark.skipif(
    not DEFAULT_MODEL_PATH.is_file(), reason="model not downloaded (scripts/fetch_models.ps1)"
)
onnxruntime = pytest.importorskip("onnxruntime")


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


@requires_model
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
