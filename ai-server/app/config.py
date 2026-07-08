"""
FishDex AI Server - Configuration
===================================
Centralized settings using pydantic-settings.
Override any setting with environment variables prefixed FISHDEX_.
Example: FISHDEX_SIMILARITY_THRESHOLD=0.80
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Server configuration. Override with environment variables prefixed FISHDEX_."""

    # Similarity pipeline
    similarity_threshold: float = 0.70
    max_frames_to_save: int = 5
    max_frames_to_extract: int = 10
    nearby_area_radius_km: float = 5.0

    # Storage
    server_data_dir: str = "server-data"
    jpeg_quality: int = 90

    # ONNX model
    onnx_model_path: str = "norway fish/fin_detector_best.onnx"

    # Video limits
    max_video_size_mb: int = 50
    max_video_duration_seconds: int = 15

    class Config:
        env_prefix = "FISHDEX_"


# Singleton instance — import this everywhere
settings = Settings()
