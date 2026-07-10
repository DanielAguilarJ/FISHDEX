# YOLOv8 OBB Model Training Guide

Training an Oriented Bounding Box (OBB) fish detector for FishDex.

---

## 1. Dataset Format

Label Studio exports OBB annotations in the following format (one `.txt` file per image):

```
class_id x1 y1 x2 y2 x3 y3 x4 y4
```

Each line contains **9 values**:
- `class_id` - integer class index (0 = Fish)
- `x1 y1 x2 y2 x3 y3 x4 y4` - four corners of the oriented bounding box, **normalized** to [0, 1] relative to image width/height

Corner order: top-left, top-right, bottom-right, bottom-left (clockwise from top-left of the rotated box).

Example label file (`frame_001.txt`):
```
0 0.4531 0.3125 0.7812 0.2891 0.7969 0.5547 0.4688 0.5781
0 0.1250 0.6000 0.3100 0.5800 0.3200 0.7200 0.1350 0.7400
```

This file has 2 fish detections, both class 0, each with 4 normalized corner points.

---

## 2. Dataset Structure

Required folder layout:

```
datasets/fish_obb/
├── data.yaml
├── train/
│   ├── images/
│   │   ├── frame_001.jpg
│   │   ├── frame_002.jpg
│   │   └── ...
│   └── labels/
│       ├── frame_001.txt
│       ├── frame_002.txt
│       └── ...
└── val/
    ├── images/
    │   ├── frame_081.jpg
    │   ├── frame_082.jpg
    │   └── ...
    └── labels/
        ├── frame_081.txt
        ├── frame_082.txt
        └── ...
```

Rules:
- Each image must have a corresponding `.txt` label file with the same name
- Images without any objects should have an empty `.txt` file
- Supported image formats: `.jpg`, `.jpeg`, `.png`, `.bmp`

---

## 3. data.yaml

Create `datasets/fish_obb/data.yaml` with the following content:

```yaml
path: C:/FishDex/datasets/fish_obb
train: train/images
val: val/images

names:
  0: Fish
```

Notes:
- `path` must be an absolute path to the dataset root
- `train` and `val` are relative to `path`
- For single-class detection, we only need class `0: Fish`
- On Linux/macOS adjust the path accordingly (e.g. `/home/user/datasets/fish_obb`)

---

## 4. Splitting Dataset

Python script to split 100 labeled images into 80% train / 20% val:

```python
"""
split_dataset.py
Splits images and labels into train/val sets (80/20).
Run from the directory containing your raw images/ and labels/ folders.
"""

import os
import shutil
import random
from pathlib import Path

# Configuration
SOURCE_IMAGES = Path("images")
SOURCE_LABELS = Path("labels")
OUTPUT_DIR = Path("datasets/fish_obb")
TRAIN_RATIO = 0.8
SEED = 42

def split_dataset():
    random.seed(SEED)

    # Get all image files
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
    all_images = [
        f for f in SOURCE_IMAGES.iterdir()
        if f.suffix.lower() in image_extensions
    ]

    print(f"Found {len(all_images)} images")

    # Shuffle and split
    random.shuffle(all_images)
    split_idx = int(len(all_images) * TRAIN_RATIO)
    train_images = all_images[:split_idx]
    val_images = all_images[split_idx:]

    print(f"Train: {len(train_images)}, Val: {len(val_images)}")

    # Create output directories
    for split in ["train", "val"]:
        (OUTPUT_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    # Copy files
    def copy_files(image_list, split_name):
        for img_path in image_list:
            # Copy image
            dst_img = OUTPUT_DIR / split_name / "images" / img_path.name
            shutil.copy2(img_path, dst_img)

            # Copy corresponding label
            label_name = img_path.stem + ".txt"
            src_label = SOURCE_LABELS / label_name
            dst_label = OUTPUT_DIR / split_name / "labels" / label_name

            if src_label.exists():
                shutil.copy2(src_label, dst_label)
            else:
                # Create empty label file (no objects in image)
                dst_label.touch()

    copy_files(train_images, "train")
    copy_files(val_images, "val")

    print(f"Dataset split complete at: {OUTPUT_DIR}")
    print(f"  Train: {len(train_images)} images")
    print(f"  Val:   {len(val_images)} images")

if __name__ == "__main__":
    split_dataset()
```

Usage:
```bash
python split_dataset.py
```

---

## 5. Training Command

Install ultralytics and start training:

```bash
pip install ultralytics
```

```bash
yolo obb train model=yolov8n-obb.pt data=C:/FishDex/datasets/fish_obb/data.yaml imgsz=640 epochs=100 batch=8
```

Key parameters:
- `model=yolov8n-obb.pt` - Start from pretrained nano OBB model
- `imgsz=640` - Input image size (640x640)
- `epochs=100` - Training epochs (increase for better results)
- `batch=8` - Batch size (reduce if GPU OOM, increase if GPU has headroom)

Additional useful parameters:
```bash
yolo obb train \
  model=yolov8n-obb.pt \
  data=C:/FishDex/datasets/fish_obb/data.yaml \
  imgsz=640 \
  epochs=100 \
  batch=8 \
  patience=20 \
  lr0=0.01 \
  augment=True \
  mosaic=1.0 \
  flipud=0.5 \
  fliplr=0.5 \
  degrees=15.0 \
  project=runs/obb \
  name=fish_detector
```

Training output will be saved to `runs/obb/fish_detector/` with:
- `weights/best.pt` - Best model checkpoint
- `weights/last.pt` - Last epoch checkpoint
- `results.csv` - Training metrics
- Validation plots and confusion matrix

---

## 6. Export to ONNX

Export the best model to ONNX format for deployment:

```bash
yolo export model=runs/obb/train/weights/best.pt format=onnx imgsz=640
```

This produces `runs/obb/train/weights/best.onnx`.

For optimized inference, add simplification:
```bash
yolo export model=runs/obb/train/weights/best.pt format=onnx imgsz=640 simplify=True opset=17
```

Optional: export with dynamic batch size for server flexibility:
```bash
yolo export model=runs/obb/train/weights/best.pt format=onnx imgsz=640 simplify=True dynamic=True
```

---

## 7. Deployment

Copy the exported ONNX model to the AI server:

```bash
cp runs/obb/train/weights/best.onnx ai-server/models/detector/fish_detector_v1.onnx
```

Directory structure on AI server:
```
ai-server/
├── models/
│   ├── detector/
│   │   └── fish_detector_v1.onnx      ← OBB detector
│   ├── classifier/
│   │   └── fish_classifier_v1.onnx    ← Species classifier (future)
│   └── embedder/
│       └── fish_embedder_v1.onnx      ← Re-ID embeddings (future)
├── src/
├── main.py
└── ...
```

Update the environment variable:
```bash
FISHDEX_MODEL_DETECTOR=models/detector/fish_detector_v1.onnx
```

---

## 8. OBB Output Format

The ONNX OBB model outputs detections in the following format per detection:

```
[cx, cy, w, h, angle, conf, class_id]
```

| Field | Description |
|-------|-------------|
| `cx` | Center x (normalized 0-1 or pixels depending on export) |
| `cy` | Center y |
| `w` | Width of the oriented box |
| `h` | Height of the oriented box |
| `angle` | Rotation angle in **radians** (range: -pi/4 to 3pi/4) |
| `conf` | Confidence score 0.0-1.0 |
| `class_id` | Class index (0 = Fish) |

### Converting to 4 Corners

To convert `(cx, cy, w, h, angle)` to 4 corner points, apply a rotation matrix:

```python
import numpy as np

def obb_to_corners(cx, cy, w, h, angle):
    """Convert OBB parameters to 4 corner points."""
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)

    # Half dimensions
    hw = w / 2
    hh = h / 2

    # Corner offsets (before rotation)
    corners = np.array([
        [-hw, -hh],
        [ hw, -hh],
        [ hw,  hh],
        [-hw,  hh],
    ])

    # Rotation matrix
    rotation = np.array([
        [cos_a, -sin_a],
        [sin_a,  cos_a],
    ])

    # Rotate and translate
    rotated = corners @ rotation.T
    rotated[:, 0] += cx
    rotated[:, 1] += cy

    return rotated  # shape: (4, 2)
```

### Cropping the OBB Region

```python
import cv2

def crop_obb(image, corners):
    """Crop the oriented bounding box region from the image."""
    # Get the minimal upright bounding rect
    rect = cv2.minAreaRect(corners.astype(np.float32))
    width = int(rect[1][0])
    height = int(rect[1][1])

    # Perspective transform to straighten
    src_pts = corners.astype(np.float32)
    dst_pts = np.array([
        [0, 0],
        [width, 0],
        [width, height],
        [0, height],
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    cropped = cv2.warpPerspective(image, matrix, (width, height))

    return cropped
```

---

## 9. Verification

Quick script to test inference on a sample image:

```python
"""
verify_model.py
Test OBB model inference on a single image.
"""

import cv2
import numpy as np
import onnxruntime as ort

# Configuration
MODEL_PATH = "ai-server/models/detector/fish_detector_v1.onnx"
IMAGE_PATH = "test_samples/underwater_001.jpg"
CONFIDENCE_THRESHOLD = 0.5
INPUT_SIZE = 640


def preprocess(image_path):
    """Load and preprocess image for ONNX inference."""
    img = cv2.imread(image_path)
    h, w = img.shape[:2]

    # Resize with letterboxing
    scale = INPUT_SIZE / max(h, w)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h))

    # Pad to square
    canvas = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
    pad_x = (INPUT_SIZE - new_w) // 2
    pad_y = (INPUT_SIZE - new_h) // 2
    canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized

    # Normalize and transpose (HWC → CHW)
    blob = canvas.astype(np.float32) / 255.0
    blob = blob.transpose(2, 0, 1)
    blob = np.expand_dims(blob, axis=0)

    return blob, img, scale, pad_x, pad_y


def postprocess(outputs, scale, pad_x, pad_y, conf_threshold):
    """Parse OBB detections from model output."""
    # Output shape depends on ultralytics export version
    # Typically: (1, num_detections, 7) → [cx, cy, w, h, angle, conf, class]
    predictions = outputs[0]

    if predictions.ndim == 3:
        predictions = predictions[0]

    detections = []
    for pred in predictions:
        conf = pred[4] if len(pred) == 7 else pred[5]
        if conf < conf_threshold:
            continue

        cx, cy, w, h, angle = pred[0], pred[1], pred[2], pred[3], pred[4]

        # Remove padding and rescale to original image coords
        cx = (cx - pad_x) / scale
        cy = (cy - pad_y) / scale
        w = w / scale
        h = h / scale

        detections.append({
            "cx": float(cx),
            "cy": float(cy),
            "w": float(w),
            "h": float(h),
            "angle": float(angle),
            "confidence": float(conf),
            "class_id": int(pred[-1]) if len(pred) == 7 else 0,
        })

    return detections


def draw_detections(image, detections):
    """Draw OBB boxes on the image."""
    for det in detections:
        corners = obb_to_corners(det["cx"], det["cy"], det["w"], det["h"], det["angle"])
        corners_int = corners.astype(np.int32)

        cv2.polylines(image, [corners_int], True, (0, 255, 0), 2)
        label = f"Fish {det['confidence']:.2f}"
        cv2.putText(image, label, tuple(corners_int[0]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    return image


def obb_to_corners(cx, cy, w, h, angle):
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    hw, hh = w / 2, h / 2
    corners = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]])
    rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    rotated = corners @ rotation.T
    rotated[:, 0] += cx
    rotated[:, 1] += cy
    return rotated


def main():
    print(f"Loading model: {MODEL_PATH}")
    session = ort.InferenceSession(MODEL_PATH)

    input_name = session.get_inputs()[0].name
    print(f"Input name: {input_name}")
    print(f"Input shape: {session.get_inputs()[0].shape}")

    print(f"\nProcessing: {IMAGE_PATH}")
    blob, original_img, scale, pad_x, pad_y = preprocess(IMAGE_PATH)

    # Run inference
    outputs = session.run(None, {input_name: blob})
    print(f"Output shapes: {[o.shape for o in outputs]}")

    # Parse detections
    detections = postprocess(outputs, scale, pad_x, pad_y, CONFIDENCE_THRESHOLD)
    print(f"\nFound {len(detections)} fish detection(s):")

    for i, det in enumerate(detections):
        print(f"  [{i}] confidence={det['confidence']:.3f} "
              f"center=({det['cx']:.1f}, {det['cy']:.1f}) "
              f"size=({det['w']:.1f}x{det['h']:.1f}) "
              f"angle={np.degrees(det['angle']):.1f}deg")

    # Save visualization
    result_img = draw_detections(original_img.copy(), detections)
    output_path = "test_samples/detection_result.jpg"
    cv2.imwrite(output_path, result_img)
    print(f"\nVisualization saved to: {output_path}")


if __name__ == "__main__":
    main()
```

Run:
```bash
pip install onnxruntime opencv-python numpy
python verify_model.py
```

---

## 10. Notes

### Model Selection

| Model | Size | Speed (GPU) | Accuracy | Use Case |
|-------|------|-------------|----------|----------|
| `yolov8n-obb` | 6 MB | ~2ms | Good | Development, mobile, quick iteration |
| `yolov8s-obb` | 23 MB | ~4ms | Better | Production with sufficient data |
| `yolov8m-obb` | 52 MB | ~8ms | Best | Research, high-accuracy requirements |

### Data Requirements

- **100 images** - Minimum viable for initial detector (expect ~70% mAP)
- **300 images** - Reasonable accuracy for controlled environments (~80% mAP)
- **500+ images** - Production quality (~85%+ mAP)
- **1000+ images** - Robust across varied conditions (~90%+ mAP)

### Tips

- Start with `yolov8n-obb` (nano) for speed during development
- Upgrade to `yolov8s-obb` (small) when you have 300+ labeled images
- Use diverse training data: different water clarity, lighting, angles, fish sizes
- Include negative examples (frames with no fish) — just use empty label files
- Monitor validation mAP50 during training; stop if it plateaus for 20+ epochs
- Re-export to ONNX after every significant training run
- Version your models: `fish_detector_v1.onnx`, `fish_detector_v2.onnx`, etc.
- Test on real underwater footage, not just cropped fish images

### Common Issues

| Problem | Solution |
|---------|----------|
| Low confidence scores | More training data, longer training, lower conf threshold |
| False positives on rocks/plants | Add hard negatives to training set |
| Misses small fish | Use higher `imgsz` (960 or 1280) |
| Slow inference | Use nano model, reduce input size, enable GPU |
| ONNX export fails | Update ultralytics: `pip install -U ultralytics` |
| Label format errors | Verify 9 values per line, all normalized 0-1 |
