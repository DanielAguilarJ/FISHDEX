"""
FishDex AI Server - Servicio de Inferencia
============================================
Lógica de identificación de peces.
Actualmente usa un PLACEHOLDER que genera IDs simulados.
Cuando integres tu modelo PyTorch real, reemplaza la clase PlaceholderModel.
"""

import random
import hashlib
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple

from app.models.schemas import FishPreviousData


# =============================================================================
# ESPECIES DE PECES (para simulación realista - legacy fallback)
# =============================================================================
FISH_SPECIES = [
    {"name": "Trucha Arcoíris", "scientific": "Oncorhynchus mykiss", "family": "Salmonidae", "rarity": "common", "size_range": (15, 60)},
    {"name": "Trucha Marrón", "scientific": "Salmo trutta", "family": "Salmonidae", "rarity": "common", "size_range": (20, 70)},
    {"name": "Salmón Atlántico", "scientific": "Salmo salar", "family": "Salmonidae", "rarity": "uncommon", "size_range": (40, 120)},
    {"name": "Lucio", "scientific": "Esox lucius", "family": "Esocidae", "rarity": "uncommon", "size_range": (30, 130)},
    {"name": "Carpa Común", "scientific": "Cyprinus carpio", "family": "Cyprinidae", "rarity": "common", "size_range": (20, 100)},
    {"name": "Black Bass", "scientific": "Micropterus salmoides", "family": "Centrarchidae", "rarity": "uncommon", "size_range": (20, 60)},
    {"name": "Barbo", "scientific": "Barbus barbus", "family": "Cyprinidae", "rarity": "common", "size_range": (15, 80)},
    {"name": "Siluro", "scientific": "Silurus glanis", "family": "Siluridae", "rarity": "rare", "size_range": (50, 250)},
    {"name": "Esturión", "scientific": "Acipenser sturio", "family": "Acipenseridae", "rarity": "legendary", "size_range": (60, 300)},
    {"name": "Tenca", "scientific": "Tinca tinca", "family": "Cyprinidae", "rarity": "common", "size_range": (15, 50)},
    {"name": "Perca", "scientific": "Perca fluviatilis", "family": "Percidae", "rarity": "common", "size_range": (10, 45)},
    {"name": "Lucioperca", "scientific": "Sander lucioperca", "family": "Percidae", "rarity": "rare", "size_range": (30, 100)},
    {"name": "Anguila", "scientific": "Anguilla anguilla", "family": "Anguillidae", "rarity": "rare", "size_range": (30, 120)},
    {"name": "Hucho", "scientific": "Hucho hucho", "family": "Salmonidae", "rarity": "legendary", "size_range": (50, 150)},
]

# XP según rareza
XP_BY_RARITY = {
    "common": 10,
    "uncommon": 25,
    "rare": 50,
    "legendary": 100,
}

# Bonus XP por primer avistamiento
XP_NEW_FISH_BONUS = 50


# =============================================================================
# MODELO PLACEHOLDER (Reemplazar con el modelo real)
# =============================================================================
class PlaceholderModel:
    """
    Modelo placeholder que simula la identificación de peces.

    PARA INTEGRAR TU MODELO REAL:
    1. Reemplaza esta clase con tu modelo PyTorch
    2. Implementa el método predict(frame: np.ndarray) -> Tuple[str, float]
    3. El método debe retornar (fish_id, confidence)
    """

    def __init__(self, model_path: Optional[str] = None):
        """
        Inicializa el modelo.
        En producción, aquí cargarías el modelo PyTorch:
        self.model = torch.load(model_path)
        self.model.eval()
        """
        self.model_path = model_path
        self.is_loaded = True
        # Base de datos simulada de peces "conocidos"
        self._known_fish_db = {}

    def predict(self, frame: np.ndarray) -> Tuple[str, float, dict]:
        """
        Ejecuta la inferencia sobre un frame.

        PLACEHOLDER: Genera un fish_id basado en un hash del frame.
        Esto simula que el mismo pez (mismo frame similar) devuelve el mismo ID.

        Args:
            frame: Frame del video como array NumPy (BGR, shape HxWxC)

        Returns:
            Tuple de (fish_id, confidence, metadata)
        """
        # Generar un hash del frame para simular consistencia
        # En la realidad, el modelo generaría un embedding del pez
        frame_hash = hashlib.md5(frame.tobytes()[:1000]).hexdigest()[:8]

        # Simular: 50% probabilidad de ser un pez "nuevo" vs uno "conocido"
        is_new = random.random() < 0.5

        if is_new or not self._known_fish_db:
            # Generar un nuevo fish_id
            fish_id = f"FISH-{random.randint(1000, 9999)}"
            species_data = random.choice(FISH_SPECIES)
            size = random.uniform(*species_data["size_range"])

            # Guardarlo en nuestra "base de datos" local
            self._known_fish_db[fish_id] = {
                "species": species_data["name"],
                "scientific_name": species_data.get("scientific"),
                "family": species_data.get("family"),
                "rarity": species_data["rarity"],
                "size": round(size, 1),
                "first_seen": datetime.now().isoformat(),
                "sightings": 1,
            }

            return fish_id, random.uniform(0.75, 0.98), {"is_new": True}
        else:
            # Devolver un pez "conocido" aleatorio
            fish_id = random.choice(list(self._known_fish_db.keys()))
            self._known_fish_db[fish_id]["sightings"] += 1

            return fish_id, random.uniform(0.80, 0.99), {"is_new": False}


# =============================================================================
# SERVICIO DE INFERENCIA
# =============================================================================
class InferenceService:
    """Servicio principal de inferencia que coordina el modelo y los datos."""

    def __init__(self, model_path: Optional[str] = None):
        """Initialize inference service with placeholder model."""
        self.model = PlaceholderModel(model_path)

    def identify_fish(
        self,
        frame: np.ndarray,
        area_code: str = "",
        species: Optional[str] = None,
        user_role: str = "fisherman",
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Identifica un pez a partir de un frame de video.

        Implements the full 7-step pipeline with Czech area system integration.

        Args:
            frame: Frame seleccionado como array NumPy (already cropped)
            area_code: Czech fishing area code (e.g. '401 001')
            species: Species name if already known by user (skip Step 1)
            user_role: 'fisherman' or 'researcher'
            metadata: Dict with all catch metadata fields

        Returns:
            Dict con toda la información de la identificación
        """
        if metadata is None:
            metadata = {}

        # Step 3: Look up area information
        area_info = None
        if area_code:
            try:
                from app.data.czech_areas import find_area_by_code
                area_info = find_area_by_code(area_code)
            except ImportError:
                pass

        # Step 1: Species classification (use provided or placeholder)
        species_info = None
        if species:
            try:
                from app.data.czech_species import find_species_by_name
                species_info = find_species_by_name(species)
            except ImportError:
                pass

        # Use species info if found; otherwise fall back to PlaceholderModel
        if species_info:
            # We have a known Czech species
            species_name = species_info["english_name"]
            scientific_name = species_info["latin_name"]
            species_slug = species_info["slug"]
            rarity = species_info["rarity"]
            xp_base = species_info["xp_base"]
            family = None  # Could be added to species DB later
            confidence = random.uniform(0.82, 0.98)  # Higher confidence when user provides species
        else:
            # Fallback: Use PlaceholderModel prediction
            fish_id_placeholder, confidence, pred_metadata = self.model.predict(frame)
            fish_data = self.model._known_fish_db.get(fish_id_placeholder, {})
            species_name = fish_data.get("species", "Unknown Species")
            scientific_name = fish_data.get("scientific_name")
            family = fish_data.get("family")
            rarity = fish_data.get("rarity", "common")
            xp_base = XP_BY_RARITY.get(rarity, 10)
            species_slug = (scientific_name or "unknown_species").lower().replace(" ", "_")

        # Step 5: Generate fish ID and determine if new or recapture
        is_new = True
        fish_id = ""
        catch_number = 1
        history = []

        if area_code and species_slug:
            try:
                from app.services.storage_service import (
                    generate_fish_id,
                    save_catch,
                    get_fish_history,
                    get_restricted_history,
                    list_fish_in_area,
                )

                # Check existing fish in area for this species
                existing_fish = list_fish_in_area(area_code, species_slug)

                if existing_fish:
                    # Simulate: 40% chance of recapture when fish exist in area
                    if random.random() < 0.4:
                        fish_id = random.choice(existing_fish)
                        is_new = False
                    else:
                        fish_id = generate_fish_id(area_code, species_slug)
                        is_new = True
                else:
                    fish_id = generate_fish_id(area_code, species_slug)
                    is_new = True

                # Build full metadata for storage
                storage_metadata = {
                    "area_code": area_code,
                    "fisherman_id": metadata.get("fisherman_id", ""),
                    "datetime": datetime.now().isoformat(),
                    "latitude": metadata.get("latitude"),
                    "longitude": metadata.get("longitude"),
                    "species": species_name,
                    "species_slug": species_slug,
                    "fish_state": metadata.get("fish_state"),
                    "name": metadata.get("name"),
                    "weather": metadata.get("weather"),
                    "bite": metadata.get("bite"),
                    "size": metadata.get("size"),
                    "user_role": user_role,
                }

                # Save the catch
                save_catch(area_code, species_slug, fish_id, [frame], storage_metadata)

                # Get history
                history = get_fish_history(area_code, species_slug, fish_id)
                catch_number = len(history)

            except Exception:
                # If storage fails, generate a fallback ID
                if not fish_id:
                    fish_id = f"CZ-{area_code.replace(' ', '')}-TEMP-{random.randint(1000, 9999)}"
        else:
            # No area code: use simple ID generation
            fish_id = f"FISH-{random.randint(1000, 9999)}"

        # Calculate XP
        xp_earned = xp_base + (XP_NEW_FISH_BONUS if is_new else 0)

        # Estimated size
        estimated_size = metadata.get("size") or random.uniform(15, 80)

        # Build previous data if recapture
        previous_data = None
        if not is_new and history and len(history) > 1:
            first_catch = history[0]
            last_catch = history[-2] if len(history) > 1 else history[0]
            previous_size = last_catch.get("size") or estimated_size - random.uniform(0.5, 5.0)
            previous_data = FishPreviousData(
                fish_id=fish_id,
                species=species_name,
                first_seen_date=first_catch.get("datetime", datetime.now().isoformat()),
                first_seen_location=first_catch.get("area_code", ""),
                total_sightings=len(history),
                last_seen_date=last_catch.get("datetime", datetime.now().isoformat()),
                last_estimated_size_cm=round(float(previous_size) if previous_size else 0, 1),
                growth_cm=round(float(estimated_size) - float(previous_size) if previous_size else 0, 1),
            )

        # Build message
        if is_new:
            message = f"NEW FISH DISCOVERED! You identified a {species_name} for the first time."
        else:
            message = f"RECAPTURE! This {species_name} has been seen {catch_number} times."

        # Build full history for researchers
        full_history = None
        if user_role == "researcher" and history:
            full_history = history
        elif user_role == "fisherman" and history:
            try:
                from app.services.storage_service import get_restricted_history
                full_history = get_restricted_history(history)
            except ImportError:
                full_history = None

        # Build response
        result = {
            "success": True,
            "fish_id": fish_id,
            "species": species_name,
            "scientific_name": scientific_name,
            "family": family,
            "common_name": species_name,
            "confidence": round(confidence, 3),
            "is_new": is_new,
            "estimated_size_cm": round(float(estimated_size), 1),
            "rarity": rarity,
            "xp_earned": xp_earned,
            "requires_manual_input": False,
            "previous_data": previous_data,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            # New Czech area system fields
            "area_code": area_code if area_code else None,
            "area_name": area_info["name"] if area_info else None,
            "area_url": area_info.get("url") if area_info else None,
            "species_czech": species_info["czech_name"] if species_info else None,
            "species_english": species_info["english_name"] if species_info else None,
            "catch_number": catch_number,
            "full_history": full_history,
            "user_role": user_role,
        }

        return result


# Instancia global del servicio (singleton)
_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    """Obtiene o crea la instancia del servicio de inferencia."""
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service
