"""
FishDex AI Server - Modelos Pydantic
=====================================
Esquemas de datos para requests y responses de la API.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class FishPreviousData(BaseModel):
    """Datos previos de un pez ya identificado."""
    fish_id: str = Field(..., description="ID único del pez")
    species: str = Field(..., description="Especie del pez")
    first_seen_date: str = Field(..., description="Fecha del primer avistamiento")
    first_seen_location: Optional[str] = Field(None, description="Ubicación del primer avistamiento")
    total_sightings: int = Field(..., description="Total de veces que ha sido visto")
    last_seen_date: str = Field(..., description="Fecha del último avistamiento")
    last_estimated_size_cm: float = Field(..., description="Último tamaño estimado en cm")
    growth_cm: float = Field(0.0, description="Crecimiento estimado desde el último avistamiento")


class IdentifyRequest(BaseModel):
    """Request para identificar un pez (cuando se envía metadata junto al video)."""
    latitude: Optional[float] = Field(None, description="Latitud GPS donde se capturó")
    longitude: Optional[float] = Field(None, description="Longitud GPS donde se capturó")
    user_id: Optional[str] = Field(None, description="ID del usuario que capturó el video")
    notes: Optional[str] = Field(None, description="Notas adicionales del pescador")
    confidence_threshold: float = Field(
        0.70,
        description="Umbral de confianza. Si la identificación está por debajo, "
                    "se marca como requires_manual_input=True",
        ge=0.0,
        le=1.0,
    )


class IdentifyResponse(BaseModel):
    """Response de identificación de un pez."""
    success: bool = Field(..., description="Si la identificación fue exitosa")
    fish_id: str = Field(..., description="ID único del pez identificado")
    species: str = Field(..., description="Especie identificada (nombre común)")
    scientific_name: Optional[str] = Field(
        None, description="Nombre científico de la especie"
    )
    family: Optional[str] = Field(
        None, description="Familia taxonómica del pez"
    )
    common_name: Optional[str] = Field(
        None, description="Nombre común alternativo"
    )
    confidence: float = Field(..., description="Confianza de la identificación (0-1)")
    is_new: bool = Field(..., description="Si es un pez nuevo (primera vez identificado)")
    estimated_size_cm: float = Field(..., description="Tamaño estimado en centímetros")
    rarity: str = Field(..., description="Rareza del pez: common, uncommon, rare, legendary")
    xp_earned: int = Field(..., description="Puntos de XP ganados por este avistamiento")
    requires_manual_input: bool = Field(
        False,
        description="Si True, la confianza fue baja y se necesita input manual del usuario"
    )
    previous_data: Optional[FishPreviousData] = Field(
        None, description="Datos previos si el pez ya existía"
    )
    frame_used: Optional[str] = Field(
        None, description="Frame del video usado para la identificación (base64)"
    )
    message: str = Field(..., description="Mensaje para mostrar al usuario")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Timestamp de la identificación"
    )


class ErrorResponse(BaseModel):
    """Response de error."""
    success: bool = Field(default=False)
    error: str = Field(..., description="Descripción del error")
    detail: Optional[str] = Field(None, description="Detalle técnico del error")
