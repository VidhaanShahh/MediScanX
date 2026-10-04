import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from app.services.imaging.chexnet import CLASS_NAMES
from app.services.evaluation.metrics import calculate_auroc, calculate_macro_auroc

# Try importing the model loading logic
try:
    from app.services.imaging.chexnet import DenseNet121
    import torch
    import torchvision.transforms as transforms
    from torch.utils.data import DataLoader
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    
    class ChestXrayDataSet(torch.utils.data.Dataset):
        def __init__(self, data_dir, image_list_file, transform=None):
            import pandas as pd
            csv_path = os.path.abspath(os.path.join(data_dir, "../labels/Data_Entry_2017_v2020.csv"))
            df = pd.read_csv(csv_path)
            # Create a mapping from Image Index to a 14-dim binary label vector
            from app.services.imaging.chexnet import CLASS_NAMES
            
            label_map = {}
            for _, row in df.iterrows():
                findings = row["Finding Labels"].split("|")
                vec = [1 if c in findings else 0 for c in CLASS_NAMES]
                label_map[row["Image Index"]] = vec
                
            image_names = []
            labels = []
            with open(image_list_file, "r") as f:
                for line in f:
                    image_name = line.strip().split()[0]
                    if image_name in label_map:
                        image_names.append(os.path.join(data_dir, image_name))
                        labels.append(label_map[image_name])
            self.image_names = image_names
            self.labels = labels
            self.transform = transform
            
        def __getitem__(self, index):
            image = Image.open(self.image_names[index]).convert('RGB')
            label = self.labels[index]
            if self.transform is not None:
                image = self.transform(image)
            return image, torch.FloatTensor(label)
            
        def __len__(self):
            return len(self.image_names)
            
    MODEL_AVAILABLE = True
except ImportError as e:
    print(f"ImportError: {e}")
    MODEL_AVAILABLE = False
    
def evaluate_imaging(data_dir=None, model_path=None, test_list_path=None, output_dir="reports/evaluation"):
    if not MODEL_AVAILABLE:
        return {"status": "error", "message": "Failed to import imaging dependencies."}
        
    data_dir = data_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../data/ChestX-ray14/images"))
    model_path = model_path or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../models/imaging/model.pth.tar"))
    test_list_path = test_list_path or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../data/ChestX-ray14/labels/test_list.txt"))
    
    # 1. Determine local data availability
    available_images = set(os.listdir(data_dir))
    
    try:
        with open(test_list_path, 'r') as f:
            test_list_content = f.read().splitlines()
    except Exception as e:
        return {"status": "error", "message": f"Could not read test list: {str(e)}"}
        
    test_images_in_list = {line.split()[0] for line in test_list_content}
    available_test_images = available_images.intersection(test_images_in_list)
    
    # Is official test set available?
    is_official_test = False
    if len(available_test_images) == 0:
        # Fallback to train_val_list.txt for subset development
        train_val_path = test_list_path.replace("test_list.txt", "train_val_list.txt")
        try:
            with open(train_val_path, 'r') as f:
                train_val_content = f.read().splitlines()
            train_val_images = {line.split()[0] for line in train_val_content}
            available_dev_images = available_images.intersection(train_val_images)
            if len(available_dev_images) > 0:
                print(f"OFFICIAL TEST SET NOT LOCALLY AVAILABLE. Using {len(available_dev_images)} development images.")
                evaluation_list = [line for line in train_val_content if line.split()[0] in available_dev_images]
                split_name = "development_subset"
            else:
                return {"status": "error", "message": "No images available for evaluation."}
        except Exception as e:
            return {"status": "error", "message": f"Could not read train_val list: {str(e)}"}
    else:
        print(f"Using {len(available_test_images)} official test images.")
        evaluation_list = [line for line in test_list_content if line.split()[0] in available_test_images]
        split_name = "official_test"

    # Create temporary evaluation list file
    temp_list_path = "temp_eval_list.txt"
    with open(temp_list_path, "w") as f:
        f.write("\n".join(evaluation_list))

    try:
        # Load Model
        model = DenseNet121(len(CLASS_NAMES)).cpu()
        
        # Load weights, handling DataParallel prefix
        if os.path.isfile(model_path):
            checkpoint = torch.load(model_path, map_location='cpu')
            state_dict = checkpoint['state_dict']
            
            # Remove 'module.' prefix if present
            new_state_dict = {}
            for k, v in state_dict.items():
                name = k[7:] if k.startswith('module.') else k
                # Handle old DenseNet naming convention
                name = name.replace('norm.1', 'norm1').replace('norm.2', 'norm2')
                new_state_dict[name] = v
                
            model.load_state_dict(new_state_dict, strict=False)
        else:
            return {"status": "error", "message": f"Model not found at {model_path}"}
            
        model.eval()

        # Preprocessing matching M4 / M5
        normalize = transforms.Normalize([0.485, 0.456, 0.406],
                                         [0.229, 0.224, 0.225])
        
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            normalize
        ])
        
        # Custom dataset to match M5, but without TenCrop
        dataset = ChestXrayDataSet(data_dir=data_dir,
                                   image_list_file=temp_list_path,
                                   transform=transform)
                                   
        loader = DataLoader(dataset=dataset, batch_size=32, shuffle=False)

        gt = []
        pred = []
        
        with torch.no_grad():
            for inp, target in loader:
                gt.append(target.numpy())
                output = model(inp)
                pred.append(output.numpy())

        gt = np.concatenate(gt, axis=0)
        pred = np.concatenate(pred, axis=0)
        
        # Calculate AUROCs
        per_class_auroc = {}
        for i, class_name in enumerate(CLASS_NAMES):
            auroc = calculate_auroc(gt[:, i], pred[:, i])
            per_class_auroc[class_name] = auroc

        macro_auroc = calculate_macro_auroc(per_class_auroc)
        valid_classes = sum(1 for v in per_class_auroc.values() if v is not None)
        
        result = {
            "model": "DenseNet-121",
            "model_file": model_path,
            "dataset": "ChestX-ray14",
            "dataset_version": "v2020",
            "split": split_name,
            "evaluation_type": "imaging_classification",
            "sample_count": len(dataset),
            "valid_sample_count": len(dataset),
            "class_count": len(CLASS_NAMES),
            "valid_class_count": valid_classes,
            "per_class_auroc": per_class_auroc,
            "macro_auroc": macro_auroc,
            "timestamp": datetime.now().isoformat(),
            "preprocessing_description": "Resize to 224x224, ImageNet normalize (matching M4)",
            "target_macro_auroc": 0.80,
            "measured_macro_auroc": macro_auroc,
            "status": "success",
            "limitations": "Subset evaluation only." if split_name != "official_test" else "Evaluated on local subset."
        }
        
    finally:
        if os.path.exists(temp_list_path):
            os.remove(temp_list_path)
            
    # Save output
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "imaging_evaluation.json"), "w") as f:
        json.dump(result, f, indent=4)
        
    return result

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
    res = evaluate_imaging()
    print(json.dumps(res, indent=2))
