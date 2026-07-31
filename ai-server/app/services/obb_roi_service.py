"""
FishDex AI Server - OBB ROI Service
=====================================
Reemplaza crop_service.py (ONNX bbox + center-crop fallback) con un
servicio online basado en YOLO OBB .pt.

Adaptado de obb_roi_extractor_summerscholl_2026_ID.py para el flujo online:
  - Recibe un frame BGR (np.ndarray)
  - Ejecuta YOLO OBB inference
  - Valida: exactamente 1 detección (si roi_require_single_detection=True)
  - Recorta y endereza el ROI con perspectiva (deskew)
  - Devuelve RoiResult(qualified, roi, confidence, reason)

Diferencias respecto al script offline:
  - Sin process_dataset() ni lectura de disco
  - Sin CSV de unqualified, sin _log_unqualified
  - Sin guardar _vis.jpg en el flujo online (contamina soporte si se usa ImageFolder)
  - Sin center-crop fallback (embeddings malos arruinan el matching)
"""

from __future__ import annotations

import threading

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RoiResult:
    """Resultado de la extracción de ROI para un frame."""
    qualified: bool
    roi: Optional[np.ndarray]
    confidence: float
    reason: Optional[str]


class OBBRoiService:
    """
    Online OBB ROI extractor powered by YOLO .pt.

    El modelo se carga en el primer uso (lazy init en __init__).
    """

    def __init__(self) -> None:
        """Load the YOLO OBB model, leaving is_loaded False when unavailable."""
        self._model = None
        self.is_loaded: bool = False
        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load the YOLO OBB model. Logs success or failure clearly."""
        model_path = Path(settings.obb_model_path)

        if not model_path.is_file():
            logger.error(
                "OBBRoiService: model file not found at '%s'. "
                "Set FISHDEX_OBB_MODEL_PATH in your .env.",
                model_path,
            )
            return

        try:
            from ultralytics import YOLO  # noqa: PLC0415
            self._model = YOLO(str(model_path))
            self.is_loaded = True
            logger.info(
                "OBBRoiService loaded: model=%s  conf_thresh=%.2f  require_single=%s",
                model_path.name,
                settings.obb_conf_threshold,
                settings.roi_require_single_detection,
            )
        except Exception as exc:
            logger.error(
                "OBBRoiService FAILED to load YOLO from '%s': %s",
                model_path,
                exc,
                exc_info=True,
            )
            self.is_loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_roi(self, frame: np.ndarray) -> RoiResult:
        """
        Detect the fish in a BGR frame and return a perspective-corrected crop.

        Args:
            frame: BGR uint8 numpy array (OpenCV format).

        Returns:
            RoiResult with qualified=True and roi set if a single fish was
            detected and cropped successfully, or qualified=False with reason.
        """
        if not self.is_loaded or self._model is None:
            if settings.roi_allow_center_fallback:
                logger.warning("OBBRoiService: model not loaded — using center-crop fallback")
                return self._center_crop_fallback(frame, reason="model not loaded")
            return RoiResult(
                qualified=False,
                roi=None,
                confidence=0.0,
                reason="OBB model not loaded",
            )

        # ── YOLO inference ──────────────────────────────────────────
        try:
            results = self._model(
                frame,
                verbose=False,
                conf=settings.obb_conf_threshold,
                task="obb",
            )[0]
        except Exception as exc:  # noqa: BLE001 — inference failure degrades to 'no detection'
            logger.warning("OBBRoiService: YOLO inference failed: %s", exc)
            return RoiResult(qualified=False, roi=None, confidence=0.0, reason=f"inference error: {exc}")

        # ── Validate detections ──────────────────────────────────────
        # Guard every attribute access: a malformed or unexpected result object
        # must degrade to "no detection" rather than raise AttributeError and
        # abort the whole identification job.
        obb = getattr(results, "obb", None)
        polygons_tensor = getattr(obb, "xyxyxyxy", None) if obb is not None else None
        confidences_tensor = getattr(obb, "conf", None) if obb is not None else None

        if polygons_tensor is None or confidences_tensor is None:
            return RoiResult(
                qualified=False, roi=None, confidence=0.0, reason="no detection"
            )
        if len(polygons_tensor) == 0:
            return RoiResult(
                qualified=False, roi=None, confidence=0.0, reason="no detection"
            )

        polys = polygons_tensor.cpu().numpy()
        confs = confidences_tensor.cpu().numpy()
        n_detections = len(polys)

        if n_detections == 0 or len(confs) == 0:
            return RoiResult(
                qualified=False, roi=None, confidence=0.0, reason="no detection"
            )

        if n_detections > 1 and settings.roi_require_single_detection:
            return RoiResult(
                qualified=False,
                roi=None,
                confidence=float(confs.max()),
                reason=f"{n_detections} detections (require_single_detection=True)",
            )

        # Use the highest-confidence detection
        best_idx = int(confs.argmax())
        best_poly = polys[best_idx].reshape((4, 2))
        conf = float(confs[best_idx])

        # ── Deskew crop ──────────────────────────────────────────────
        roi = self._deskew_crop(frame, best_poly)
        if roi is None or roi.size == 0:
            return RoiResult(
                qualified=False,
                roi=None,
                confidence=conf,
                reason="empty ROI after perspective crop",
            )

        # ── Validar tamaño mínimo del ROI ────────────────────────────
        h_roi, w_roi = roi.shape[:2]
        min_side = settings.roi_min_side_px
        if min(h_roi, w_roi) < min_side:
            return RoiResult(
                qualified=False,
                roi=None,
                confidence=conf,
                reason=f"ROI too small ({w_roi}x{h_roi} px, min side={min_side}px)",
            )

        # ── Normalizar a orientación horizontal (ancho > alto) ───────────
        # Un pez debe quedar siempre apaisado para que el embedding sea
        # consistente entre tomas (independientemente de cómo se detectó el OBB).
        if roi.shape[0] > roi.shape[1]:
            roi = cv2.rotate(roi, cv2.ROTATE_90_CLOCKWISE)

        return RoiResult(qualified=True, roi=roi, confidence=conf, reason=None)

    # ------------------------------------------------------------------
    # Geometry helpers (ported from obb_roi_extractor_summerscholl_2026_ID.py)
    # ------------------------------------------------------------------

    @staticmethod
    def _order_points_clockwise(pts: np.ndarray) -> np.ndarray:
        """
        Order 4 OBB corner points as: top-left, top-right, bottom-right, bottom-left.

        Args:
            pts: (4,2) float32 array of corner points.

        Returns:
            (4,2) float32 array ordered TL→TR→BR→BL.
        """
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left  (min sum)
        rect[2] = pts[np.argmax(s)]   # bottom-right (max sum)
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right  (min diff)
        rect[3] = pts[np.argmax(diff)]  # bottom-left (max diff)
        return rect

    def _deskew_crop(self, img: np.ndarray, pts: np.ndarray) -> Optional[np.ndarray]:
        """
        Apply a perspective transform to straighten the OBB ROI.

        Args:
            img: Source BGR frame.
            pts: (4,2) float32 corner points of the OBB.

        Returns:
            Warped BGR crop, or None if geometry is degenerate.
        """
        pts = np.array(pts, dtype=np.float32)
        rect = self._order_points_clockwise(pts)
        tl, tr, br, bl = rect

        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_width = int(max(width_a, width_b))
        max_height = int(max(height_a, height_b))

        if max_width <= 0 or max_height <= 0:
            return None

        dst = np.array(
            [
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1],
            ],
            dtype=np.float32,
        )

        m = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img, m, (max_width, max_height))
        return warped

    def _center_crop_fallback(self, frame: np.ndarray, reason: str) -> RoiResult:
        """
        Center-crop fallback (70% of frame).
        Only used when roi_allow_center_fallback=True.

        WARNING: Do not enable in production — center crops generate noisy
        embeddings that degrade matching quality.
        """
        h, w = frame.shape[:2]
        mx, my = int(w * 0.15), int(h * 0.15)
        crop = frame[my : h - my, mx : w - mx]
        return RoiResult(
            qualified=True,
            roi=crop,
            confidence=0.0,
            reason=f"center-crop fallback ({reason})",
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_obb_roi_service: Optional[OBBRoiService] = None
_obb_roi_service_lock = threading.Lock()


def get_obb_roi_service() -> OBBRoiService:
    """
    Return the process-wide OBBRoiService singleton, creating it on first use.

    Uses double-checked locking: without it two concurrent first-callers can each
    construct the service, loading the model weights twice (wasted memory) or
    publishing a partially initialised instance.

    Returns:
        The shared OBBRoiService instance.
    """
    global _obb_roi_service
    if _obb_roi_service is None:
        with _obb_roi_service_lock:
            if _obb_roi_service is None:
                _obb_roi_service = OBBRoiService()
    return _obb_roi_service


def get_loaded_obb_roi_service() -> Optional[OBBRoiService]:
    """
    Return the singleton only if it has already been constructed.

    Lets health and diagnostic endpoints report model status without triggering a
    heavyweight model load on the first probe.

    Returns:
        The existing instance, or None when it was never created.
    """
    return _obb_roi_service
