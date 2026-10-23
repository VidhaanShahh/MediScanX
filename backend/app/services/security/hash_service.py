"""
MediScanX — Cryptographic Hashing and File Integrity Service.

Provides:
- Standard SHA-256 calculation for in-memory bytes and on-disk files.
- Chunked hashing for memory-efficient processing of large medical datasets.
- Verification function that recalculates digests from authoritative disk files
  and compares against recorded cryptographic hashes.
- Educational demonstration helpers comparing hashing vs. encryption,
  avalanche effect, and deterministic consistency.
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional


def compute_bytes_sha256(data: bytes) -> str:
    """
    Calculate the SHA-256 hex digest of raw byte content.
    Returns 64-character lowercase hexadecimal string.
    """
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(file_path: str | Path, chunk_size: int = 65536) -> str:
    """
    Calculate the SHA-256 hex digest of a file on disk using streaming chunks.
    Prevents loading entire multi-megabyte DICOM/CXR/ECG/PDF files into memory.

    Parameters:
    -----------
    file_path : str | Path
        Path to target file on disk.
    chunk_size : int
        Buffer size in bytes (default 64KB).

    Returns:
    --------
    64-character lowercase hexadecimal SHA-256 digest string.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_file_integrity(file_path: str | Path, recorded_hash: Optional[str]) -> Dict[str, Any]:
    """
    Verify the cryptographic integrity of a file against its stored reference digest.

    Parameters:
    -----------
    file_path : str | Path
        Target file path on disk.
    recorded_hash : Optional[str]
        Expected SHA-256 hex digest recorded in the authoritative database.

    Returns:
    --------
    Dict containing:
        - is_valid: bool (True only if file exists, is readable, and digest matches exactly)
        - file_exists: bool
        - recorded_hash: Optional[str]
        - calculated_hash: Optional[str]
        - status: str ("VERIFIED", "CORRUPTED_OR_MODIFIED", "FILE_MISSING", "NO_RECORDED_HASH", "ERROR")
        - message: str
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "is_valid": False,
            "file_exists": False,
            "recorded_hash": recorded_hash,
            "calculated_hash": None,
            "status": "FILE_MISSING",
            "message": f"Target file does not exist on disk at {path.name}.",
        }

    if not recorded_hash:
        # Calculate current hash for transparency, but indicate no baseline exists
        try:
            curr_hash = compute_file_sha256(path)
        except Exception as exc:
            return {
                "is_valid": False,
                "file_exists": True,
                "recorded_hash": None,
                "calculated_hash": None,
                "status": "ERROR",
                "message": f"Unable to read file: {str(exc)}",
            }

        return {
            "is_valid": False,
            "file_exists": True,
            "recorded_hash": None,
            "calculated_hash": curr_hash,
            "status": "NO_RECORDED_HASH",
            "message": "File is present on disk, but no trusted reference hash was stored at ingestion.",
        }

    try:
        current_hash = compute_file_sha256(path)
    except Exception as exc:
        return {
            "is_valid": False,
            "file_exists": True,
            "recorded_hash": recorded_hash,
            "calculated_hash": None,
            "status": "ERROR",
            "message": f"File read error during verification: {str(exc)}",
        }

    is_match = (current_hash.lower() == recorded_hash.lower())
    status = "VERIFIED" if is_match else "CORRUPTED_OR_MODIFIED"
    message = (
        "File integrity verified: current SHA-256 digest matches stored database record exactly."
        if is_match
        else "Integrity alert: calculated digest differs from recorded reference. File content has been modified or corrupted."
    )

    return {
        "is_valid": is_match,
        "file_exists": True,
        "recorded_hash": recorded_hash,
        "calculated_hash": current_hash,
        "status": status,
        "message": message,
    }


def demonstrate_cryptographic_hashing(sample_text: str = "MediScanX Patient Chest X-Ray Study") -> Dict[str, Any]:
    """
    Educational demonstration of cryptographic hashing principles:
    1. Determinism: identical input always produces identical 256-bit digest.
    2. Avalanche Effect: a single bit alteration completely changes the output digest.
    3. Fixed Output Length: input of arbitrary size always hashes to exactly 64 hex characters (256 bits).
    4. One-Way Property: hash cannot be reversed to plaintext (contrast with two-way encryption).
    """
    raw_bytes = sample_text.encode("utf-8")
    hash_1 = compute_bytes_sha256(raw_bytes)
    hash_1_repeat = compute_bytes_sha256(raw_bytes)

    # Slight modification (e.g. changing one character at the end)
    modified_text = sample_text + "."
    hash_modified = compute_bytes_sha256(modified_text.encode("utf-8"))

    # Count differing hex characters
    diff_chars = sum(1 for a, b in zip(hash_1, hash_modified) if a != b)

    return {
        "algorithm": "SHA-256 (FIPS 180-4 / NIST Secure Hash Standard)",
        "digest_bit_length": 256,
        "digest_hex_length": 64,
        "sample_input": sample_text,
        "primary_digest": hash_1,
        "deterministic_verification": {
            "repeated_digest": hash_1_repeat,
            "is_identical": (hash_1 == hash_1_repeat),
            "concept": "Determinism: The same message always yields the exact same hash digest.",
        },
        "avalanche_effect_demonstration": {
            "modified_input": modified_text,
            "modified_digest": hash_modified,
            "differing_hex_characters": diff_chars,
            "differing_ratio": round(diff_chars / 64.0, 4),
            "concept": "Avalanche Effect: A minor 1-character modification causes ~50%+ pseudo-random divergence across all digest bits.",
        },
        "hashing_vs_encryption_comparison": {
            "type": "Cryptographic Hash Function (One-Way Trapdoor)",
            "reversible": False,
            "requires_key": False,
            "purpose": "Data Integrity, Tamper Detection, Digital Fingerprinting",
            "contrast_with_encryption": (
                "Encryption (e.g. AES, RSA) is a two-way transform intended for confidentiality and requires a secret/private key to decrypt. "
                "Hashing (SHA-256) is mathematically irreversible and maps arbitrary-length data to a fixed 256-bit digest without keys."
            ),
            "security_boundary_limitation": (
                "A hash stored beside a file in the same database cannot prevent an attacker with full database and disk write access "
                "from modifying both the file and the stored hash simultaneously. For complete non-repudiation, digital signatures "
                "(asymmetric private keys) or write-once append-only audit ledgers are required."
            ),
        },
    }
