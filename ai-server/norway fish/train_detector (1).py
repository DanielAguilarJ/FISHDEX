"""
Fish Fin Damage Analysis - YOLOv8 Detector Training Script

Trains a YOLOv8 model to detect fish fins in images.
Optimized for CPU-only execution.

Author: Fish Analysis Team
Date: 2025-07-03
CPU Optimized: Yes
"""

import os
import logging
from ultralytics import YOLO
import torch
from pathlib import Path
import yaml
import psutil 
import gc

import csv
from datetime import datetime

MEMORY_LOG_PATH = "memory_log.csv"

# Initialize CSV file with headers (only if it doesn't exist)
if not os.path.exists(MEMORY_LOG_PATH):
    with open(MEMORY_LOG_PATH, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "label", "rss_MB"])

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# memory log 
def log_memory_usage(tag=""):
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss / 1024 ** 2  # In MB
    timestamp = datetime.now().isoformat(timespec='seconds')

    # Log to console
    logger.info(f"🧠 [Memory] {tag} - RSS Memory: {mem:.2f} MB")

    # Log to CSV
    with open(MEMORY_LOG_PATH, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, tag, f"{mem:.2f}"])



# --- CONFIGURATION ---
# Dataset configuration
DATASET_CONFIG = "detector_dataset/data.yaml"

# Model configuration
MODEL_SIZE = "yolov8n.pt"  # Options: yolov8n.pt (nano), yolov8s.pt (small), yolov8m.pt (medium)
IMAGE_SIZE = 512
PATIENCE = 20  # Early stopping patience

# TEMPORAL: Forzar CPU para desarrollo local
FORCE_CPU = True  # Cambiar a False para usar GPU cuando esté disponible

if FORCE_CPU:
    # Configuración forzada para CPU
    EPOCHS = 50  # Reducido para pruebas rápidas en CPU
    BATCH_SIZE = 8  # Batch muy pequeño para CPU
    WORKERS = 0     # Sin workers en CPU
    DEVICE = 'mps'  # Forzar CPU
else:
    # Configuración automática (GPU/CPU)
    EPOCHS = 50
    BATCH_SIZE = 8  # Reduced for CPU training
    WORKERS = 8 if torch.cuda.is_available() else 2  # More workers for GPU
    DEVICE = 'auto'  # Auto-detect best available device (cuda/mps/cpu)
SAVE_PERIOD = 10  # Save checkpoint every N epochs

# Output directory
OUTPUT_DIR = "runs/detect"
MODEL_SAVE_DIR = "models"

# --- END CONFIGURATION ---

def validate_dataset_config() -> bool:
    """Validate that the dataset configuration exists and is properly formatted."""
    if not os.path.exists(DATASET_CONFIG):
        logger.error(f"❌ Dataset config not found: {DATASET_CONFIG}")
        logger.info("Please run 'python prepare_data.py' first to create the dataset")
        return False
    
    try:
        with open(DATASET_CONFIG, 'r') as f:
            config = yaml.safe_load(f)
        
        required_keys = ['path', 'train', 'val', 'nc', 'names']
        for key in required_keys:
            if key not in config:
                logger.error(f"❌ Missing required key in dataset config: {key}")
                return False
        
        # Check if dataset directories exist
        dataset_path = config['path']
        train_path = os.path.join(dataset_path, config['train'])
        val_path = os.path.join(dataset_path, config['val'])
        
        if not os.path.exists(train_path):
            logger.error(f"❌ Training images directory not found: {train_path}")
            return False
        
        if not os.path.exists(val_path):
            logger.error(f"❌ Validation images directory not found: {val_path}")
            return False
        
        # Count images
        train_images = len([f for f in os.listdir(train_path) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        val_images = len([f for f in os.listdir(val_path) 
                        if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        
        if train_images == 0:
            logger.error("❌ No training images found")
            return False
        
        logger.info(f"✅ Dataset validation passed:")
        logger.info(f"   Training images: {train_images}")
        logger.info(f"   Validation images: {val_images}")
        logger.info(f"   Classes: {config['nc']} ({', '.join(config['names'].values())})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error validating dataset config: {e}")
        return False

def setup_training_environment() -> None:
    """Setup the training environment and directories."""
    # Create model save directory
    os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
    
    # Auto-detect device and configure accordingly
    import torch
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
        logger.info("✅ Training environment configured for GPU")
        logger.info(f"   GPU: {device_name}")
        logger.info(f"   GPU Memory: {gpu_memory:.1f} GB")
        logger.info(f"   CUDA Version: {torch.version.cuda}")
        torch.backends.cudnn.benchmark = True  # Optimize for GPU
    else:
        torch.set_num_threads(4)  # Limit threads for CPU training
        logger.info("✅ Training environment configured for CPU")
        logger.info(f"   PyTorch version: {torch.__version__}")
        logger.info(f"   CPU threads: {torch.get_num_threads()}")
    
    logger.info(f"   Device: {DEVICE}")

def create_training_config() -> dict:
    """Create training configuration dictionary."""
    
    
    return {
        'data': DATASET_CONFIG,
        #'cache' : False,
        'imgsz': IMAGE_SIZE,
        'batch': BATCH_SIZE,
        'device': DEVICE,
        'workers': WORKERS,
        'patience': PATIENCE,
        'save_period': SAVE_PERIOD,
        'project': OUTPUT_DIR,
        'name': 'train',
        'exist_ok': True,
        'pretrained': True,
        'optimizer': 'SGD',
        'lr0': 0.01,
        'momentum': 0.937,
        'weight_decay': 0.0005,
        'warmup_epochs': 3,
        'warmup_momentum': 0.8,
        'warmup_bias_lr': 0.1,
        'box': 7.5,
        'cls': 0.5,
        'dfl': 1.5,
        'pose': 12.0,
        'kobj': 1.0,
        'label_smoothing': 0.0,
        'nbs': 64,
        'hsv_h': 0.015,
        'hsv_s': 0.7,
        'hsv_v': 0.4,
        'degrees': 0.0,
        'translate': 0.1,
        'scale': 0.5,
        'shear': 0.0,
        'perspective': 0.0,
        'flipud': 0.0,
        'fliplr': 0.5,
        'mosaic': 1.0,
        'mixup': 0.0,
        'copy_paste': 0.0
    }

def train_detector() -> str:
    """
    Train the YOLOv8 detector model.
    
    Returns:
        Path to the best trained model
    """
    logger.info("🎯 Starting YOLOv8 Fin Detector Training")
    logger.info("="*50)
    
    try:
        
        log_memory_usage("Before model loading")
        
        # Load pre-trained YOLOv8 model
        logger.info(f"📥 Loading pre-trained model: {MODEL_SIZE}")
        model = YOLO(MODEL_SIZE)

        log_memory_usage("After model loading")
        
        # Get training configuration
        train_config = create_training_config()

        
        logger.info("🚀 Training configuration:")
        for key, value in train_config.items():
            logger.info(f"   {key}: {value}")
        
        logger.info("\n🏃‍♂️ Starting training process...")
        logger.info("This may take a while on CPU. Consider using a smaller model or fewer epochs for faster training.")

        gc.collect()
        log_memory_usage("Before training (post-GC)")
        
        # Start training
        save_dir = None

        for epoch in range(EPOCHS):
            logger.info(f"Epoch {epoch + 1}/{EPOCHS} starting...")

            # Reload the model only after the first epoch
            if epoch > 0 and save_dir:
                last_model_path = os.path.join(save_dir, "weights", "last.pt")
                if os.path.exists(last_model_path):
                    model = YOLO(last_model_path)
                else:
                    logger.warning(f"⚠️ Cannot resume: Checkpoint not found at {last_model_path}. Starting fresh...")

         # Train for 1 epoch (resume=False always since we handle it manually)
            results = model.train(
                **train_config,
                epochs=1,
                resume=False
            )

            save_dir = results.save_dir  # Store path to find the "last.pt" next time

            # Log memory usage after epoch
            log_memory_usage(f"After Epoch {epoch + 1}")


        gc.collect()
        log_memory_usage("After training (post-GC)")
        
        # Get paths to trained models
        best_model_path = results.save_dir / "weights" / "best.pt"
        last_model_path = results.save_dir / "weights" / "last.pt"
        
        # Copy best model to models directory
        import shutil
        final_model_path = os.path.join(MODEL_SAVE_DIR, "fin_detector_best.pt")
        shutil.copy2(str(best_model_path), final_model_path)
        
        logger.info("✅ Training completed successfully!")
        logger.info(f"📊 Training results saved to: {results.save_dir}")
        logger.info(f"🏆 Best model saved to: {final_model_path}")
        logger.info(f"📈 Last model saved to: {last_model_path}")
        
        # Print training summary
        if hasattr(results, 'results_dict'):
            logger.info("\n📈 Training Summary:")
            logger.info(f"   Final mAP50: {results.results_dict.get('metrics/mAP50(B)', 'N/A')}")
            logger.info(f"   Final mAP50-95: {results.results_dict.get('metrics/mAP50-95(B)', 'N/A')}")
        
        return final_model_path
        
    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        raise

def test_trained_model(model_path: str) -> None:
    """Test the trained model on validation data."""
    logger.info("\n🔍 Testing trained model...")
    
    try:
        
        log_memory_usage("Before loading trained model")

        # Load trained model
        model = YOLO(model_path)

        log_memory_usage("After loading trained model")
        
        # Run validation
        logger.info("Running validation on test set...")
        results = model.val(data=DATASET_CONFIG, device=DEVICE)

        gc.collect()
        log_memory_usage("After validation (post-GC)")
        
        logger.info("✅ Model validation completed")
        logger.info(f"📊 Validation results:")
        if hasattr(results, 'results_dict'):
            for metric, value in results.results_dict.items():
                if 'mAP' in metric:
                    logger.info(f"   {metric}: {value:.4f}")
        
    except Exception as e:
        logger.error(f"❌ Model testing failed: {e}")

def create_inference_example() -> None:
    """Create a simple inference example script."""
    example_code = '''"""
Simple inference example for the trained YOLOv8 fin detector.
"""

from ultralytics import YOLO
import cv2

# Load the trained model
model = YOLO("models/fin_detector_best.pt")

# Run inference on an image
results = model("path/to/your/image.jpg")

# Display results
for result in results:
    # Save annotated image
    result.save("detected_fins.jpg")
    print("Results saved to detected_fins.jpg")
    
    # Print detections
    for box in result.boxes:
        class_id = int(box.cls[0])
        confidence = float(box.conf[0])
        coordinates = box.xyxy[0].tolist()
        print(f"Detected: Class {class_id}, Confidence: {confidence:.2f}, Box: {coordinates}")
'''
    
    with open("detector_inference_example.py", "w") as f:
        f.write(example_code)
    
    logger.info("✅ Created detector_inference_example.py")

def main():
    """Main training pipeline."""
    logger.info("🐟 Fish Fin Detector Training Pipeline")
    logger.info("="*60)
    
    # Step 1: Validate dataset
    if not validate_dataset_config():
        return
    
    # Step 2: Setup training environment
    setup_training_environment()
    
    # Step 3: Train the model
    try:
        model_path = train_detector()
    except Exception as e:
        logger.error(f"❌ Training pipeline failed: {e}")
        return
    
    # Step 4: Test the trained model
    test_trained_model(model_path)
    
    # Step 5: Create inference example
    create_inference_example()
    
    logger.info("\n🎉 Detector training pipeline completed!")
    logger.info("🚀 Next steps:")
    logger.info("   1. Review training results in the 'runs/detect/train' directory")
    logger.info("   2. Run 'python train_classifier.py' to train the damage classifier")
    logger.info("   3. Use 'python run_inference.py' for complete fin detection and damage analysis")
    logger.info(f"   4. Or try the simple example: 'python detector_inference_example.py'")

if __name__ == '__main__':
    main()
