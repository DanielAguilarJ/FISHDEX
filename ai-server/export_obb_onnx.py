import os
import shutil
from ultralytics import YOLO

def main():
    best_pt = r"c:\Users\Student\Documents\GitHub\FISHDEX\ai-server\runs\obb\fish_obb-2\weights\best.pt"
    if not os.path.exists(best_pt):
        # Fallback to fish_obb
        best_pt = r"c:\Users\Student\Documents\GitHub\FISHDEX\ai-server\runs\obb\fish_obb\weights\best.pt"
        
    print(f"Loading weights from {best_pt}...")
    model = YOLO(best_pt)
    
    print("Exporting to ONNX...")
    # Export the model
    onnx_path = model.export(format="onnx")
    print(f"Exported to: {onnx_path}")
    
    # Destination path
    dest_path = r"c:\Users\Student\Documents\GitHub\FISHDEX\ai-server\models\detector\fish_detector_v1.onnx"
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    shutil.copy(onnx_path, dest_path)
    print(f"Successfully copied to {dest_path}")

if __name__ == "__main__":
    main()
