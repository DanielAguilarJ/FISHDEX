import os
import sys
from pathlib import Path
import sqlite3
import numpy as np
import cv2
import shutil

# Add ai-server to python path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.append(str(PROJECT_ROOT / "ai-server"))

from app.database import get_db_connection
from app.utils.video import get_video_info
from app.utils.crop_utils import pad_image_to_aspect
from app.config import settings

def main():
    conn = get_db_connection()
    cursor = conn.conn.cursor() if hasattr(get_db_connection(), "conn") else conn.cursor()
    
    # Directory for the reconstructed raw training dataset
    data_raw_dir = SCRIPT_DIR / "data" / "raw"
    if data_raw_dir.exists():
        shutil.rmtree(data_raw_dir)
    data_raw_dir.mkdir(parents=True, exist_ok=True)
    
    cursor.execute("""
        SELECT id, species_slug, result_fish_id, catch_number, area_code, artifact_dir 
        FROM identification_jobs 
        WHERE status = 'completed'
    """)
    jobs = cursor.fetchall()
    print(f"Encontrados {len(jobs)} trabajos completados.")
    
    total_processed = 0
    
    for job in jobs:
        job_id = job["id"]
        species_slug = job["species_slug"]
        fish_id = job["result_fish_id"]
        artifact_dir = job["artifact_dir"]
        
        if not species_slug or not fish_id or not artifact_dir:
            continue
            
        # Determine original aspect ratio of the video
        video_path = PROJECT_ROOT / "ai-server" / "data" / "storage" / "raw_videos" / f"{job_id}_raw.mp4"
        if not video_path.exists():
            video_path = PROJECT_ROOT / "ai-server" / "data" / "storage" / "raw_videos" / f"{job_id}_raw.temp"
        if not video_path.exists():
            video_path = PROJECT_ROOT / "ai-server" / "data" / artifact_dir / "raw" / "raw_capture.temp"
            
        target_aspect = 720.0 / 1280.0 # Default vertical
        if video_path.exists():
            try:
                info = get_video_info(str(video_path))
                if info and info.get("width") and info.get("height"):
                    target_aspect = float(info["width"]) / float(info["height"])
            except Exception as e:
                print(f"  Error reading video info for {job_id}: {e}")
                
        print(f"Job {job_id} ({species_slug}) aspect={target_aspect:.4f}")
        
        catch_dir = PROJECT_ROOT / "ai-server" / "data" / "storage" / artifact_dir
        
        # Locate all crop files in the catch directory
        images_dir = catch_dir / "images"
        images_bbox_dir = catch_dir / "images_bbox"
        dataset_dir = catch_dir / "dataset"
        
        images_dir.mkdir(parents=True, exist_ok=True)
        images_bbox_dir.mkdir(parents=True, exist_ok=True)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        
        crop_files = []
        for p in catch_dir.rglob("crop_*.jpg"):
            if "images_bbox" in str(p) or "bbox" in p.name:
                continue
            crop_files.append(p)
            
        crop_files = list(set(crop_files))
        print(f"  Encontrados {len(crop_files)} recortes a re-procesar.")
        
        species_raw_dir = data_raw_dir / species_slug
        species_raw_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, crop_path in enumerate(crop_files):
            img = cv2.imread(str(crop_path))
            if img is None or img.size == 0:
                continue
                
            # Pad the crop to target aspect ratio
            padded = pad_image_to_aspect(img, target_aspect=target_aspect)
            if padded is None:
                continue
                
            rel_name = crop_path.name
            
            # Save to dataset/
            dataset_crop_path = dataset_dir / rel_name
            cv2.imwrite(str(dataset_crop_path), padded)
            
            # Save to images/
            images_crop_path = images_dir / rel_name
            cv2.imwrite(str(images_crop_path), padded)
            
            # Save preview.jpg (copy of first padded crop)
            if idx == 0:
                cv2.imwrite(str(catch_dir / "preview.jpg"), padded)
                
            # Keep original unpadded (OBB) version as bbox for compatibility
            bbox_name = rel_name.replace(".jpg", "_bbox.jpg")
            cv2.imwrite(str(dataset_dir / bbox_name), img)
            cv2.imwrite(str(images_bbox_dir / rel_name), img)
            
            # Copy padded crop to training directory
            raw_filename = f"{job_id}_{idx:03d}_{rel_name}"
            cv2.imwrite(str(species_raw_dir / raw_filename), padded)
            
            total_processed += 1
            
    conn.close()
    print(f"\nRe-procesamiento completado. Total de imágenes preparadas para entrenamiento: {total_processed}")
    
    # Resumen del dataset de entrenamiento raw reconstruido
    print("\nResumen del dataset de entrenamiento raw reconstruido:")
    for class_dir in sorted(data_raw_dir.iterdir()):
        if class_dir.is_dir():
            count = len(list(class_dir.glob("*.jpg")))
            print(f"  {class_dir.name}: {count} imágenes")

if __name__ == '__main__':
    main()
