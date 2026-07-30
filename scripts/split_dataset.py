"""
FishDex - Split YOLOv8 OBB dataset into train/val
===================================================
Splits the Label Studio export into 80% train / 20% val.

Usage:
    python split_dataset.py

Input:  ai-server/model/project-115-at-2026-07-10-11-36-a28e1f28/
Output: ai-server/model/fish_obb_dataset/
            ├── data.yaml
            ├── train/images/ + train/labels/
            └── val/images/   + val/labels/
"""

import os
import random
import shutil
from pathlib import Path

# Config
SEED = 42
TRAIN_RATIO = 0.8

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
# Source dataset root. Was hardcoded to a Windows path, making the script
# unusable on any other machine. Override with FISHDEX_OBB_DATASET_DIR or --source.
SOURCE_DIR = Path(
    os.environ.get(
        "FISHDEX_OBB_DATASET_DIR",
        str(PROJECT_ROOT / "ai-server" / "models" / "fish_obb_source"),
    )
)
OUTPUT_DIR = PROJECT_ROOT / "ai-server" / "models" / "fish_obb_dataset"

def main():
    images_dir = SOURCE_DIR / "images"
    labels_dir = SOURCE_DIR / "labels"

    if not images_dir.exists():
        print(f"ERROR: Source images not found at {images_dir}")
        return

    # Get all image files
    image_files = sorted(list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpg")))
    print(f"Found {len(image_files)} images")

    # Shuffle with fixed seed for reproducibility
    random.seed(SEED)
    random.shuffle(image_files)

    # Split
    split_idx = int(len(image_files) * TRAIN_RATIO)
    train_images = image_files[:split_idx]
    val_images = image_files[split_idx:]

    print(f"Train: {len(train_images)} images")
    print(f"Val:   {len(val_images)} images")

    # Create output directories
    for split in ["train", "val"]:
        (OUTPUT_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    # Copy files
    for img_path in train_images:
        _copy_pair(img_path, labels_dir, OUTPUT_DIR / "train")

    for img_path in val_images:
        _copy_pair(img_path, labels_dir, OUTPUT_DIR / "val")

    # Create data.yaml
    data_yaml = OUTPUT_DIR / "data.yaml"
    data_yaml.write_text(
        f"# FishDex YOLOv8 OBB Dataset\n"
        f"path: {OUTPUT_DIR}\n"
        f"train: train/images\n"
        f"val: val/images\n"
        f"\n"
        f"# Classes\n"
        f"names:\n"
        f"  0: Fish\n"
    )

    print(f"\nDataset ready at: {OUTPUT_DIR}")
    print(f"data.yaml created at: {data_yaml}")
    print(f"\nTo train:")
    print(f"  yolo obb train model=yolov8n-obb.pt data={data_yaml} imgsz=640 epochs=100 batch=8")


def _copy_pair(img_path: Path, labels_dir: Path, dest_split: Path):
    """Copy an image and its matching label file to the destination split."""
    # Copy image
    shutil.copy2(img_path, dest_split / "images" / img_path.name)

    # Copy label (same name, .txt extension)
    label_name = img_path.stem + ".txt"
    label_path = labels_dir / label_name
    if label_path.exists():
        shutil.copy2(label_path, dest_split / "labels" / label_name)
    else:
        # Create empty label (no annotations for this image)
        (dest_split / "labels" / label_name).touch()


if __name__ == "__main__":
    main()
