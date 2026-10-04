"""
MediScanX — Unit tests for M5 (Imaging AI).

Tests:
    1.  CheXNet model loads successfully from checkpoint
    2.  Model architecture has 14 output classes
    3.  Inference on synthetic image returns 14 probabilities
    4.  Probabilities are valid sigmoid outputs (0 ≤ p ≤ 1)
    5.  Inference on preprocessed real ChestX-ray14 image
    6.  predict_image rejects wrong input shape
    7.  predict_image rejects non-ndarray input
    8.  CLASS_NAMES has correct 14 labels
    9.  Model metadata returns expected structure
    10. Model is loaded once (singleton reuse)
    11. reset_model clears cached model
    12. End-to-end preprocessing → inference pipeline
"""

import os
import sys

import numpy as np
import pytest

# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

# Path to a real ChestX-ray14 image for integration testing
_SAMPLE_IMAGE = os.path.join(
    os.path.dirname(__file__), "..", "data", "ChestX-ray14", "images", "00000001_000.png"
)

# Flag: skip heavyweight tests if checkpoint is not available
_CKPT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "models", "imaging", "model.pth.tar"
)
_HAS_CHECKPOINT = os.path.isfile(_CKPT_PATH)

requires_checkpoint = pytest.mark.skipif(
    not _HAS_CHECKPOINT,
    reason="CheXNet checkpoint not found — skipping inference tests",
)

requires_sample_image = pytest.mark.skipif(
    not os.path.isfile(_SAMPLE_IMAGE),
    reason="Sample ChestX-ray14 image not found",
)


# ════════════════════════════════════════════════════════════════
# 1. Model loads successfully
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_model_loads():
    from app.services.imaging.chexnet import load_model, reset_model

    reset_model()
    model = load_model()
    assert model is not None


# ════════════════════════════════════════════════════════════════
# 2. Model architecture has 14 output classes
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_model_has_14_classes():
    from app.services.imaging.chexnet import load_model
    import torch

    model = load_model()
    # Get the classifier Linear layer
    classifier = model.densenet121.classifier
    linear = classifier[0]  # nn.Sequential(Linear, Sigmoid)
    assert linear.out_features == 14


# ════════════════════════════════════════════════════════════════
# 3. Inference on synthetic image returns 14 probabilities
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_inference_synthetic_image():
    from app.services.imaging.chexnet import predict_image

    # Create a synthetic preprocessed image (ImageNet-normalised, shape 224×224×3)
    fake_input = np.random.randn(224, 224, 3).astype(np.float32)
    result = predict_image(fake_input)

    assert len(result.predictions) == 14
    assert result.num_classes == 14
    assert result.inference_ms > 0


# ════════════════════════════════════════════════════════════════
# 4. Probabilities are valid sigmoid outputs
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_probabilities_in_range():
    from app.services.imaging.chexnet import predict_image

    fake_input = np.random.randn(224, 224, 3).astype(np.float32)
    result = predict_image(fake_input)

    for pred in result.predictions:
        assert 0.0 <= pred.probability <= 1.0, (
            f"{pred.disease}: probability {pred.probability} out of [0, 1]"
        )


# ════════════════════════════════════════════════════════════════
# 5. Inference on real ChestX-ray14 image
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
@requires_sample_image
def test_inference_real_image():
    from app.services.imaging.chexnet import predict_image
    from app.services.preprocessing.image import preprocess_image

    preprocessed, poor = preprocess_image(_SAMPLE_IMAGE)
    result = predict_image(preprocessed)

    assert len(result.predictions) == 14
    # All probabilities must be valid
    for pred in result.predictions:
        assert 0.0 <= pred.probability <= 1.0
    # At least one class should have a non-trivial probability
    probs = [p.probability for p in result.predictions]
    assert max(probs) > 0.0


# ════════════════════════════════════════════════════════════════
# 6. Rejects wrong input shape
# ════════════════════════════════════════════════════════════════

def test_predict_rejects_wrong_shape():
    from app.services.imaging.chexnet import predict_image
    from app.core.exceptions import InferenceError

    wrong_shape = np.random.randn(128, 128, 3).astype(np.float32)
    with pytest.raises(InferenceError, match="shape"):
        predict_image(wrong_shape)


# ════════════════════════════════════════════════════════════════
# 7. Rejects non-ndarray input
# ════════════════════════════════════════════════════════════════

def test_predict_rejects_non_ndarray():
    from app.services.imaging.chexnet import predict_image
    from app.core.exceptions import InferenceError

    with pytest.raises(InferenceError, match="ndarray"):
        predict_image("not an array")  # type: ignore[arg-type]


# ════════════════════════════════════════════════════════════════
# 8. CLASS_NAMES are correct
# ════════════════════════════════════════════════════════════════

def test_class_names():
    from app.services.imaging.chexnet import CLASS_NAMES, N_CLASSES

    expected = [
        "Atelectasis", "Cardiomegaly", "Effusion", "Infiltration",
        "Mass", "Nodule", "Pneumonia", "Pneumothorax",
        "Consolidation", "Edema", "Emphysema", "Fibrosis",
        "Pleural_Thickening", "Hernia",
    ]
    assert CLASS_NAMES == expected
    assert N_CLASSES == 14
    assert len(CLASS_NAMES) == N_CLASSES


# ════════════════════════════════════════════════════════════════
# 9. Model metadata
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_model_metadata():
    from app.services.imaging.chexnet import load_model, get_model_metadata

    load_model()
    meta = get_model_metadata()

    assert meta["model_name"] == "CheXNet-DenseNet121"
    assert meta["model_version"] == "v1.0-chestxray14"
    assert meta["num_classes"] == 14
    assert len(meta["class_names"]) == 14
    assert meta["checkpoint"] is not None


# ════════════════════════════════════════════════════════════════
# 10. Singleton reuse — model loaded only once
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_singleton_reuse():
    from app.services.imaging.chexnet import load_model, _holder

    m1 = load_model()
    m2 = load_model()
    assert m1 is m2  # Same object — not reloaded


# ════════════════════════════════════════════════════════════════
# 11. reset_model clears cache
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_reset_model():
    from app.services.imaging.chexnet import load_model, reset_model, _holder

    load_model()
    assert _holder.is_loaded()

    reset_model()
    assert not _holder.is_loaded()

    # Reload should work
    m = load_model()
    assert m is not None


# ════════════════════════════════════════════════════════════════
# 12. End-to-end: preprocessing → inference
# ════════════════════════════════════════════════════════════════

@requires_checkpoint
def test_end_to_end_synthetic():
    from app.services.imaging.chexnet import predict_image
    from app.services.preprocessing.image import preprocess_image

    # Create a synthetic 512×512 grayscale image
    raw = np.random.randint(50, 200, (512, 512), dtype=np.uint8)
    preprocessed, poor = preprocess_image(raw)

    assert preprocessed.shape == (224, 224, 3)

    result = predict_image(preprocessed)
    assert len(result.predictions) == 14
    assert result.model_name == "CheXNet-DenseNet121"
    assert result.model_version == "v1.0-chestxray14"
