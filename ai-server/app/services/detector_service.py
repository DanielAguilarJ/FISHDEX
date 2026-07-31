"""
YOLOv8 OBB (Oriented Bounding Box) detector service for FishDex AI Server.
Handles fish detection with rotated bounding boxes from ONNX inference.
Uses letterbox preprocessing (aspect-ratio-preserving resize + padding).
"""

import threading
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_instance: Optional["DetectorService"] = None
_detector_service_lock = threading.Lock()

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

    hw = w / 2.0
    hh = h / 2.0

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


def _nms_axis_aligned(
    detections: list,
    iou_threshold: float = 0.45,
) -> list:
    """
    Apply axis-aligned NMS to a list of DetectionResult objects.
    Uses cv2.dnn.NMSBoxes on the bbox_xyxy of each detection.
    Returns the surviving subset, sorted by confidence descending.
    """
    if not detections:
        return []

    boxes = []
    scores = []
    for d in detections:
        x1, y1, x2, y2 = d.bbox_xyxy
        bw = max(1, int(x2 - x1))
        bh = max(1, int(y2 - y1))
        boxes.append([int(max(0, x1)), int(max(0, y1)), bw, bh])
        scores.append(float(d.confidence))

    indices = cv2.dnn.NMSBoxes(
        boxes,
        scores,
        score_threshold=0.0,   # pre-filtered already
        nms_threshold=iou_threshold,
    )

    if len(indices) == 0:
        return []

    flat = np.array(indices).flatten().tolist()
    kept = [detections[i] for i in flat]
    kept.sort(key=lambda d: d.confidence, reverse=True)
    return kept


class DetectorService:
    """YOLOv8 OBB fish detector using ONNX runtime with letterbox preprocessing."""

    def __init__(self) -> None:
        self.model_path = Path(settings.detector_model_path)
        self.confidence_threshold = settings.detector_confidence_threshold
        self.session = None
        self._available = False

        if self.model_path.exists():
            try:
                import onnxruntime as ort

                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if ort.get_available_providers() and "CUDAExecutionProvider" in ort.get_available_providers() else ["CPUExecutionProvider"]
                sess_options = ort.SessionOptions()
                sess_options.intra_op_num_threads = 0  # 0 = Use 100% of all available CPU cores for max speed
                sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

                self.session = ort.InferenceSession(
                    str(self.model_path),
                    sess_options=sess_options,
                    providers=providers,
                )
                self._available = True
                logger.info("Detector model loaded: %s (providers=%s)", self.model_path, providers)
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

    def _preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, int, int, int, int]:
        """
        Letterbox preprocessing: resize keeping aspect ratio + gray padding.
        Returns (input_tensor, ratio, pad_left, pad_top, orig_h, orig_w).
        """
        orig_h, orig_w = frame.shape[:2]

        # Convert BGR to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Calculate scale ratio (fit within 640x640 maintaining aspect)
        ratio = min(INPUT_SIZE / orig_w, INPUT_SIZE / orig_h)
        new_w = int(round(orig_w * ratio))
        new_h = int(round(orig_h * ratio))

        # Resize maintaining aspect ratio
        resized = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        # Pad to 640x640 with gray (114, 114, 114) — standard YOLO letterbox
        pad_w = INPUT_SIZE - new_w
        pad_h = INPUT_SIZE - new_h
        pad_left = pad_w // 2
        pad_top = pad_h // 2
        pad_right = pad_w - pad_left
        pad_bottom = pad_h - pad_top

        padded = cv2.copyMakeBorder(
            resized, pad_top, pad_bottom, pad_left, pad_right,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )

        # Normalize 0-1, HWC -> CHW, add batch dim
        blob = padded.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))  # CHW
        blob = np.expand_dims(blob, axis=0)  # NCHW

        return blob, ratio, pad_left, pad_top, orig_h, orig_w

    def _parse_obb_output(
        self,
        output: np.ndarray,
        ratio: float,
        pad_left: int,
        pad_top: int,
        orig_h: int,
        orig_w: int,
        conf_threshold: float | None = None,
    ) -> list[DetectionResult]:
        """
        Parse YOLOv8 OBB ONNX output.

        Column layout is controlled by settings.detector_output_layout:
          "xywh_conf_angle"  (default): [cx, cy, w, h, conf, angle]  ← Ultralytics YOLOv8 OBB nc=1
          "xywh_angle_conf"           : [cx, cy, w, h, angle, conf]  ← older/custom exports

        For nc>1 (n_cols > 6) the generic format is used:
          [cx, cy, w, h, class_scores..., angle]  (angle in last column)

        All coordinates are converted from letterbox 640×640 space back to
        original image space by removing padding and dividing by ratio.
        """
        threshold = conf_threshold if conf_threshold is not None else self.confidence_threshold
        layout = settings.detector_output_layout  # "xywh_conf_angle" or "xywh_angle_conf"

        out = output[0]  # Remove batch dim

        if out.ndim != 2:
            logger.warning("OBB output is not 2D: shape=%s", out.shape)
            return []

        dim0, dim1 = out.shape

        # Transpose to (N, D) if needed — D is the small dimension
        if dim0 < dim1:
            out = out.T

        n_preds, n_cols = out.shape

        if n_cols < 6:
            logger.warning("OBB output has too few columns (%d < 6)", n_cols)
            return []

        results = []
        for pred in out:
            cx_lb = float(pred[0])
            cy_lb = float(pred[1])
            w_lb  = float(pred[2])
            h_lb  = float(pred[3])

            # ── Column layout: derive conf and angle ───────────────────────────
            if n_cols == 6:
                # nc=1: exactly 6 columns. Layout determined by config.
                if layout == "xywh_angle_conf":
                    angle = float(pred[4])
                    conf  = float(pred[5])
                else:
                    # Default: Ultralytics YOLOv8 OBB nc=1
                    # [cx, cy, w, h, conf, angle]
                    conf  = float(pred[4])
                    angle = float(pred[5])
                class_id = 0
            elif n_cols == 7:
                # Legacy explicit: [cx, cy, w, h, angle, conf, class_id]
                angle    = float(pred[4])
                conf     = float(pred[5])
                class_id = int(pred[6])
            else:
                # Generic YOLO OBB nc>1: [cx, cy, w, h, class_scores..., angle]
                class_scores = pred[4:-1]
                angle    = float(pred[-1])
                class_id = int(np.argmax(class_scores))
                conf     = float(class_scores[class_id])

            # ── Validity guards ────────────────────────────────────────────────
            if not np.isfinite(conf) or conf < threshold or conf > 1.0:
                continue
            if not np.isfinite(angle):
                continue
            if w_lb <= 2.0 or h_lb <= 2.0:
                continue

            # ── Convert corners from letterbox 640×640 space to original coords ─
            corners_lb = _obb_to_corners(cx_lb, cy_lb, w_lb, h_lb, angle)

            corners_orig = []
            for x_lb, y_lb in corners_lb:
                x_orig = (x_lb - pad_left) / ratio
                y_orig = (y_lb - pad_top) / ratio
                # Clamp to image bounds
                x_orig = max(0.0, min(float(orig_w - 1), x_orig))
                y_orig = max(0.0, min(float(orig_h - 1), y_orig))
                corners_orig.append((x_orig, y_orig))

            bbox_xyxy = _polygon_to_bbox_xyxy(corners_orig)

            results.append(
                DetectionResult(
                    confidence=conf,
                    class_id=class_id,
                    polygon=corners_orig,
                    bbox_xyxy=bbox_xyxy,
                    angle=float(angle),
                )
            )

        # ── NMS: remove duplicate / overlapping raw predictions ────────────────
        results = _nms_axis_aligned(
            results,
            iou_threshold=settings.detector_nms_iou_threshold,
        )
        # _nms_axis_aligned already sorts by confidence descending
        return results

    def detect(self, frame: np.ndarray, conf_threshold: float | None = None) -> list[DetectionResult]:
        """
        Run OBB detection on a BGR frame.
        Returns list of DetectionResult sorted by confidence.
        Falls back to center-crop pseudo-detection if model unavailable.

        Args:
            frame: BGR numpy array
            conf_threshold: override confidence threshold (for retries)
        """
        if not self._available or self.session is None:
            return self._fallback_detection(frame)

        try:
            blob, ratio, pad_left, pad_top, orig_h, orig_w = self._preprocess(frame)

            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: blob})

            raw_output = outputs[0]
            detections = self._parse_obb_output(
                raw_output, ratio, pad_left, pad_top, orig_h, orig_w,
                conf_threshold=conf_threshold,
            )

            logger.debug("Detected %d fish in frame (threshold=%.2f)",
                         len(detections), conf_threshold or self.confidence_threshold)
            return detections

        except Exception as e:
            logger.error("Detection inference failed: %s", e)
            return self._fallback_detection(frame)

    def _fallback_detection(self, frame: np.ndarray) -> list[DetectionResult]:
        """Return a center 70% crop as a single pseudo-detection.
        Confidence is set to 0.01 so it's recognized as a fallback and never
        passes threshold checks for crop validation."""
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
                confidence=0.01,
                class_id=0,
                polygon=polygon,
                bbox_xyxy=(x1, y1, x2, y2),
                angle=0.0,
            )
        ]


def get_detector_service() -> DetectorService:
    """
    Return the process-wide DetectorService singleton, creating it on first use.

    Uses double-checked locking: without it two concurrent first-callers can each
    construct the service, loading the model weights twice (wasted memory) or
    publishing a partially initialised instance.

    Returns:
        The shared DetectorService instance.
    """
    global _instance
    if _instance is None:
        with _detector_service_lock:
            if _instance is None:
                _instance = DetectorService()
    return _instance


def get_loaded_detector_service() -> Optional[DetectorService]:
    """
    Return the singleton only if it has already been constructed.

    Lets health and diagnostic endpoints report model status without triggering a
    heavyweight model load on the first probe.

    Returns:
        The existing instance, or None when it was never created.
    """
    return _instance
