"""
Fish species classifier service for FishDex AI Server.
Runs ONNX classification model or gracefully falls back when model is unavailable.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_instance: Optional["ClassifierService"] = None

# ImageNet normalization constants
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

INPUT_SIZE = 224


class ClassifierService:
    """Fish species classifier using ONNX model with graceful fallback."""

    def __init__(self):
        self.model_path = Path(settings.classifier_model_path)
        self.labels_path = Path(settings.classifier_labels_path)
        self.session = None
        self.labels: dict[int, str] = {}
        self._available = False

        self._load_model()

    def _load_model(self):
        """Attempt to load the ONNX classifier and labels."""
        if not self.model_path.exists():
            logger.warning("Classifier model not found at %s", self.model_path)
            return

        if not self.labels_path.exists():
            logger.warning("Classifier labels not found at %s", self.labels_path)
            return

        try:
            # Load labels
            with open(self.labels_path, "r") as f:
                raw_labels = json.load(f)
            self.labels = {int(k): v for k, v in raw_labels.items()}

            # Load ONNX model
            import onnxruntime as ort

            self.session = ort.InferenceSession(
                str(self.model_path),
                providers=["CPUExecutionProvider"],
            )
            self._available = True
            logger.info(
                "Classifier loaded: %s (%d classes)",
                self.model_path,
                len(self.labels),
            )
        except Exception as e:
            logger.error("Failed to load classifier: %s", e)
            self.session = None
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess a BGR cropped fish image for classification.
        Resize to 224x224, normalize with ImageNet mean/std, HWC -> CHW.
        """
        # BGR to RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        # Resize
        resized = cv2.resize(rgb, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_LINEAR)

        # Normalize to 0-1 then apply ImageNet stats
        normalized = resized.astype(np.float32) / 255.0
        normalized = (normalized - IMAGENET_MEAN) / IMAGENET_STD

        # HWC -> CHW, add batch dim
        blob = np.transpose(normalized, (2, 0, 1))
        blob = np.expand_dims(blob, axis=0)

        return blob

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        """Compute softmax probabilities."""
        exp = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        return exp / np.sum(exp, axis=-1, keepdims=True)

    def classify(self, image: np.ndarray, top_k: int = 5) -> dict:
        """
        Classify a cropped fish image.

        Args:
            image: BGR numpy array of the cropped fish region.
            top_k: Number of top predictions to return.

        Returns:
            dict with either:
              - {"available": True, "predictions": [{"species_slug": str, "confidence": float}, ...]}
              - {"available": False, "requires_manual_input": True}
        """
        if not self._available or self.session is None:
            return {"available": False, "requires_manual_input": True}

        try:
            blob = self._preprocess(image)

            input_name = self.session.get_inputs()[0].name
            outputs = self.session.run(None, {input_name: blob})

            logits = outputs[0]  # shape: (1, num_classes)
            probs = self._softmax(logits[0])

            # Get top-k indices
            top_indices = np.argsort(probs)[::-1][:top_k]

            predictions = []
            for idx in top_indices:
                species_slug = self.labels.get(int(idx), f"unknown_{idx}")
                confidence = float(probs[idx])
                predictions.append({
                    "species_slug": species_slug,
                    "confidence": confidence,
                })

            return {"available": True, "predictions": predictions}

        except Exception as e:
            logger.error("Classification inference failed: %s", e)
            return {"available": False, "requires_manual_input": True}


def get_classifier_service() -> ClassifierService:
    """Return the singleton ClassifierService instance."""
    global _instance
    if _instance is None:
        _instance = ClassifierService()
    return _instance
