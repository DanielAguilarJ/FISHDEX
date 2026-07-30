"""
FishDex AI Server - Fish Crop Service
=======================================
Integrates the ONNX fin_detector_best.onnx model for fish body detection and cropping.
Falls back to center-crop if ONNX runtime is unavailable or detection fails.
"""

import threading
import numpy as np
import cv2
from pathlib import Path
from typing import Optional


class FishCropService:
    """Service for cropping fish from video frames using ONNX detection model."""

    def __init__(self):
        """Initialize the ONNX model for fish detection."""
        model_path = Path(__file__).parent.parent.parent / "norway fish" / "fin_detector_best.onnx"
        try:
            import onnxruntime as ort
            self.session = ort.InferenceSession(str(model_path))
            self.available = True
        except Exception:
            self.available = False

    def crop_fish(self, frame: np.ndarray) -> np.ndarray:
        """
        Run ONNX detection to find bounding box of fish body and crop it.

        If detection fails or model is unavailable, returns center 70% crop of original frame.

        Args:
            frame: BGR frame (H, W, 3) as numpy array.

        Returns:
            Cropped BGR frame containing only the fish.
        """
        if not self.available:
            return self._center_crop(frame)
        try:
            h, w = frame.shape[:2]
            # Preprocess: resize to 640x640, normalize to 0-1, add batch dim, channels first
            resized = cv2.resize(frame, (640, 640))
            blob = resized.astype(np.float32) / 255.0
            blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]

            # Run inference
            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: blob})

            # Parse YOLO output: [batch, 84, 8400] for YOLOv8 format
            # Extract bbox with highest confidence
            pred = outputs[0][0]  # (84, 8400)

            # Handle different output shapes
            if pred.shape[0] < pred.shape[1]:
                # Standard YOLOv8: (84, 8400) - rows are [cx, cy, w, h, class_scores...]
                scores = pred[4:, :].max(axis=0)
                best_idx = scores.argmax()
                if scores[best_idx] < 0.3:
                    return self._center_crop(frame)
                cx, cy, bw, bh = pred[:4, best_idx]
            else:
                # Transposed format: (8400, 84)
                pred_t = pred.T
                scores = pred_t[:, 4:].max(axis=1)
                best_idx = scores.argmax()
                if scores[best_idx] < 0.3:
                    return self._center_crop(frame)
                cx, cy, bw, bh = pred_t[best_idx, :4]

            # Convert from normalized 640x640 space to original frame space
            x1 = int((cx - bw / 2) / 640 * w)
            y1 = int((cy - bh / 2) / 640 * h)
            x2 = int((cx + bw / 2) / 640 * w)
            y2 = int((cy + bh / 2) / 640 * h)

            # Add 10% padding, clamp to frame bounds
            pad_x = int((x2 - x1) * 0.1)
            pad_y = int((y2 - y1) * 0.1)
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w, x2 + pad_x)
            y2 = min(h, y2 + pad_y)

            if x2 > x1 and y2 > y1:
                return frame[y1:y2, x1:x2]
            return self._center_crop(frame)
        except Exception:
            return self._center_crop(frame)

    def _center_crop(self, frame: np.ndarray) -> np.ndarray:
        """
        Fallback center crop: returns the center 70% of the frame.

        Args:
            frame: BGR frame (H, W, 3).

        Returns:
            Center-cropped frame.
        """
        h, w = frame.shape[:2]
        margin_x, margin_y = int(w * 0.15), int(h * 0.15)
        return frame[margin_y:h - margin_y, margin_x:w - margin_x]


# Singleton instance
_crop_service: Optional[FishCropService] = None
_crop_service_lock = threading.Lock()


def get_crop_service() -> FishCropService:
    """
    Return the process-wide FishCropService singleton, creating it on first use.

    Uses double-checked locking: without it two concurrent first-callers can each
    construct the service, loading the model weights twice (wasted memory) or
    publishing a partially initialised instance.

    Returns:
        The shared FishCropService instance.
    """
    global _crop_service
    if _crop_service is None:
        with _crop_service_lock:
            if _crop_service is None:
                _crop_service = FishCropService()
    return _crop_service
