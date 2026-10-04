# MediScanX — Project Specification

## Status

| Module | Description | Status |
|--------|-------------|--------|
| **M1** | User and Access Management (registration, login, JWT, RBAC) | ✅ **IMPLEMENTED** |
| **M2** | Patient and Case Management (CRUD, history, relationships) | ✅ **IMPLEMENTED** |
| **M3** | Upload and Validation (image/ECG validation, DICOM support, SHA-256) | ✅ **IMPLEMENTED** |
| **M4** | Preprocessing (image 224×224×3, ECG 12×1000, CLAHE, Butterworth) | ✅ **IMPLEMENTED** |
| **M5** | Imaging Analysis (DenseNet-121, 14-label classification) | ✅ **IMPLEMENTED** |
| **M6** | ECG Analysis (1D-CNN, 5 superclass classification, HR, 12-lead plot) | ✅ **IMPLEMENTED** |
| **M7** | Multimodal Fusion (decision-level weighted fusion) | ✅ **IMPLEMENTED** |
| **M8** | Explainability (Grad-CAM heatmaps, ECG saliency) | ✅ **IMPLEMENTED** |
| **M9** | Results and Reporting (PDF report generation) | ✅ **IMPLEMENTED** |
| **M10** | Administration and Audit (user management, model registry, audit logs) | ✅ **IMPLEMENTED** |

## Architecture

```
FastAPI (REST API)
    ↓
Service layer (business logic, validation)
    ↓
Preprocessing (image.py, ecg.py)
    ↓
[Future] ML inference → fusion → explainability
    ↓
PostgreSQL (SQLAlchemy ORM)
```

## Database Schema (10 tables)

- `users` — authentication, roles
- `patients` — anonymised ID, age, sex
- `cases` — linked to patient and user
- `imaging_studies` — uploaded chest images/DICOM
- `ecg_records` — uploaded ECG files
- `predictions` — model outputs per case
- `explanations` — Grad-CAM/saliency file refs
- `reports` — PDF reports with clinician remarks
- `model_versions` — model registry
- `audit_logs` — event tracking

## M1 Details

- POST `/api/auth/register` — bcrypt password hashing, role assignment
- POST `/api/auth/login` — JWT token (HS256, 60-minute expiry)
- Role-based access control (user / admin)
- Protected endpoints via OAuth2 bearer token dependency
- Password hashes never returned in any response

## M2 Details

- POST `/api/patients/` — anonymised patient creation (anon_code, age, sex)
- GET `/api/patients/`, GET `/api/patients/{id}` — retrieval
- POST `/api/cases` — case creation linked to patient
- GET `/api/cases`, GET `/api/cases/{id}` — list/filter/detail
- GET `/api/patients/{id}/cases` — case history
- DELETE `/api/cases/{id}` — cascade delete with file cleanup

## M3 Details

- Image: JPEG/PNG/DICOM, ≤20 MB, content-based validation (actual decode), dimension check (≥128px), SHA-256
- DICOM: pydicom parsing, sensitive tag removal (PatientName, ID, DOB, etc.)
- ECG: CSV (12 numeric columns) or WFDB (.hea/.dat), 12-lead validation, SHA-256
- No ML inference at upload time

## M4 Details

### Image Preprocessing (P3 Algorithm A2)
1. Load image or DICOM → 8-bit grayscale
2. Convert to grayscale if multi-channel
3. Optional CLAHE (clip=2.0, tiles=8×8)
4. Resize to 224×224
5. Low-contrast flag (std < 10)
6. Normalise to [0, 1], copy to 3 channels
7. ImageNet normalisation (mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
8. Output: float32 ndarray (224, 224, 3)

### ECG Preprocessing (P3 Algorithm A3)
1. Resample to 100 Hz
2. 4th-order Butterworth band-pass 0.5–40 Hz (scipy.signal.filtfilt)
3. Per-lead normalisation (zero mean, unit std)
4. Pad/trim to 10 seconds (1000 samples)
5. Flag flat/noisy leads
6. Output: float32 ndarray (12, 1000)

## M5 Details

### Imaging AI — CheXNet DenseNet-121 Inference
- Architecture: DenseNet-121 with 14-class sigmoid classifier
- Checkpoint: `models/imaging/model.pth.tar` (84 MB, epoch 14)
- Key compatibility: Handles old DenseNet key naming (`norm.1` → `norm1`) and DataParallel `module.` prefix stripping
- Inference: Single centre-crop on CPU (no TenCrop)
- Output: 14 sigmoid probabilities for ChestX-ray14 diseases:
  Atelectasis, Cardiomegaly, Effusion, Infiltration, Mass, Nodule, Pneumonia, Pneumothorax, Consolidation, Edema, Emphysema, Fibrosis, Pleural_Thickening, Hernia
- Singleton model loading: loaded once, reused for subsequent requests
- Preprocessing: Uses M4 image pipeline (224×224×3, ImageNet normalisation)
## M6 Details

### ECG AI — PTB-XL 1D-CNN Inference
- Architecture: 4-stage 1D-CNN with Conv1D, BatchNorm, MaxPooling, SpatialDropout, GlobalAveragePooling, Dense, and 5-class Sigmoid output
- Pretrained Asset: `models/ecg/ecg_model.keras` (Steenslid/ecg-ptbxl-classification, 8.4 MB)
- Normalisation: `models/ecg/normalisation_params.npz` (per-channel mean/std from training folds)
- Decision Thresholds: `models/ecg/thresholds.json` (NORM: 0.44, MI: 0.35, STTC: 0.33, CD: 0.26, HYP: 0.20)
- Superclasses (5): NORM, MI, STTC, CD, HYP
- Heart Rate Estimation: P3 Algorithm A6 using Lead II R-peak detection (5–15 Hz bandpass filter, scipy find_peaks, median RR-interval)
- 12-Lead Plot Rendering: SRS FR-6.2 generates base64-encoded PNG diagnostic plot of standard 12 leads
- Integration: `POST /api/cases/{case_id}/analyze` handles ECG analysis and multimodal dual analysis
- Persistence: Predictions persisted to `predictions` table with `source="ecg"`, `model_id`, timing, and threshold flags

## M7 Details

### Multimodal Fusion (Algorithm A7)
- Dual-modality weighted fusion based on validation AUROC.
- Image risk ($p_{img}$): Maximum of Cardiomegaly, Edema, and Effusion.
- ECG risk ($p_{ecg}$): $1 - P(NORM)$.
- Fusion Score ($S$): $(w_{img} \cdot p_{img} + w_{ecg} \cdot p_{ecg}) / (w_{img} + w_{ecg})$.
- Disagreement flag: Modalities disagree if absolute difference > 0.5.
- Risk bands: Low (<0.33), Moderate (<0.66), High (≥0.66).
- Weight configuration: Uses dynamically loaded measured test AUROC if available, otherwise falls back to provisional default SRS targets (0.80 imaging, 0.87 ECG). Tracks weight sources explicitly.
- Integration: `/api/cases/{case_id}/analyze` handles fusion on single and dual modality cases.
    # Persistence: Fusion results saved in `predictions` table (`source="fusion"`) transparently.

## M8 Details

### Explainability (Algorithm A8)
- **Grad-CAM (Imaging)**: Computes spatial attention maps from the actual M5 DenseNet-121 model by tracking gradients against `model.densenet121.features.denseblock4`. Normalised to [0, 1] and overlaid onto the original medical image with a JET colormap.
- **Saliency (ECG)**: Computes input-gradient sensitivity maps from the actual M6 1D-CNN model (`abs(d(target) / d(input))`). The target defaults to `risk = 1 - P(NORM)`. Visualised as a scattered overlay on the 12-lead diagnostic plot.
- **Integration**: Computed on-the-fly during `/api/cases/{case_id}/analyze` without mutating prediction behaviour. Does NOT fabricate explanations if generation fails.
- **Persistence**: Rendered visualizations are persisted to the server's file system, and their paths are stored in the `explanations` database table, linked to the respective base `predictions`.

## M9 Details

### Results and Reporting
- PDF generation using `reportlab`.
- Generates a multimodal clinical-style report from case metadata, imaging, ECG predictions, and fusion.
- Embedded Grad-CAM and saliency visualisations alongside the source imagery.
- Saved persistently on the filesystem with the path logged in the `reports` table.

## M10 Details

### Administration and Audit
- Protected endpoint `GET /api/admin/audit-logs` accessible only by users with role `admin`.
- Tracks API events including:
  - User registration (`register`)
  - User login (`login`)
  - Patient creation (`create_patient`)
  - Case creation (`create_case`)
  - File uploads (`upload_file`)
  - Analysis initiation and completion (`analyze_started`, `analyze_completed`)
  - Report generation (`generate_report`)
- Returns paginated and sortable logs reflecting genuine system interactions without mocking or hallucination.

## Model Evaluation

### Evaluation Methodology
- **M5 (Imaging)**: Evaluated locally on a development subset of 500 images due to official test set unavailability locally. Passes through standard M4 imaging pipeline to obtain continuous probabilities for all 14 classes, then computes AUROC per-class and Macro AUROC.
- **M6 (ECG)**: Evaluated locally on a subset of records distributed across folds (since fold-10 is not completely present). Passes through standard M4 ECG preprocessing and the model to generate continuous predictions. Computes AUROC per-superclass and Macro AUROC.

### Distinction Between Targets and Measurements
The SRS specifies **target** performances:
- **Imaging Target AUROC**: 0.80
- **ECG Target Macro AUROC**: 0.87
These represent aspirational performance targets. They are strictly separate from **measured** AUROC on the evaluation subset.

### Multimodal Weighting
M7 Multimodal Fusion supports AUROC-based weighting. Appropriate measured AUROC can be used when available.
Because the current local evaluation values are strictly subset measurements and are not official test performance, they are NOT injected into M7. Therefore, the current M7 weights remain the provisional SRS targets unless appropriate validation/test AUROCs are available.
The weight source is explicitly tracked (e.g. `source = "provisional_srs_target"` or `source = "measured_test_auroc"`).

### Limitations
- **Local Datasets**: The evaluations run on very small subsets compared to official test sets. Imaging is evaluated on a development subset of `train_val_list.txt`. ECG is evaluated on a cross-fold subset. Because of this, the evaluation numbers do not represent generalizable true test performance and serve only as a pipeline validation framework.

## What Is NOT Implemented

- No frontend
- All M1 to M10 backend modules are fully implemented
