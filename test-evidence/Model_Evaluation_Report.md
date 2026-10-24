# Model Evaluation Report

## 1. Scope & Academic Prototype Disclaimer
> **IMPORTANT NOTICE:** MediScanX is an academic prototype developed for research and educational purposes. Successful execution of computational tests and pipeline validations does **NOT** establish clinical safety or diagnostic efficacy. It is not an FDA/CE-cleared medical device and must never substitute for licensed clinical judgment.

## 2. Checkpoints & Architectures
- **Modality 1 (Imaging - Chest X-Ray):**
  - **Architecture:** DenseNet-121 (CheXNet-derived architecture)
  - **Checkpoint Path:** `models/imaging/model.pth.tar`
  - **Number of Disease Classes:** 14 thoracic disease categories (Atelectasis, Cardiomegaly, Effusion, Infiltration, Mass, Nodule, Pneumonia, Pneumothorax, Consolidation, Edema, Emphysema, Fibrosis, Pleural Thickening, Hernia)
  - **Activation:** 14-output Sigmoid for multilabel classification
  - **Input Contract:** 3-channel normalized tensor `[1, 3, 224, 224]` with ImageNet mean and std.

- **Modality 2 (Electrophysiology - ECG):**
  - **Architecture:** PTB-XL 1D-CNN (4-stage Conv1D with SpatialDropout and GlobalAveragePooling)
  - **Checkpoint Path:** `models/ecg/ecg_model.keras`
  - **Number of Diagnostic Superclasses:** 5 classes (NORM, MI, STTC, CD, HYP)
  - **Activation:** Sigmoid output for multi-label diagnostic classification
  - **Input Contract:** 12-lead time-series signal `[1, 1000, 12]` resampled to 100 Hz.

## 3. Evaluation Metrics on Available Subsets & In-Depth Discrepancy Analysis

### Imaging Pipeline Evaluation (Development Subset, 500 images)
*Note: Due to the unavailability of the full held-out NIH ChestX-ray14 test split on the local development workstation, metrics reflect pipeline validation on the accessible development sample.*
- **Macro AUROC (subset):** **0.457 – 0.493** (Provisional subset measurement)
- **Official Test Set Performance:** **NOT ESTABLISHED** on local workstation.
- **Root-Cause Analysis of Imaging Subset AUROC (~0.46 - 0.49):**
  1. **Extreme Class Imbalance:** In the 500-image development sample, positive cases for rare diseases are critically sparse:
     - `Hernia`: exactly **1 positive sample** out of 500 (per-class AUROC drops to ~0.008 due to ranking sensitivity with a single positive).
     - `Edema`: 4 positive samples.
     - `Pneumonia`: 5 positive samples.
     - `No Finding`: 236 images (47.2% of the subset).
     ROC-AUC metrics become erratic and uninformative when positive support is < 10 samples.
  2. **Single Center-Crop vs TenCrop Inference:** The original Stanford CheXNet publication benchmarked official AUC using 10-crop evaluation (averaging 4 corner crops, 1 center crop, and their horizontal flips). The MediScanX deployment pipeline employs a single 224x224 center crop to ensure low-latency inference on CPU.
  3. **Development vs. Unseen Split:** The 500 samples were drawn from `train_val_list.txt` because the official `test_list.txt` NIH image archives are not present locally.

### ECG Pipeline Evaluation (Cross-fold Subset, 100 records)
*Note: Evaluated across 100 available records from PTB-XL.*
- **Per-class AUROC:**
  - NORM: 0.956
  - MI: 0.939
  - STTC: 0.940
  - CD: 0.944
  - HYP: 0.976
- **Macro AUROC (subset):** **0.951**
- **Official Held-Out Test AUROC:** **NOT ESTABLISHED** (PTB-XL fold-10 full held-out evaluation was not locally present). High performance on 100 samples confirms that the 1D-CNN pipeline correctly executes preprocessing, convolution, and diagnostic classification, but cannot be generalized as clinical proof.

## 4. Cross-Modal Fusion & Explainability Review
- **Decision Fusion Rule (M7):** When both imaging and ECG are available, the fusion service evaluates concordance/discordance. In accordance with safety design, internal subset AUROCs are NOT ingested as production weights; calibrated fallback weights are applied.
- **Explainability (Grad-CAM & Saliency):**
  - DenseNet-121 Grad-CAM heatmaps generate overlays highlighting regions of high gradient activation. Visual inspection confirms spatial alignment with the input lung fields, but does not prove clinical localization validity.
  - ECG 1D Saliency correctly identifies temporal regions of interest across the 12 leads without numerical errors.

## 5. Identified Limitations
1. **Absence of Full Held-Out Sets:** Evaluation tests on patient-level split separation (`ME-001`), comprehensive per-class confusion matrices on unseen data (`ME-002`), and controlled perturbation robustness (`ME-003`, `ME-004`) cannot be marked as PASS without full multi-gigabyte held-out datasets.
2. **Clinical Interpretation:** High AUROC values on small subsets must not be interpreted as generalizable diagnostic performance.
