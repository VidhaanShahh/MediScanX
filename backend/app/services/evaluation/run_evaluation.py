import os
import json
from datetime import datetime

def run_all_evaluations():
    print("Starting MediScanX Model Evaluation...")
    
    from app.services.evaluation.imaging_evaluation import evaluate_imaging
    from app.services.evaluation.ecg_evaluation import evaluate_ecg
    from app.services.evaluation.metrics import load_evaluation_results
    
    reports_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../reports/evaluation"))
    os.makedirs(reports_dir, exist_ok=True)
    
    print("\n--- Running M5 (Imaging) Evaluation ---")
    imaging_res = evaluate_imaging(output_dir=reports_dir)
    print(f"Imaging evaluation completed. Macro AUROC: {imaging_res.get('macro_auroc', 'N/A')}")
    
    print("\n--- Running M6 (ECG) Evaluation ---")
    ecg_res = evaluate_ecg(output_dir=reports_dir)
    print(f"ECG evaluation completed. Macro AUROC: {ecg_res.get('macro_auroc', 'N/A')}")
    
    print("\n--- Generating Summary ---")
    summary = {
        "timestamp": datetime.now().isoformat(),
        "imaging_evaluation": imaging_res,
        "ecg_evaluation": ecg_res,
        "m7_provisional_weights": {
            "image_weight": 0.80,
            "ecg_weight": 0.87
        }
    }
    
    # Load what M7 would actually use
    m7_weights = load_evaluation_results(reports_dir=reports_dir)
    summary["m7_configured_weights"] = m7_weights
    
    with open(os.path.join(reports_dir, "evaluation_summary.json"), "w") as f:
        json.dump(summary, f, indent=4)
        
    print("Evaluation full pipeline complete. Results stored in reports/evaluation/")
    
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../backend")))
    run_all_evaluations()
