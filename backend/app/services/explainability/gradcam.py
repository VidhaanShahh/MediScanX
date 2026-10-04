"""
MediScanX — M8 Grad-CAM Explainability Service.

Generates Grad-CAM attention heatmaps using the ACTUAL M5 CheXNet
DenseNet-121 model.  The heatmap is an attention / plausibility
visualization of image regions associated with a selected model output.
It is NOT proof of disease location and NOT proof of causal reasoning.

Algorithm reference
-------------------
P3 § 9  "A8: Explainability"

Key formula (standard Grad-CAM, Selvaraju et al. 2017):
    alpha_k = mean(gradient_k over spatial dimensions)
    CAM     = ReLU( sum_k( alpha_k * feature_map_k ) )

Target layer
------------
``model.densenet121.features`` — the final convolutional feature-map
block of the DenseNet-121 architecture (before the adaptive-avg-pool
and classifier).  This is the standard Grad-CAM target for DenseNets.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F

from app.services.imaging.chexnet import (
    load_model,
    CLASS_NAMES,
    N_CLASSES,
    DenseNet121,
)

logger = logging.getLogger(__name__)


def generate_gradcam(
    preprocessed: np.ndarray,
    target_class: Optional[str] = None,
) -> dict:
    """
    Generate a Grad-CAM heatmap for a preprocessed chest X-ray image.

    Parameters
    ----------
    preprocessed : np.ndarray
        ImageNet-normalised float32 array of shape ``(224, 224, 3)`` as
        produced by the M4 preprocessing pipeline.
    target_class : str or None
        One of the 14 ChestX-ray14 class names.  If None, the
        highest-probability class from the M5 prediction is used.

    Returns
    -------
    dict with keys:
        heatmap       : np.ndarray of shape (224, 224), values in [0, 1]
        target_class  : str — the class used for the heatmap
        target_index  : int — the index of the class
        probabilities : dict[str, float] — all 14 class probabilities
        model_name    : str
        model_version : str

    Raises
    ------
    ValueError
        If target_class is supplied but is not one of the 14 classes.
    """
    # ── Validate target class ────────────────────────────────────
    if target_class is not None and target_class not in CLASS_NAMES:
        raise ValueError(
            f"Invalid target class '{target_class}'. "
            f"Must be one of: {CLASS_NAMES}"
        )

    # ── Load model (reuses singleton — does NOT reload) ──────────
    model = load_model()

    # ── Prepare input tensor ─────────────────────────────────────
    # HWC → CHW, add batch dim: (1, 3, 224, 224)
    tensor = torch.from_numpy(
        preprocessed.transpose(2, 0, 1).copy()
    ).unsqueeze(0).float()
    tensor.requires_grad_(False)

    # ── Register hooks on the final feature-map layer ────────────
    #
    # DenseNet121 structure:
    #   model.densenet121.features  → final conv feature maps
    #   model.densenet121.classifier → Linear + Sigmoid
    #
    # The features sub-module ends with norm5 + relu.
    # We hook the entire features block to get the output feature maps.

    feature_maps: list[torch.Tensor] = []
    gradients: list[torch.Tensor] = []

    def forward_hook(module, input, output):
        feature_maps.append(output.clone().detach())

    def backward_hook(module, grad_input, grad_output):
        gradients.append(grad_output[0].clone().detach())

    target_layer = model.densenet121.features.denseblock4
    fwd_handle = target_layer.register_forward_hook(forward_hook)
    bwd_handle = target_layer.register_full_backward_hook(backward_hook)

    try:
        # ── Forward pass (NO torch.no_grad — need gradients) ─────
        model.eval()
        output = model(tensor)  # shape: (1, 14)
        probs = output.squeeze(0).detach().cpu().numpy()  # (14,)

        # ── Determine target class ───────────────────────────────
        if target_class is None:
            target_index = int(np.argmax(probs))
            target_class = CLASS_NAMES[target_index]
        else:
            target_index = CLASS_NAMES.index(target_class)

        # ── Backward pass for target class ───────────────────────
        model.zero_grad()
        target_score = output[0, target_index]
        target_score.backward()

        # ── Compute Grad-CAM ─────────────────────────────────────
        if not gradients or not feature_maps:
            logger.warning("No gradients/feature maps captured; returning zero heatmap.")
            heatmap = np.zeros((224, 224), dtype=np.float32)
        else:
            grads = gradients[0]       # (1, C, H, W)
            fmaps = feature_maps[0]    # (1, C, H, W)

            # alpha_k = mean of gradient over spatial dimensions
            alpha = grads.mean(dim=(2, 3), keepdim=True)  # (1, C, 1, 1)

            # Weighted combination
            cam = (alpha * fmaps).sum(dim=1, keepdim=True)  # (1, 1, H, W)

            # ReLU
            cam = F.relu(cam)

            # Resize to input dimensions
            cam = F.interpolate(
                cam, size=(224, 224), mode="bilinear", align_corners=False
            )

            cam = cam.squeeze().detach().cpu().numpy()  # (224, 224)

            # ── Safe normalisation to [0, 1] ─────────────────────
            cam_min = cam.min()
            cam_max = cam.max()
            if cam_max - cam_min > 1e-8:
                heatmap = (cam - cam_min) / (cam_max - cam_min)
            else:
                # Constant or zero CAM → return zero heatmap
                heatmap = np.zeros_like(cam, dtype=np.float32)

            # Ensure finite values
            heatmap = np.nan_to_num(heatmap, nan=0.0, posinf=1.0, neginf=0.0)
            heatmap = heatmap.astype(np.float32)

    finally:
        fwd_handle.remove()
        bwd_handle.remove()

    # Build probabilities dict
    probabilities = {
        CLASS_NAMES[i]: float(probs[i]) for i in range(N_CLASSES)
    }

    return {
        "heatmap": heatmap,
        "target_class": target_class,
        "target_index": target_index,
        "probabilities": probabilities,
        "model_name": "CheXNet-DenseNet121",
        "model_version": "v1.0-chestxray14",
    }


def render_gradcam_overlay(
    original_image_path: str,
    heatmap: np.ndarray,
    alpha: float = 0.4,
    colormap: int | None = None,
) -> bytes:
    """
    Render a Grad-CAM heatmap overlay on the original X-ray image.

    Parameters
    ----------
    original_image_path : str
        Path to the original uploaded X-ray image file.
    heatmap : np.ndarray
        Grad-CAM heatmap of shape (224, 224), values in [0, 1].
    alpha : float
        Transparency for the heatmap overlay (0 = invisible, 1 = opaque).
    colormap : int or None
        OpenCV colormap constant. Defaults to cv2.COLORMAP_JET.

    Returns
    -------
    bytes : PNG image bytes of the overlay visualisation.

    Note
    ----
    The original medical image is NOT modified.  This function creates
    a separate overlay image for explanation purposes only.
    """
    import cv2
    from PIL import Image
    import io

    # Load original image
    orig = Image.open(original_image_path).convert("RGB")
    orig_w, orig_h = orig.size

    # Resize heatmap to original image dimensions
    heatmap_resized = cv2.resize(
        heatmap, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR
    )

    # Apply colormap
    if colormap is None:
        colormap = cv2.COLORMAP_JET
    heatmap_colored = cv2.applyColorMap(
        (heatmap_resized * 255).astype(np.uint8), colormap
    )
    heatmap_colored = cv2.cvtColor(heatmap_colored, cv2.COLOR_BGR2RGB)

    # Blend with original
    orig_array = np.array(orig)
    overlay = (
        (1 - alpha) * orig_array.astype(np.float32)
        + alpha * heatmap_colored.astype(np.float32)
    ).clip(0, 255).astype(np.uint8)

    # Encode to PNG bytes
    overlay_img = Image.fromarray(overlay)
    buf = io.BytesIO()
    overlay_img.save(buf, format="PNG")
    return buf.getvalue()
