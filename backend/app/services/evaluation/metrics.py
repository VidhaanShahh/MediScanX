import json
from pathlib import Path
from sklearn.metrics import roc_auc_score
import numpy as np

def calculate_auroc(y_true, y_score):
    """
    Calculate AUROC for a single class.
    Returns float or None if mathematically invalid (e.g. only one class).
    """
    y_true = np.array(y_true)
    y_score = np.array(y_score)
    if len(np.unique(y_true)) < 2:
        return None
    try:
        return float(roc_auc_score(y_true, y_score))
    except ValueError:
        return None

def calculate_macro_auroc(class_aurocs):
    """
    Calculate macro AUROC given a dict or list of AUROCs.
    Ignores None values.
    """
    valid_aurocs = [val for val in class_aurocs.values() if val is not None] if isinstance(class_aurocs, dict) else [val for val in class_aurocs if val is not None]
    if not valid_aurocs:
        return None
    return float(np.mean(valid_aurocs))

def load_evaluation_results(reports_dir: str = "reports/evaluation"):
    """
    Load evaluation results to use for M7 weight configuration.
    """
    reports_path = Path(reports_dir)
    results = {}
    
    # Load imaging results
    imaging_file = reports_path / "imaging_evaluation.json"
    if imaging_file.exists():
        try:
            with open(imaging_file, "r") as f:
                data = json.load(f)
                if data.get("status") == "success" and data.get("macro_auroc") is not None:
                    split = data.get("split", "unknown")
                    if split == "test" or split == "official_test":
                        results["imaging_measured_test_auroc"] = data.get("macro_auroc")
                    elif split == "validation":
                        results["imaging_measured_validation_auroc"] = data.get("macro_auroc")
                    else:
                        results[f"imaging_{split}_auroc"] = data.get("macro_auroc")
        except Exception:
            pass

    # Load ecg results
    ecg_file = reports_path / "ecg_evaluation.json"
    if ecg_file.exists():
        try:
            with open(ecg_file, "r") as f:
                data = json.load(f)
                if data.get("status") == "success" and data.get("macro_auroc") is not None:
                    split = data.get("split", "unknown")
                    if split == "test" or split == "official_test":
                        results["ecg_measured_test_auroc"] = data.get("macro_auroc")
                    elif split == "validation":
                        results["ecg_measured_validation_auroc"] = data.get("macro_auroc")
                    else:
                        results[f"ecg_{split}_auroc"] = data.get("macro_auroc")
        except Exception:
            pass

    return results
