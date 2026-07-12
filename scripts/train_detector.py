import os
import shutil
import torch
import logging
from pathlib import Path
from ultralytics import YOLO

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting YOLOv8 OBB Fish Detector Re-training Script")
    
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    
    # Path to YAML and model config
    data_yaml = project_root / "ai-server" / "models" / "fish_obb_dataset" / "data.yaml"
    pretrained_model = project_root / "ai-server" / "yolov8n-obb.pt"
    
    if not data_yaml.exists():
        logger.error(f"Dataset config not found at {data_yaml}")
        return
        
    device = "0" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device} (CUDA available: {torch.cuda.is_available()})")
    
    # Initialize model
    model_source = str(pretrained_model) if pretrained_model.exists() else "yolov8n-obb.pt"
    logger.info(f"Loading model source: {model_source}")
    model = YOLO(model_source)
    
    # Train model for 1000 epochs
    logger.info("Training started (imgsz=640, epochs=1000, batch=16)")
    model.train(
        data=str(data_yaml),
        imgsz=640,
        epochs=1000,
        batch=16,
        device=device,
        patience=50,  # early stopping patience
        project=str(project_root / "runs" / "detect"),
        name="fish_obb_train",
        exist_ok=True,
    )
    
    logger.info("Training complete. Exporting best checkpoint to ONNX...")
    
    # Best model path
    best_pt_path = project_root / "runs" / "detect" / "fish_obb_train" / "weights" / "best.pt"
    if not best_pt_path.exists():
        logger.error(f"Could not find best.pt at {best_pt_path}")
        return
        
    # Load best trained model
    best_model = YOLO(str(best_pt_path))
    
    # Export to ONNX
    onnx_output_path = best_model.export(format="onnx", imgsz=640, dynamic=False)
    
    # Destination path
    dest_onnx_path = project_root / "ai-server" / "models" / "detector" / "fish_detector_v1.onnx"
    dest_onnx_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy exported ONNX file
    logger.info(f"Copying {onnx_output_path} to {dest_onnx_path}")
    shutil.copy2(onnx_output_path, dest_onnx_path)
    logger.info("Model training, export, and deployment successful!")

if __name__ == "__main__":
    main()
