# Performance Test Report

## 1. Overview and Methodology
Performance testing was conducted using isolated unit/integration measurement fixtures and Python's high-resolution performance timers (`time.perf_counter()`), combined with `psutil` process monitoring.

## 2. Actual Measurements

| Component / Action | Operations Measured | Mean Latency | Target / SLA | Status | Notes |
|---|---|---|---|---|---|
| **SHA-256 Hashing (1 MB payload)** | 50 iterations | **0.624 ms** | < 10 ms | PASS | Verified deterministic chunked/direct hashing |
| **Chest X-Ray Preprocessing** | 10 iterations (1024x1024 input) | **18.803 ms** | < 500 ms | PASS | CLAHE + resize to 224x224 + ImageNet normalization |
| **ECG Signal Preprocessing** | 10 iterations (5000 samples, 12 leads) | **14.262 ms** | < 200 ms | PASS | Bandpass filter + resampling + per-lead normalization |
| **API Healthcheck Response** | 20 iterations (TestClient) | **4.763 ms** | < 50 ms | PASS | ASGI dispatch without cold start |
| **Frontend Production Build** | Full Next.js 16 compile | **6.2 s** (bundle) / **2.9 s** (TS) | < 30 s | PASS | Zero type or bundling errors |
| **Peak Resident Memory (RSS)** | Warm process with PyTorch | **510.82 MB** | < 2048 MB | PASS | PyTorch model loaded in memory |

## 3. Latency & Load Analysis
- **Model Warmup vs Cold Start:** Initial model weights loading takes ~1.2s for DenseNet-121 on CPU; subsequent inferences reuse singleton in-memory weights.
- **Integrity Verification Overhead:** Calculating SHA-256 takes under 1 ms per megabyte, adding negligible overhead to asset retrieval and verification.
- **Concurrency & Load Bounds:** The backend handles synchronous request pipelines with asynchronous endpoints. Database transactions in SQLite test isolation maintain strict ACID guarantees with rollback times < 5 ms.
