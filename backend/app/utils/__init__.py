"""
MediScanX — Utility helpers.

Shared helper functions used across services.
"""

import hashlib


def sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()
