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
    area_code: str = Field(..., description="Czech fishing area code e.g. '401 001'")
    fisherman_id: str = Field(..., description="UUID of the user (from Appwrite)")
    user_role: str = Field("fisherman", description="'fisherman' or 'researcher'")
    species: Optional[str] = Field(None, description="Species if already known (skip Step 1)")
    fish_state: Optional[str] = Field(None, description="Injury notes or distinguishing marks")
    name: Optional[str] = Field(None, description="Custom name given by fisherman to this fish")
    weather: Optional[str] = Field(None, description="Weather conditions: sunny, cloudy, raining, etc.")
    bite: Optional[str] = Field(None, description="Bait or lure used")
    size: Optional[float] = Field(None, description="Measured size in cm")
    latitude: Optional[float] = Field(None, description="Latitud GPS donde se capturó")
    longitude: Optional[float] = Field(None, description="Longitud GPS donde se capturó")
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
    detection_confidence: float = Field(
        0.0, description="Confidence from ONNX detection/crop step (0-1)"
    )
    match_confidence: float = Field(
        0.0, description="Raw similarity score from the matching pipeline (0-1)"
    )
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
    # New fields for Czech area system
    area_code: Optional[str] = Field(None, description="Czech fishing area code")
    area_name: Optional[str] = Field(None, description="Human-readable area name")
    area_url: Optional[str] = Field(None, description="Link to rybsvaz.cz area page")
    species_czech: Optional[str] = Field(None, description="Czech name of species")
    species_english: Optional[str] = Field(None, description="English name of species")
    catch_number: Optional[int] = Field(None, description="Which catch this is for this fish")
    full_history: Optional[list] = Field(None, description="Full catch history (researchers only)")
    user_role: Optional[str] = Field(None, description="Role of the user who submitted")
    # ReID pipeline debug info (new in v3)
    match_method: Optional[str] = Field(None, description="Matching algorithm used (e.g. fishencoder_prototype_topN_vote)")
    query_images_used: Optional[int] = Field(None, description="Number of query frames used in prototype voting")
    winning_votes: Optional[int] = Field(None, description="Votes the winning identity received")
    roi_images_used: Optional[int] = Field(None, description="Number of frames with a qualified OBB ROI")


class ErrorResponse(BaseModel):
    """Response de error."""
    success: bool = Field(default=False)
    error: str = Field(..., description="Descripción del error")
    detail: Optional[str] = Field(None, description="Detalle técnico del error")
