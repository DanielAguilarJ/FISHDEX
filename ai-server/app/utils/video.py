"""
FishDex AI Server - Utilidades de Video
========================================
Funciones para procesar videos: extraer frames, validar formato, etc.

Orientación:
  Los videos grabados en móvil suelen contener metadata de rotación (90°/270°).
  OpenCV en algunas versiones aplica esa rotación automáticamente; en otras, no.
  Para evitar doble rotación:
    1. Se desactiva la auto-rotación de OpenCV (CAP_PROP_ORIENTATION_AUTO = 0).
    2. Se lee la rotación real con ffprobe.
    3. Se aplica manualmente con cv2.rotate().
  Si ffprobe no está disponible, rotation=0 (sin crash).
"""

import cv2
import json
import logging
import numpy as np
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Iterator, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DecodedVideoFrame:
    """One decoded frame with its index and timestamp within the source video."""
    frame_index: int
    timestamp_seconds: float
    frame: np.ndarray


def iter_frames_from_video(
    video_path: str,
    max_side: int = 960,
) -> Iterator[DecodedVideoFrame]:
    """
    Decodes every frame from a video sequentially from index 0 to EOF without skipping.

    Args:
        video_path: Path to the video file.
        max_side: Maximum pixels for longest side (default 960).

    Yields:
        DecodedVideoFrame for every frame in sequence.
    """
    rotation = _probe_video_rotation(video_path)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise ValueError(f"No se pudo abrir el video: {video_path}")

    try:
        try:
            cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
        except (AttributeError, cv2.error) as exc:
            # The constant is missing on older OpenCV builds; rotation is then
            # handled by _probe_video_rotation instead.
            logger.debug("CAP_PROP_ORIENTATION_AUTO unsupported: %s", exc)

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None or frame.size == 0:
                break

            rotated = _apply_video_rotation(frame, rotation)
            resized = _resize_preserve_aspect(rotated, max_side=max_side)
            ts = (frame_idx / fps) if fps > 0.0 else 0.0

            yield DecodedVideoFrame(
                frame_index=frame_idx,
                timestamp_seconds=ts,
                frame=resized,
            )
            frame_idx += 1
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Orientación
# ---------------------------------------------------------------------------

def _probe_video_rotation(video_path: str) -> int:
    """
    Lee la rotación del video usando ffprobe.
    Devuelve 0, 90, 180 o 270 (grados enteros).
    Retorna 0 sin lanzar excepción si ffprobe no está disponible.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream_tags=rotate:stream_side_data=rotation",
            "-of", "json",
            video_path,
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10)
        data = json.loads(output.decode("utf-8"))

        streams = data.get("streams") or []
        if not streams:
            return 0

        stream = streams[0]
        rotate = None

        # Intentar primero en tags (formato antiguo)
        tags = stream.get("tags") or {}
        if "rotate" in tags:
            rotate = tags["rotate"]

        # Luego en side_data (formato moderno MP4/MOV)
        if rotate is None:
            for side_data in stream.get("side_data_list") or []:
                if "rotation" in side_data:
                    rotate = side_data["rotation"]
                    break

        if rotate is None:
            return 0

        # ffprobe a veces devuelve rotaciones negativas (-90 = 270, etc.)
        return int(round(float(rotate))) % 360

    except FileNotFoundError:
        logger.debug("ffprobe not found — video rotation metadata will not be read")
        return 0
    except Exception as e:  # noqa: BLE001 — rotation metadata is optional
        logger.debug("ffprobe error reading rotation: %s", e)
        return 0


def _apply_video_rotation(frame: np.ndarray, rotation: int) -> np.ndarray:
    """
    Aplica la rotación de metadata al frame leído por OpenCV.
    Debe usarse solo cuando CAP_PROP_ORIENTATION_AUTO está desactivado.
    """
    rotation = rotation % 360
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def _resize_preserve_aspect(frame: np.ndarray, max_side: int = 960) -> np.ndarray:
    """
    Redimensiona el frame sin deformar ni forzar landscape.
    Escala por el lado mayor; si ya es <= max_side, no toca nada.
    """
    if max_side <= 0:
        return frame

    h, w = frame.shape[:2]
    longest = max(h, w)

    if longest <= max_side:
        return frame

    scale = max_side / float(longest)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------------------
# Extracción de frames
# ---------------------------------------------------------------------------

def extract_frames_from_video(
    video_path: str,
    max_frames: int = 10,
    max_side: int = 960,
) -> List[np.ndarray]:
    """
    Extrae frames de un video para el análisis de IA.

    Preserva la orientación real del video (portrait/landscape).
    NO fuerza ningún tamaño fijo — redimensiona manteniendo aspect ratio.

    Args:
        video_path: Ruta al archivo de video.
        max_frames:  Número máximo de frames a extraer (distribuidos uniformemente).
        max_side:    Tamaño máximo del lado más largo en píxeles (default 960).

    Returns:
        Lista de frames como arrays NumPy BGR, orientados correctamente.
    """
    frames = []

    # Leer rotación antes de abrir el cap para no perder el archivo si falla
    rotation = _probe_video_rotation(video_path)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise ValueError(f"No se pudo abrir el video: {video_path}")

    # Desactivar auto-rotación de OpenCV para evitar doble rotación.
    # La constante puede no existir en versiones antiguas → ignorar excepción.
    try:
        cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
    except (AttributeError, cv2.error) as exc:
        logger.debug("CAP_PROP_ORIENTATION_AUTO unsupported: %s", exc)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        logger.warning("Video has 0 frames: %s", video_path)
        return frames

    if total_frames <= max_frames:
        frame_indices = list(range(total_frames))
    else:
        frame_indices = np.linspace(0, total_frames - 1, max_frames, dtype=int).tolist()

    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()

        if not ret or frame is None:
            continue

        frame = _apply_video_rotation(frame, rotation)
        frame = _resize_preserve_aspect(frame, max_side=max_side)
        frames.append(frame)

    cap.release()

    logger.debug(
        "Extracted %d/%d frames from %s (rotation=%d°, max_side=%d)",
        len(frames), len(frame_indices), video_path, rotation, max_side,
    )
    return frames


# ---------------------------------------------------------------------------
# Selección de frames por nitidez
# ---------------------------------------------------------------------------

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

    sharpness_scores = []
    for frame in frames:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_scores.append(laplacian_var)

    best_idx = int(np.argmax(sharpness_scores))
    return frames[best_idx]


def select_best_n_frames(frames: List[np.ndarray], n: int = 5) -> List[np.ndarray]:
    """
    Selecciona N frames combinando nitidez y diversidad temporal.

    Divide el video en N segmentos uniformes y toma el frame MÁS NÍTIDO
    de cada segmento. Esto garantiza cobertura de todo el video (distintos
    ángulos y poses del pez), evitando N frames casi idénticos del mismo instante
    (problema típico cuando se seleccionan por nitidez pura).

    Args:
        frames: List of BGR frames as NumPy arrays.
        n:      Number of frames to return (default 5).

    Returns:
        List of N frames (one per temporal segment), each the sharpest in its segment.
    """
    if not frames:
        return []

    if len(frames) <= n:
        return list(frames)

    def _sharpness(f: np.ndarray) -> float:
        """
        Score a frame's sharpness by Laplacian variance.

        Args:
            f: BGR frame.

        Returns:
            Variance of the Laplacian; higher means sharper.
        """
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    total = len(frames)
    # Fronteras de N segmentos uniformes a lo largo del video
    bounds = np.linspace(0, total, n + 1, dtype=int)

    selected: List[np.ndarray] = []
    for i in range(n):
        start, end = int(bounds[i]), int(bounds[i + 1])
        if start >= end:
            continue
        segment = frames[start:end]
        best_in_segment = max(segment, key=_sharpness)
        selected.append(best_in_segment)

    return selected


# ---------------------------------------------------------------------------
# Utilidades de archivos temporales
# ---------------------------------------------------------------------------

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
    except OSError as exc:
        # Never fail the request because a temp file lingered, but do record it:
        # repeated failures mean the temp directory is filling up.
        logger.warning("Could not remove temp file %s: %s", file_path, exc)


def get_video_info(video_path: str) -> dict:
    """
    Obtiene información básica de un video.

    Returns:
        Dict con fps, total_frames, duration_seconds, width, height, rotation
    """
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        return {"error": "No se pudo abrir el video"}

    info = {
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "rotation": _probe_video_rotation(video_path),
    }
    info["duration_seconds"] = info["total_frames"] / info["fps"] if info["fps"] > 0 else 0

    cap.release()
    return info
