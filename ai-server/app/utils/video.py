"""
FishDex AI Server - Utilidades de Video
========================================
Funciones para procesar videos: extraer frames, validar formato, etc.
"""

import cv2
import numpy as np
import tempfile
import os
from typing import List, Tuple
from pathlib import Path


def extract_frames_from_video(
    video_path: str,
    max_frames: int = 10,
    target_size: Tuple[int, int] = (640, 480)
) -> List[np.ndarray]:
    """
    Extrae frames de un video para el análisis de IA.
    
    Args:
        video_path: Ruta al archivo de video
        max_frames: Número máximo de frames a extraer
        target_size: Tamaño objetivo (ancho, alto) para cada frame
    
    Returns:
        Lista de frames como arrays NumPy (BGR)
    """
    frames = []
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        raise ValueError(f"No se pudo abrir el video: {video_path}")
    
    # Obtener info del video
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    duration = total_frames / fps if fps > 0 else 0
    
    # Calcular intervalo entre frames para distribuir uniformemente
    if total_frames <= max_frames:
        frame_indices = list(range(total_frames))
    else:
        frame_indices = np.linspace(0, total_frames - 1, max_frames, dtype=int).tolist()
    
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        
        if ret:
            # Redimensionar al tamaño objetivo
            frame_resized = cv2.resize(frame, target_size)
            frames.append(frame_resized)
    
    cap.release()
    return frames


def select_best_frame(frames: List[np.ndarray]) -> np.ndarray:
    """
    Selecciona el mejor frame de una lista basándose en nitidez (Laplacian variance).
    
    El frame más nítido generalmente es el que tiene al pez mejor enfocado.
    
    Args:
        frames: Lista de frames como arrays NumPy
    
    Returns:
        El frame con mayor nitidez
    """
    if not frames:
        raise ValueError("No hay frames disponibles")
    
    if len(frames) == 1:
        return frames[0]
    
    # Calcular la varianza del Laplaciano para cada frame (medida de nitidez)
    sharpness_scores = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_scores.append(laplacian_var)
    
    # Retornar el frame más nítido
    best_idx = int(np.argmax(sharpness_scores))
    return frames[best_idx]


def select_best_n_frames(frames: List[np.ndarray], n: int = 5) -> List[np.ndarray]:
    """
    Select the top-N sharpest frames from a list, ranked by Laplacian variance.

    Args:
        frames: List of BGR frames as NumPy arrays.
        n:      Number of frames to return (default 5).

    Returns:
        List of the N sharpest frames (or all frames if fewer than N available).
    """
    if not frames:
        return []

    if len(frames) <= n:
        return list(frames)

    # Score every frame by Laplacian variance
    scored: List[Tuple[float, int]] = []
    for i, frame in enumerate(frames):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        scored.append((score, i))

    # Sort descending by score, pick top N
    scored.sort(reverse=True)
    top_indices = sorted(idx for _, idx in scored[:n])  # keep temporal order
    return [frames[i] for i in top_indices]


def save_temp_video(video_bytes: bytes, suffix: str = ".mp4") -> str:
    """
    Guarda bytes de video en un archivo temporal.
    
    Args:
        video_bytes: Contenido del video en bytes
        suffix: Extensión del archivo
    
    Returns:
        Ruta al archivo temporal
    """
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(video_bytes)
    temp_file.close()
    return temp_file.name


def cleanup_temp_file(file_path: str):
    """Elimina un archivo temporal si existe."""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
    except Exception:
        pass  # No fallar si no se puede eliminar


def get_video_info(video_path: str) -> dict:
    """
    Obtiene información básica de un video.
    
    Returns:
        Dict con fps, total_frames, duration_seconds, width, height
    """
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        return {"error": "No se pudo abrir el video"}
    
    info = {
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    info["duration_seconds"] = info["total_frames"] / info["fps"] if info["fps"] > 0 else 0
    
    cap.release()
    return info
