"""
YOLOv8 OBB (Oriented Bounding Box) detector service for FishDex AI Server.
Handles fish detection with rotated bounding boxes from ONNX inference.
"""

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_instance: Optional["DetectorService"] = None

INPUT_SIZE = 640


@dataclass
class DetectionResult:
    """A single OBB detection result."""

    confidence: float
    class_id: int
    polygon: list[tuple[float, float]]  # 4 corner points (x, y) in original image coords
    bbox_xyxy: tuple[float, float, float, float]  # min bounding rect (x1, y1, x2, y2)
    angle: float  # radians


def _obb_to_corners(cx: float, cy: float, w: float, h: float, angle: float) -> list[tuple[float, float]]:
    """Convert OBB (center, size, angle) to 4 corner points using rotation matrix."""
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    # Half dimensions
    hw = w / 2.0
    hh = h / 2.0

    # Corner offsets (unrotated)
    corners_offset = [
        (-hw, -hh),
        (hw, -hh),
        (hw, hh),
        (-hw, hh),
    ]

    corners = []
    for dx, dy in corners_offset:
        rx = cx + dx * cos_a - dy * sin_a
        ry = cy + dx * sin_a + dy * cos_a
        corners.append((rx, ry))

    return corners


def _polygon_to_bbox_xyxy(polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Get axis-aligned bounding rect from polygon corners."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


class DetectorService:
    """YOLOv8 OBB fish detector using ONNX runtime."""

    def __init__(self):
        self.model_path = Path(settings.detector_model_path)
        self.confidence_threshold = settings.detector_confidence_threshold
        self.session = None
        self._available = False

        if self.model_path.exists():
            try:
                import onnxruntime as ort

                self.session = ort.InferenceSession(
                    str(self.model_path),
                    providers=["CPUExecutionProvider"],
                )
                self._available = True
                logger.info("Detector model loaded: %s", self.model_path)
            except Exception as e:
                logger.warning("Failed to load detector model: %s", e)
        else:
            logger.warning(
                "Detector model not found at %s, using fallback center-crop",
                self.model_path,
            )

    @property
    def available(self) -> bool:
        return self._available

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, float, int, int]:
        """
        Preprocess frame for YOLOv8 OBB inference.
        Returns (input_tensor, scale_x, scale_y, orig_h, orig_w).
        """
        orig_h, orig_w = frame.shape[:2]

        # Convert BGR to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Resize to 640x640 (letterbox not used here for simplicity - direct resize)
        resized = cv2.resize(rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)

        # Normalize 0-1, HWC -> CHW, add batch dim
        blob = resized.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))  # CHW
        blob = np.expand_dims(blob, axis=0)  # NCHW

        scale_x = orig_w / INPUT_SIZE
        scale_y = orig_h / INPUT_SIZE

        return blob, scale_x, scale_y, orig_h, orig_w

    def _parse_obb_output(
        self, output: np.ndarray, scale_x: float, scale_y: float
    ) -> list[DetectionResult]:
        """
        Parse YOLOv8 OBB ONNX output.
        Handles two possible shapes:
          - [1, num_preds, 7]: each row is [cx, cy, w, h, angle, conf, class_id]
          - [1, 7, num_preds]: transposed version
        """
        # Remove batch dimension
        out = output[0]  # shape: (num_preds, 7) or (7, num_preds)

        # Detect orientation: if dim 0 is 7 (or small fixed), it's transposed
        if out.shape[0] == 7 and out.shape[1] != 7:
            out = out.T  # Now (num_preds, 7)
        elif out.shape[1] != 7 and out.shape[0] != 7:
            # Try alternative: might be (num_preds, 7) already or unexpected shape
            if out.shape[1] == 7:
                pass  # Already correct
            else:
                logger.warning("Unexpected OBB output shape: %s", out.shape)
                return []

        results = []
        for pred in out:
            cx, cy, w, h, angle, conf, class_id = pred[:7]

            if conf < self.confidence_threshold:
                continue

            # Convert corners in 640x640 space
            corners_640 = _obb_to_corners(cx, cy, w, h, angle)

            # Scale corners to original image coordinates
            corners_orig = [
                (x * scale_x, y * scale_y) for x, y in corners_640
            ]

            bbox_xyxy = _polygon_to_bbox_xyxy(corners_orig)

            results.append(
                DetectionResult(
                    confidence=float(conf),
                    class_id=int(class_id),
                    polygon=corners_orig,
                    bbox_xyxy=bbox_xyxy,
                    angle=float(angle),
                )
            )

        # Sort by confidence descending
        results.sort(key=lambda d: d.confidence, reverse=True)
        return results

    def detect(self, frame: np.ndarray) -> list[DetectionResult]:
        """
        Run OBB detection on a BGR frame.
        Returns list of DetectionResult sorted by confidence.
        Falls back to center-crop pseudo-detection if model unavailable.
        """
        if not self._available or self.session is None:
            return self._fallback_detection(frame)

        try:
            blob, scale_x, scale_y, orig_h, orig_w = self._preprocess(frame)

            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: blob})

            # First output contains the OBB predictions
            raw_output = outputs[0]
            detections = self._parse_obb_output(raw_output, scale_x, scale_y)

            logger.debug("Detected %d fish in frame", len(detections))
            return detections

        except Exception as e:
            logger.error("Detection inference failed: %s", e)
            return self._fallback_detection(frame)

    def _fallback_detection(self, frame: np.ndarray) -> list[DetectionResult]:
        """Return a center 70% crop as a single pseudo-detection."""
        h, w = frame.shape[:2]
        margin_x = w * 0.15
        margin_y = h * 0.15

        x1 = margin_x
        y1 = margin_y
        x2 = w - margin_x
        y2 = h - margin_y

        polygon = [
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2),
        ]

        return [
            DetectionResult(
                confidence=0.5,
                class_id=0,
                polygon=polygon,
                bbox_xyxy=(x1, y1, x2, y2),
                angle=0.0,
            )
        ]


def crop_fish_obb(frame: np.ndarray, detection: DetectionResult, padding: float = 0.10) -> np.ndarray:
    """
    Crop a fish region from frame using OBB polygon.
    MVP approach: uses min/max of polygon corners as rectangular crop with padding.
    Returns cropped BGR numpy array.
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = detection.bbox_xyxy

    # Add padding
    pad_x = (x2 - x1) * padding
    pad_y = (y2 - y1) * padding

    x1 = max(0, int(x1 - pad_x))
    y1 = max(0, int(y1 - pad_y))
    x2 = min(w, int(x2 + pad_x))
    y2 = min(h, int(y2 + pad_y))

    # Ensure minimum crop size
    if x2 - x1 < 10 or y2 - y1 < 10:
        return frame

    crop = frame[y1:y2, x1:x2].copy()
    return crop


def get_detector_service() -> DetectorService:
    """Return the singleton DetectorService instance."""
    global _instance
    if _instance is None:
        _instance = DetectorService()
    return _instance
