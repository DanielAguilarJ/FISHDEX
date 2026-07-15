"""
FishDex AI Server - ReID Embedding Service
============================================
Reemplaza embedding_service.py (ResNet50 2048-d) con FishEncoder 512-d.

Responsabilidades:
  - Cargar FishEncoder desde settings.reid_model_path (singleton, lazy)
  - Recibir imágenes BGR (OpenCV) → BGR→RGB → resize 128×128 → tensor batch
  - Devolver embeddings L2-normalizados de 512 dimensiones
  - Procesar en batches configurables para no reventar RAM/GPU en catch grande
  - Usar torch.inference_mode() siempre

Métodos públicos:
  extract_embedding(frame)          → (512,)  float32 numpy
  extract_embedding_matrix(frames)  → (N,512) float32 numpy
  extract_prototype(frames)         → (512,)  float32 numpy  (media L2-norm)
"""

from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms

from app.config import settings

logger = logging.getLogger(__name__)


class ReIDEmbeddingService:
    """Wraps FishEncoder for inference-only embedding extraction."""

    def __init__(self) -> None:
        self._model = None
        self._transform: Optional[transforms.Compose] = None
        self._device: Optional[torch.device] = None
        self.is_loaded: bool = False
        self._load()

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load FishEncoder checkpoint. Logs success or failure clearly."""
        try:
            from app.services.fish_encoder_model import load_model_for_infer, build_eval_transform

            device_str = settings.device if hasattr(settings, "device") else "cpu"
            self._device = torch.device(device_str)

            self._model = load_model_for_infer(
                model_path=settings.reid_model_path,
                model_name=settings.reid_model_name,
                out_dim=settings.reid_embedding_dim,
                device=self._device,
            )
            self._transform = build_eval_transform(img_size=settings.reid_img_size)
            self.is_loaded = True
            logger.info(
                "ReIDEmbeddingService loaded: model=%s  dim=%d  img_size=%d  device=%s",
                settings.reid_model_name,
                settings.reid_embedding_dim,
                settings.reid_img_size,
                self._device,
            )
        except Exception as exc:
            logger.error(
                "ReIDEmbeddingService FAILED to load FishEncoder from '%s': %s",
                settings.reid_model_path,
                exc,
                exc_info=True,
            )
            self.is_loaded = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bgr_to_pil(self, frame: np.ndarray) -> Image.Image:
        """Convert OpenCV BGR uint8 frame → PIL RGB Image."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def _frames_to_tensor(self, frames: list[np.ndarray]) -> torch.Tensor:
        """Stack a list of BGR frames into a normalised (N,3,H,W) tensor."""
        assert self._transform is not None
        tensors = [self._transform(self._bgr_to_pil(f)) for f in frames]
        return torch.stack(tensors, dim=0)  # (N,3,H,W)

    def _assert_loaded(self) -> None:
        if not self.is_loaded or self._model is None:
            raise RuntimeError(
                "ReIDEmbeddingService: FishEncoder is not loaded. "
                "Check 'FISHDEX_REID_MODEL_PATH' in your .env and server logs."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @torch.inference_mode()
    def extract_embedding(self, frame: np.ndarray) -> np.ndarray:
        """
        Extract a single L2-normalised 512-d embedding from one BGR frame.

        Args:
            frame: BGR uint8 numpy array (OpenCV format).

        Returns:
            (512,) float32 numpy array, L2-normalised.
        """
        self._assert_loaded()
        return self.extract_embedding_matrix([frame])[0]

    @torch.inference_mode()
    def extract_embedding_matrix(self, frames: list[np.ndarray]) -> np.ndarray:
        """
        Extract embeddings from a list of BGR frames.

        Processes in batches of settings.reid_batch_size to limit memory.

        Args:
            frames: List of BGR uint8 numpy arrays.

        Returns:
            (N, 512) float32 numpy array, each row L2-normalised.
        """
        self._assert_loaded()
        assert self._model is not None and self._device is not None

        if not frames:
            return np.zeros((0, settings.reid_embedding_dim), dtype=np.float32)

        batch_size = max(1, settings.reid_batch_size)
        all_embeddings: list[np.ndarray] = []

        for start in range(0, len(frames), batch_size):
            batch_frames = frames[start : start + batch_size]
            tensor = self._frames_to_tensor(batch_frames).to(self._device, non_blocking=True)
            embeddings = self._model.forward_embed_bn(tensor)  # (B, D) normalised
            all_embeddings.append(embeddings.cpu().numpy())

        return np.concatenate(all_embeddings, axis=0).astype(np.float32)

    @torch.inference_mode()
    def extract_prototype(self, frames: list[np.ndarray]) -> np.ndarray:
        """
        Compute a single L2-normalised prototype (mean embedding) from a list of frames.

        Args:
            frames: List of BGR uint8 numpy arrays.

        Returns:
            (512,) float32 numpy array, L2-normalised mean.
        """
        self._assert_loaded()
        if not frames:
            return np.zeros(settings.reid_embedding_dim, dtype=np.float32)

        matrix = self.extract_embedding_matrix(frames)  # (N, 512)
        mean_emb = matrix.mean(axis=0)  # (512,)
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb = mean_emb / norm
        return mean_emb.astype(np.float32)

    @torch.inference_mode()
    def extract_embedding_matrix_from_paths(self, paths: list[str]) -> np.ndarray:
        """
        Load images from disk paths and extract embeddings.

        Args:
            paths: List of image file paths (any OpenCV-readable format).

        Returns:
            (N, 512) float32 numpy array. Unreadable images are skipped.
        """
        frames: list[np.ndarray] = []
        for p in paths:
            img = cv2.imread(p)
            if img is not None:
                frames.append(img)
            else:
                logger.warning("ReIDEmbeddingService: could not read image: %s", p)

        if not frames:
            return np.zeros((0, settings.reid_embedding_dim), dtype=np.float32)

        return self.extract_embedding_matrix(frames)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_reid_embedding_service: Optional[ReIDEmbeddingService] = None


def get_reid_embedding_service() -> ReIDEmbeddingService:
    """Get or create the singleton ReIDEmbeddingService instance."""
    global _reid_embedding_service
    if _reid_embedding_service is None:
        _reid_embedding_service = ReIDEmbeddingService()
    return _reid_embedding_service
