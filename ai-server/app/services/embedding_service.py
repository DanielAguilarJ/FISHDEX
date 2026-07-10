"""
FishDex AI Server - Embedding Service
=======================================
Extracts feature vectors from fish images using ResNet50 (ImageNet weights).
The final FC layer is removed, producing a 2048-d embedding per image.

Note: ImageNet weights are a starting point — the embeddings capture general
visual features (texture, shape, color distribution) but are NOT trained
for individual re-identification.  For production accuracy, fine-tune with
triplet loss / ArcFace on a labelled fish dataset.
"""

import logging
import time
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms
from torchvision.models import resnet50, ResNet50_Weights

from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Extract 2048-d feature embeddings from fish images using ResNet50."""

    def __init__(self) -> None:
        """Initialize. Model is loaded lazily on first call."""
        self._model: Optional[nn.Module] = None
        self._device = torch.device(settings.device)
        self._preprocess = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])
        logger.info(
            "EmbeddingService created (device=%s, lazy load)", settings.device
        )

    def _ensure_model(self) -> nn.Module:
        """Load the ResNet50 model on first use (lazy initialization)."""
        if self._model is not None:
            return self._model

        t0 = time.perf_counter()
        base_model = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
        # Remove the final FC layer — output is the 2048-d avgpool vector
        self._model = nn.Sequential(*list(base_model.children())[:-1])
        self._model.to(self._device)
        self._model.eval()
        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "ResNet50 embedding model loaded in %.1fms (device=%s)",
            elapsed,
            self._device,
        )
        return self._model

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def extract_embedding(self, frame: np.ndarray) -> np.ndarray:
        """
        Extract a single 2048-d L2-normalized embedding from a BGR image.

        Args:
            frame: BGR numpy array (OpenCV format).

        Returns:
            L2-normalized 2048-d numpy vector (float32).
        """
        model = self._ensure_model()

        # BGR → RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        tensor = self._preprocess(rgb).unsqueeze(0).to(self._device)

        with torch.no_grad():
            features = model(tensor)  # shape: (1, 2048, 1, 1)

        embedding = features.squeeze().cpu().numpy()  # shape: (2048,)

        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding.astype(np.float32)

    def extract_embeddings(self, frames: list[np.ndarray]) -> np.ndarray:
        """
        Extract embeddings from multiple frames and return their mean.

        Useful for computing a representative embedding from several views
        of the same fish.

        Args:
            frames: List of BGR numpy arrays.

        Returns:
            L2-normalized mean embedding (2048-d float32 vector).
        """
        if not frames:
            return np.zeros(settings.embedding_dim, dtype=np.float32)

        embeddings = np.array([self.extract_embedding(f) for f in frames])
        mean_emb = embeddings.mean(axis=0)

        # Re-normalize the mean
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb = mean_emb / norm

        return mean_emb.astype(np.float32)

    @staticmethod
    def compute_cosine_similarity(emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        """
        Compute cosine similarity between two L2-normalized embeddings.

        Since both vectors are already L2-normalized, cosine similarity
        is simply their dot product.

        Args:
            emb_a: First embedding (2048-d).
            emb_b: Second embedding (2048-d).

        Returns:
            Cosine similarity in [-1.0, 1.0], clamped to [0.0, 1.0].
        """
        similarity = float(np.dot(emb_a, emb_b))
        return max(0.0, min(1.0, similarity))


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the singleton EmbeddingService instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
