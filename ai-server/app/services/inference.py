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
# ESPECIES DE PECES (para simulación realista)
# =============================================================================
FISH_SPECIES = [
    {"name": "Trucha Arcoíris", "rarity": "common", "size_range": (15, 60)},
    {"name": "Trucha Marrón", "rarity": "common", "size_range": (20, 70)},
    {"name": "Salmón Atlántico", "rarity": "uncommon", "size_range": (40, 120)},
    {"name": "Lucio", "rarity": "uncommon", "size_range": (30, 130)},
    {"name": "Carpa Común", "rarity": "common", "size_range": (20, 100)},
    {"name": "Black Bass", "rarity": "uncommon", "size_range": (20, 60)},
    {"name": "Barbo", "rarity": "common", "size_range": (15, 80)},
    {"name": "Siluro", "rarity": "rare", "size_range": (50, 250)},
    {"name": "Esturión", "rarity": "legendary", "size_range": (60, 300)},
    {"name": "Tenca", "rarity": "common", "size_range": (15, 50)},
    {"name": "Perca", "rarity": "common", "size_range": (10, 45)},
    {"name": "Lucioperca", "rarity": "rare", "size_range": (30, 100)},
    {"name": "Anguila", "rarity": "rare", "size_range": (30, 120)},
    {"name": "Hucho", "rarity": "legendary", "size_range": (50, 150)},
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
        self.model = PlaceholderModel(model_path)
    
    def identify_fish(self, frame: np.ndarray) -> dict:
        """
        Identifica un pez a partir de un frame de video.
        
        Args:
            frame: Frame seleccionado como array NumPy
        
        Returns:
            Dict con toda la información de la identificación
        """
        # Ejecutar predicción
        fish_id, confidence, metadata = self.model.predict(frame)
        is_new = metadata.get("is_new", True)
        
        # Obtener datos del pez
        fish_data = self.model._known_fish_db.get(fish_id, {})
        species = fish_data.get("species", "Especie Desconocida")
        rarity = fish_data.get("rarity", "common")
        estimated_size = fish_data.get("size", random.uniform(15, 80))
        
        # Calcular XP
        base_xp = XP_BY_RARITY.get(rarity, 10)
        xp_earned = base_xp + (XP_NEW_FISH_BONUS if is_new else 0)
        
        # Si no es nuevo, generar datos previos simulados
        previous_data = None
        if not is_new:
            days_ago = random.randint(3, 60)
            previous_size = estimated_size - random.uniform(0.5, 5.0)
            previous_data = FishPreviousData(
                fish_id=fish_id,
                species=species,
                first_seen_date=(datetime.now() - timedelta(days=days_ago)).isoformat(),
                first_seen_location="Río Guadalquivir, Sector 3",
                total_sightings=fish_data.get("sightings", 2),
                last_seen_date=(datetime.now() - timedelta(days=random.randint(1, days_ago))).isoformat(),
                last_estimated_size_cm=round(previous_size, 1),
                growth_cm=round(estimated_size - previous_size, 1),
            )
        
        # Construir mensaje para el usuario
        if is_new:
            message = f"¡NUEVO PESCADO DESCUBIERTO! Has identificado un/a {species} por primera vez."
        else:
            sightings = fish_data.get("sightings", 2)
            message = f"¡REENCUENTRO! Ya conocías a este {species}. Es la vez #{sightings} que lo ves."
        
        return {
            "success": True,
            "fish_id": fish_id,
            "species": species,
            "confidence": round(confidence, 3),
            "is_new": is_new,
            "estimated_size_cm": round(estimated_size, 1),
            "rarity": rarity,
            "xp_earned": xp_earned,
            "previous_data": previous_data,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }


# Instancia global del servicio (singleton)
_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    """Obtiene o crea la instancia del servicio de inferencia."""
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service
