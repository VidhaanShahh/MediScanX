"""
MediScanX — M4 Image preprocessing service.

Implements Algorithm A2 from P3 exactly:

    1. Load image / DICOM
    2. Convert to grayscale where required
    3. Optional CLAHE (clip=2.0, tiles=8×8)
    4. Resize to 224×224
    5. Detect / flag low contrast  (std < 10)
    6. Normalise to [0, 1]
    7. Copy into 3 channels
    8. ImageNet normalisation
    9. Return NumPy array of shape (224, 224, 3)
"""

import io
from pathlib import Path

import cv2
import numpy as np

from app.core.exceptions import PreprocessingError

# ImageNet channel statistics (RGB order)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

TARGET_SIZE = (224, 224)
LOW_CONTRAST_THRESHOLD = 10.0
CLAHE_CLIP = 2.0
CLAHE_TILE = (8, 8)


def preprocess_image(
    source: str | bytes | np.ndarray,
    *,
    use_clahe: bool = False,
) -> tuple[np.ndarray, bool]:
    """
    Preprocess a chest image for DenseNet-121 inference.

    Parameters
    ----------
    source : file path (str), raw bytes, or already-decoded ndarray
    use_clahe : apply CLAHE contrast enhancement

    Returns
    -------
    (tensor, poor_quality)
        tensor      — float32 ndarray of shape (224, 224, 3), ImageNet-normalised
        poor_quality — True if the image had very low contrast
    """
    img = _load(source)
    img = _to_grayscale(img)

    if use_clahe:
        img = _apply_clahe(img)

    img = cv2.resize(img, TARGET_SIZE, interpolation=cv2.INTER_AREA)

    # Flag low-contrast (P3 §3: std < 10)
    poor_quality = float(np.std(img)) < LOW_CONTRAST_THRESHOLD

    # Normalise to [0, 1]
    x = img.astype(np.float32) / 255.0

    # 3-channel (P3: "copy x into 3 channels")
    x = np.stack([x, x, x], axis=-1)  # (224, 224, 3)

    # ImageNet normalisation (P3: "(x - imagenet_mean) / imagenet_std")
    x = (x - IMAGENET_MEAN) / IMAGENET_STD

    return x, poor_quality


# ── Internal helpers ─────────────────────────────────────────────

def _load(source: str | bytes | np.ndarray) -> np.ndarray:
    """Load an image from path, bytes, or pass-through ndarray."""
    if isinstance(source, np.ndarray):
        return source

    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise PreprocessingError(f"Image file not found: {path}")

        ext = path.suffix.lower()
        if ext in (".dcm", ".dicom"):
            return _load_dicom(path)

        img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise PreprocessingError(f"Cannot decode image: {path}")
        return img

    if isinstance(source, bytes):
        buf = np.frombuffer(source, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise PreprocessingError("Cannot decode image from bytes.")
        return img

    raise PreprocessingError(f"Unsupported image source type: {type(source)}")


def _load_dicom(path: Path) -> np.ndarray:
    """Read pixel data from a DICOM file and convert to 8-bit grayscale."""
    try:
        import pydicom
    except ImportError:
        raise PreprocessingError("DICOM support requires pydicom.")

    try:
        ds = pydicom.dcmread(str(path))
        arr = ds.pixel_array.astype(np.float64)
    except Exception as exc:
        raise PreprocessingError(f"Cannot read DICOM pixel data: {exc}")

    # Normalise to 0–255 uint8
    arr = arr - arr.min()
    denom = arr.max()
    if denom > 0:
        arr = arr / denom
    arr = (arr * 255).astype(np.uint8)
    return arr


def _to_grayscale(img: np.ndarray) -> np.ndarray:
    """Ensure the image is single-channel grayscale."""
    if img.ndim == 3 and img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.ndim == 3 and img.shape[2] == 4:
        return cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
    return img


def _apply_clahe(gray: np.ndarray) -> np.ndarray:
    """Apply CLAHE contrast enhancement."""
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILE)
    return clahe.apply(gray)
