"""
Tests for M8 Explainability (Grad-CAM and ECG Saliency)
"""

import os
from pathlib import Path
import numpy as np

import pytest

from app.services.explainability.gradcam import generate_gradcam, render_gradcam_overlay
from app.services.explainability.ecg_saliency import generate_ecg_saliency, render_ecg_saliency


@pytest.fixture
def mock_preprocessed_image():
    # M4 image shape: (224, 224, 3) ImageNet normalized
    return np.random.randn(224, 224, 3).astype(np.float32)


@pytest.fixture
def mock_preprocessed_ecg():
    # M4 ECG shape: (1000, 12) or (12, 1000)
    return np.random.randn(1000, 12).astype(np.float32)


def test_generate_gradcam_valid_target(mock_preprocessed_image):
    result = generate_gradcam(mock_preprocessed_image, target_class="Atelectasis")
    
    assert "heatmap" in result
    assert result["heatmap"].shape == (224, 224)
    assert 0.0 <= result["heatmap"].min()
    assert result["heatmap"].max() <= 1.0 + 1e-6
    assert result["target_class"] == "Atelectasis"
    assert "model_name" in result


def test_generate_gradcam_default_target(mock_preprocessed_image):
    result = generate_gradcam(mock_preprocessed_image, target_class=None)
    
    assert "heatmap" in result
    assert result["heatmap"].shape == (224, 224)
    assert result["target_class"] is not None
    assert "probabilities" in result


def test_generate_gradcam_invalid_target(mock_preprocessed_image):
    with pytest.raises(ValueError, match="Invalid target class"):
        generate_gradcam(mock_preprocessed_image, target_class="FakeDisease")


def test_render_gradcam_overlay(tmp_path, mock_preprocessed_image):
    import cv2
    import numpy as np
    
    # Create a dummy original image
    orig_path = tmp_path / "dummy.png"
    cv2.imwrite(str(orig_path), np.zeros((1024, 1024, 3), dtype=np.uint8))
    
    heatmap = np.random.rand(224, 224).astype(np.float32)
    
    overlay_bytes = render_gradcam_overlay(str(orig_path), heatmap)
    assert isinstance(overlay_bytes, bytes)
    assert overlay_bytes.startswith(b'\x89PNG')


def test_generate_ecg_saliency_valid_target(mock_preprocessed_ecg):
    result = generate_ecg_saliency(mock_preprocessed_ecg, target_class="MI")
    
    assert "saliency" in result
    assert result["saliency"].shape == (1000, 12)
    assert 0.0 <= result["saliency"].min()
    assert result["saliency"].max() <= 1.0 + 1e-6
    assert result["target_class"] == "MI"
    assert "model_name" in result


def test_generate_ecg_saliency_default_target(mock_preprocessed_ecg):
    result = generate_ecg_saliency(mock_preprocessed_ecg, target_class=None)
    
    assert "saliency" in result
    assert result["saliency"].shape == (1000, 12)
    assert result["target_class"] == "risk_1_minus_NORM"
    assert "probabilities" in result


def test_generate_ecg_saliency_invalid_target(mock_preprocessed_ecg):
    with pytest.raises(ValueError, match="Invalid target class"):
        generate_ecg_saliency(mock_preprocessed_ecg, target_class="FakeDisease")


def test_render_ecg_saliency(mock_preprocessed_ecg):
    saliency = np.random.rand(1000, 12).astype(np.float32)
    
    saliency_bytes = render_ecg_saliency(mock_preprocessed_ecg, saliency)
    assert isinstance(saliency_bytes, bytes)
    assert saliency_bytes.startswith(b'\x89PNG')

