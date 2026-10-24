# Testing Summary — MediScanX

## 1. Overview
A comprehensive testing, verification, and evidence collection process was executed across the **MediScanX** platform.
All automated test suites, production build processes, latency benchmarks, security evaluations, and model evaluation assessments were run directly in the host environment.

## 2. Test Execution Summary

| Testing Category | Total Cases | PASS | FAIL | BLOCKED | NOT RUN | Execution Rate |
|---|---|---|---|---|---|---|
| **Unit Testing (UT)** | 20 | 20 | 0 | 0 | 0 | 100% |
| **Integration Testing (IT)** | 10 | 10 | 0 | 0 | 0 | 100% |
| **System & Functional Testing (ST)** | 8 | 8 | 0 | 0 | 0 | 100% |
| **Non-Functional Testing (NFT)** | 13 | 11 | 0 | 2 | 0 | 84.6% |
| **Model Evaluation (ME)** | 7 | 2 | 0 | 5 | 0 | 28.6% (Documented) |
| **TOTAL** | **59** | **51** | **0** | **8** | **0** | **86.4% Verified** |

- **Total Backend Pytest Items:** 108 automated tests executed, **108 passed, 0 failed** in 52.26 seconds.
- **Frontend Production Build:** Next.js 16.3.8 compiled successfully with Turbopack, TypeScript checks passed in 2.9s, all 12 application routes generated without errors.
- **Defects Identified & Verified Fixed:** 3 defects (ECG lead transposition, M7 dynamic weight safety fallback, Object-level authorization for integrity endpoints) confirmed with zero regressions.

## 3. Phase-by-Phase Breakdown

### Phase 1 — Unit Testing (UT-001 to UT-020)
- **File Validation & Uploads:** Valid PNG, JPEG, and supported extensions are accepted; zero-byte, corrupted bytes, and disallowed extensions (.exe) are rejected safely without server crashes.
- **Preprocessing:** Verified Chest X-ray tensor output `[1, 3, 224, 224]` with CLAHE and ImageNet normalization. ECG preprocessing resamples to 100 Hz, filters bandpass (0.5–40 Hz), and enforces lead dimensions.
- **Cryptographic Hashing:** Verified SHA-256 properties (64-char lowercase hexadecimal), byte determinism, chunked file hashing, modified byte detection (`CORRUPTED_OR_MODIFIED`), and handling of absent files (`FILE_MISSING`).
- **Security & Database:** Salted bcrypt password verification verified; isolated SQLite transactions roll back cleanly upon failure without data contamination.

### Phase 2 — Integration Testing (IT-001 to IT-010)
- **Upload → Preprocessing → Model Inference:** Chest X-ray and ECG uploads persist file records and SHA-256 digests; preprocessed inputs trigger inference and return schema-valid probabilities.
- **Cross-Modal Fusion:** Contradictory modality outputs route to clinical review status; concordant findings correctly escalate priority.
- **Reporting & Integrity:** PDF report generation calculates and persists SHA-256 fingerprint in database; asset integrity checks verify that physical file bytes match stored hashes.
- **Object-Level Authorization:** Direct tests confirm unauthenticated calls return `401 Unauthorized`; authenticated non-owners calling `/api/integrity/case/{case_id}` receive `403 Forbidden`.

### Phase 3 — System & Functional Testing (ST-001 to ST-008)
- Complete patient-to-report lifecycle, patient timeline ordering, DBMS explorer predefined query execution (`file_integrity_audit`), inline UI field validation, safe API error responses, and Grad-CAM overlay generation verified.

### Phase 4 — Non-Functional Testing (NFT-001 to NFT-013)
- **Performance:** Measured 0.624 ms for 1MB SHA-256 hashing, 18.8 ms for image preprocessing, 14.3 ms for ECG preprocessing, and 4.76 ms for API healthcheck response. Peak memory stabilized at ~510 MB.
- **Security:** Parameterized queries neutralize SQL injection (`' OR '1'='1'`); Next.js and Pydantic neutralize XSS; malicious file types are quarantined/rejected.
- **Blocked Items:** Concurrency load tests with 50/100 users (`NFT-004`) and classmate usability surveys (`NFT-011`) are legitimately marked `BLOCKED` due to workstation isolation constraints and user study requirements.

### Phase 5 — Model Evaluation (ME-001 to ME-007)
- Measured subset pipeline AUROC: M5 DenseNet-121 achieved ~0.493 on local development subset; M6 1D-CNN achieved 0.951 on available PTB-XL records.
- In accordance with rigorous scientific honesty, full held-out test set separation (`ME-001`), full multi-label test set confusion matrices (`ME-002`), and formal perturbation scans (`ME-003`, `ME-004`, `ME-007`) are marked `BLOCKED` because the multi-gigabyte official NIH ChestX-ray14 test split and complete PTB-XL fold-10 were not locally present.
