import os
from pathlib import Path
import os
import shutil
import random
import yaml
from ultralytics import YOLO

def main():
    # Was hardcoded to a Windows path. Override with FISHDEX_OBB_DATASET_DIR.
    dataset_dir = os.environ.get(
        "FISHDEX_OBB_DATASET_DIR",
        str(Path(__file__).resolve().parent / "models" / "fish_obb_source"),
    )
    images_dir = os.path.join(dataset_dir, "images")
    labels_dir = os.path.join(dataset_dir, "labels")

    # Create train/val structure
    train_images = os.path.join(dataset_dir, "train", "images")
    train_labels = os.path.join(dataset_dir, "train", "labels")
    val_images = os.path.join(dataset_dir, "val", "images")
    val_labels = os.path.join(dataset_dir, "val", "labels")

    for d in [train_images, train_labels, val_images, val_labels]:
        os.makedirs(d, exist_ok=True)

    # List all images
    all_images = [f for f in os.listdir(images_dir) if f.endswith(('.png', '.jpg', '.jpeg'))]
    print(f"Found {len(all_images)} total images in {images_dir}")

    # If not split yet (if train_images is empty)
    if not os.listdir(train_images):
        print("Splitting dataset into train/val...")
        random.seed(42)
        random.shuffle(all_images)
        split_idx = int(len(all_images) * 0.8)
        train_files = all_images[:split_idx]
        val_files = all_images[split_idx:]
        
        for files, img_dst, lbl_dst in [(train_files, train_images, train_labels), (val_files, val_images, val_labels)]:
            for f in files:
                img_src = os.path.join(images_dir, f)
                lbl_name = os.path.splitext(f)[0] + '.txt'
                lbl_src = os.path.join(labels_dir, lbl_name)
                
                shutil.copy(img_src, os.path.join(img_dst, f))
                if os.path.exists(lbl_src):
                    shutil.copy(lbl_src, os.path.join(lbl_dst, lbl_name))
                else:
                    print(f"Warning: No label for {f}")
    else:
        print("Dataset already split.")

    # Create data.yaml
    data_yaml_path = os.path.join(dataset_dir, "data.yaml")
    data_yaml = {
        'path': dataset_dir,
        'train': 'train/images',
        'val': 'val/images',
        'nc': 1,
        'names': ['Fish']
    }

    with open(data_yaml_path, 'w') as f:
        yaml.dump(data_yaml, f)

    print(f"Dataset prepared at {dataset_dir}")
    print("Starting YOLO OBB training...")

    # Start from pretrained YOLOv8 OBB
    base_model_path = os.path.join(os.path.dirname(__file__), "yolov8n-obb.pt")
    if not os.path.exists(base_model_path):
        # Fallback to download
        base_model_path = "yolov8n-obb.pt"
    
    model = YOLO(base_model_path)
    
    # Train
    results = model.train(
        data=data_yaml_path,
        epochs=100,  # 100 epochs for proper training
        imgsz=640,
        device=0,    # Use GPU
        batch=16,    # Default batch size or 8 if memory is tight, let's try 16
        project=os.path.join(os.path.dirname(__file__), "runs", "obb"),
        name="fish_obb"
    )

    # Copy the best model to the deployment path
    best_model_path = os.path.join(os.path.dirname(__file__), "runs", "obb", "fish_obb", "weights", "best.pt")
    deploy_path = os.path.join(os.path.dirname(__file__), "models", "yolov8n-obb.pt")
    fallback_deploy_path = os.path.join(os.path.dirname(__file__), "yolov8n-obb.pt")
    
    if os.path.exists(best_model_path):
        os.makedirs(os.path.dirname(deploy_path), exist_ok=True)
        shutil.copy(best_model_path, deploy_path)
        shutil.copy(best_model_path, fallback_deploy_path)
        print(f"Training completed. Model deployed to {deploy_path} and {fallback_deploy_path}")
    else:
        print("Error: best.pt not found after training!")

if __name__ == "__main__":
    main()
