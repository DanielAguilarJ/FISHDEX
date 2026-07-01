import 'dart:math';
import '../../core/constants/app_constants.dart';

// =============================================================================
// SERVICIO DE GAMIFICACIÓN
// =============================================================================

/// Servicio que gestiona toda la lógica de gamificación de FishDex:
/// cálculo de XP, niveles, logros desbloqueados y posición en el ranking.
class GamificationService {
  // ===========================================================================
  // CÁLCULO DE XP
  // ===========================================================================

  /// Calcula la XP ganada por un avistamiento.
  ///
  /// [rarity] - Rareza del pez: 'common', 'uncommon', 'rare', 'legendary'
  /// [isNew] - Si es la primera vez que se ve este pez individual
  ///
  /// Retorna la cantidad de XP ganada
  int calculateXP(String rarity, bool isNew) {
    // XP base según rareza
    int baseXP;
    switch (rarity.toLowerCase()) {
      case 'common':
        baseXP = AppConstants.xpBaseCommon;
        break;
      case 'uncommon':
        baseXP = AppConstants.xpBaseUncommon;
        break;
      case 'rare':
        baseXP = AppConstants.xpBaseRare;
        break;
      case 'legendary':
        baseXP = AppConstants.xpBaseLegendary;
        break;
      default:
        // Si la rareza no es reconocida, usar XP de common
        baseXP = AppConstants.xpBaseCommon;
    }

    // Bonus por pez nuevo (primera vez que se identifica)
    final newBonus = isNew ? AppConstants.xpNewFishBonus : 0;

    return baseXP + newBonus;
  }

  // ===========================================================================
  // CÁLCULO DE NIVEL
  // ===========================================================================

  /// Calcula el nivel actual basado en la XP total acumulada.
  ///
  /// Fórmula: XP necesaria para nivel N = 100 * N^1.5
  /// El nivel se determina encontrando el mayor N donde la XP acumulada
  /// supera la suma de XP necesaria para todos los niveles hasta N.
  ///
  /// [totalXP] - XP total acumulada por el usuario
  ///
  /// Retorna el nivel actual (mínimo 1)
  int calculateLevel(int totalXP) {
    if (totalXP <= 0) return 1;

    int level = 1;
    int xpAccumulated = 0;

    // Iterar hasta encontrar el nivel donde la XP no alcanza
    while (true) {
      final xpNeeded = _xpRequiredForLevel(level + 1);
      if (xpAccumulated + xpNeeded > totalXP) break;
      xpAccumulated += xpNeeded;
      level++;
    }

    return level;
  }

  /// Calcula la XP necesaria para alcanzar el siguiente nivel.
  ///
  /// [currentLevel] - Nivel actual del usuario
  ///
  /// Retorna la XP total necesaria para pasar de currentLevel a currentLevel+1
  int xpForNextLevel(int currentLevel) {
    return _xpRequiredForLevel(currentLevel + 1);
  }

  /// Calcula la XP que le falta al usuario para el siguiente nivel.
  ///
  /// [totalXP] - XP total del usuario
  /// [currentLevel] - Nivel actual
  ///
  /// Retorna la XP restante para subir de nivel
  int xpRemainingForNextLevel(int totalXP, int currentLevel) {
    // Calcular XP total necesaria hasta el nivel actual
    int xpUsed = 0;
    for (int i = 2; i <= currentLevel; i++) {
      xpUsed += _xpRequiredForLevel(i);
    }

    // XP que el usuario tiene dentro del nivel actual
    final xpInCurrentLevel = totalXP - xpUsed;

    // XP necesaria para el siguiente nivel
    final xpNeeded = _xpRequiredForLevel(currentLevel + 1);

    return xpNeeded - xpInCurrentLevel;
  }

  /// Calcula el progreso porcentual dentro del nivel actual (0.0 a 1.0)
  double levelProgress(int totalXP, int currentLevel) {
    // XP total acumulada hasta el inicio del nivel actual
    int xpUsed = 0;
    for (int i = 2; i <= currentLevel; i++) {
      xpUsed += _xpRequiredForLevel(i);
    }

    final xpInCurrentLevel = totalXP - xpUsed;
    final xpNeeded = _xpRequiredForLevel(currentLevel + 1);

    if (xpNeeded <= 0) return 1.0;
    return (xpInCurrentLevel / xpNeeded).clamp(0.0, 1.0);
  }

  /// Fórmula interna: XP requerida para alcanzar un nivel específico
  /// XP = baseXP * level^factor
  int _xpRequiredForLevel(int level) {
    return (AppConstants.xpBaseForLevel * pow(level, AppConstants.xpLevelFactor))
        .round();
  }

  // ===========================================================================
  // VERIFICACIÓN DE LOGROS
  // ===========================================================================

  /// Verifica qué logros ha desbloqueado el usuario basándose en sus estadísticas.
  ///
  /// [userStats] - Mapa con las estadísticas del usuario:
  ///   - 'total_sightings': int - Total de avistamientos registrados
  ///   - 'unique_species': int - Número de especies únicas identificadas
  ///   - 'total_xp': int - XP total acumulada
  ///   - 'level': int - Nivel actual
  ///   - 'rare_fish_count': int - Número de peces raros identificados
  ///   - 'legendary_fish_count': int - Número de peces legendarios
  ///   - 'spots_visited': int - Spots de pesca diferentes visitados
  ///   - 'days_streak': int - Días consecutivos con avistamientos
  ///   - 'fish_re_sighted': int - Peces que ha visto más de una vez
  ///   - 'already_unlocked': List<String> - IDs de logros ya desbloqueados
  ///
  /// Retorna una lista de IDs de logros que se acaban de desbloquear
  List<String> checkAchievements(Map<String, dynamic> userStats) {
    final totalSightings = userStats['total_sightings'] as int? ?? 0;
    final uniqueSpecies = userStats['unique_species'] as int? ?? 0;
    final totalXP = userStats['total_xp'] as int? ?? 0;
    final level = userStats['level'] as int? ?? 1;
    final rareFishCount = userStats['rare_fish_count'] as int? ?? 0;
    final legendaryFishCount = userStats['legendary_fish_count'] as int? ?? 0;
    final spotsVisited = userStats['spots_visited'] as int? ?? 0;
    final daysStreak = userStats['days_streak'] as int? ?? 0;
    final fishReSighted = userStats['fish_re_sighted'] as int? ?? 0;

    // Logros ya desbloqueados (para no duplicar)
    final alreadyUnlocked =
        (userStats['already_unlocked'] as List<dynamic>?)?.cast<String>() ?? [];

    final newlyUnlocked = <String>[];

    // Definición de criterios de logros
    final achievementCriteria = <String, bool>{
      // --- Logros de avistamientos ---
      'first_catch': totalSightings >= 1,
      'ten_catches': totalSightings >= 10,
      'fifty_catches': totalSightings >= 50,
      'hundred_catches': totalSightings >= 100,
      'five_hundred_catches': totalSightings >= 500,

      // --- Logros de especies ---
      'species_collector_5': uniqueSpecies >= 5,
      'species_collector_10': uniqueSpecies >= 10,
      'species_collector_25': uniqueSpecies >= 25,
      'species_collector_50': uniqueSpecies >= 50,
      'species_master': uniqueSpecies >= 100,

      // --- Logros de rareza ---
      'rare_finder': rareFishCount >= 1,
      'rare_hunter': rareFishCount >= 5,
      'rare_master': rareFishCount >= 20,
      'legendary_encounter': legendaryFishCount >= 1,
      'legendary_collector': legendaryFishCount >= 5,

      // --- Logros de nivel ---
      'level_5': level >= 5,
      'level_10': level >= 10,
      'level_25': level >= 25,
      'level_50': level >= 50,

      // --- Logros de exploración ---
      'explorer_3': spotsVisited >= 3,
      'explorer_10': spotsVisited >= 10,
      'explorer_25': spotsVisited >= 25,

      // --- Logros de constancia ---
      'streak_3': daysStreak >= 3,
      'streak_7': daysStreak >= 7,
      'streak_30': daysStreak >= 30,

      // --- Logros de re-avistamiento ---
      'old_friend': fishReSighted >= 1,
      'fish_tracker': fishReSighted >= 5,
      'fish_stalker': fishReSighted >= 20,

      // --- Logros de XP ---
      'xp_1000': totalXP >= 1000,
      'xp_5000': totalXP >= 5000,
      'xp_10000': totalXP >= 10000,
    };

    // Verificar cuáles son nuevos
    for (final entry in achievementCriteria.entries) {
      if (entry.value && !alreadyUnlocked.contains(entry.key)) {
        newlyUnlocked.add(entry.key);
      }
    }

    return newlyUnlocked;
  }

  // ===========================================================================
  // POSICIÓN EN EL RANKING
  // ===========================================================================

  /// Calcula la posición del usuario en el leaderboard basándose en XP.
  ///
  /// [userXP] - XP total del usuario
  /// [allUsersXP] - Lista de XP de todos los usuarios (ya ordenada desc)
  ///
  /// Retorna la posición (1-indexed)
  int calculateLeaderboardPosition(int userXP, List<int> allUsersXP) {
    // Ordenar descendente si no está ordenado
    final sorted = List<int>.from(allUsersXP)..sort((a, b) => b.compareTo(a));

    // Encontrar la posición del usuario
    for (int i = 0; i < sorted.length; i++) {
      if (sorted[i] <= userXP) {
        return i + 1;
      }
    }

    // Si la XP del usuario es menor que todos, está al final
    return sorted.length + 1;
  }

  /// Obtener los datos del logro por su ID (nombre y descripción)
  Map<String, String> getAchievementInfo(String achievementId) {
    return _achievementDetails[achievementId] ??
        {'name': achievementId, 'description': 'Logro desbloqueado'};
  }

  /// Base de datos estática con información de logros
  static final Map<String, Map<String, String>> _achievementDetails = {
    'first_catch': {
      'name': 'Primera Captura',
      'description': 'Identifica tu primer pez',
    },
    'ten_catches': {
      'name': 'Pescador Novato',
      'description': 'Registra 10 avistamientos',
    },
    'fifty_catches': {
      'name': 'Pescador Experimentado',
      'description': 'Registra 50 avistamientos',
    },
    'hundred_catches': {
      'name': 'Pescador Experto',
      'description': 'Registra 100 avistamientos',
    },
    'five_hundred_catches': {
      'name': 'Maestro Pescador',
      'description': 'Registra 500 avistamientos',
    },
    'species_collector_5': {
      'name': 'Coleccionista Principiante',
      'description': 'Identifica 5 especies diferentes',
    },
    'species_collector_10': {
      'name': 'Coleccionista',
      'description': 'Identifica 10 especies diferentes',
    },
    'species_collector_25': {
      'name': 'Gran Coleccionista',
      'description': 'Identifica 25 especies diferentes',
    },
    'species_collector_50': {
      'name': 'Coleccionista Maestro',
      'description': 'Identifica 50 especies diferentes',
    },
    'species_master': {
      'name': 'Enciclopedia Viviente',
      'description': 'Identifica 100 especies diferentes',
    },
    'rare_finder': {
      'name': 'Buscador de Rarezas',
      'description': 'Encuentra tu primer pez raro',
    },
    'rare_hunter': {
      'name': 'Cazador de Rarezas',
      'description': 'Encuentra 5 peces raros',
    },
    'rare_master': {
      'name': 'Maestro de Rarezas',
      'description': 'Encuentra 20 peces raros',
    },
    'legendary_encounter': {
      'name': 'Encuentro Legendario',
      'description': 'Encuentra tu primer pez legendario',
    },
    'legendary_collector': {
      'name': 'Coleccionista Legendario',
      'description': 'Encuentra 5 peces legendarios',
    },
    'level_5': {
      'name': 'Nivel 5',
      'description': 'Alcanza el nivel 5',
    },
    'level_10': {
      'name': 'Nivel 10',
      'description': 'Alcanza el nivel 10',
    },
    'level_25': {
      'name': 'Nivel 25',
      'description': 'Alcanza el nivel 25',
    },
    'level_50': {
      'name': 'Nivel 50',
      'description': 'Alcanza el nivel 50',
    },
    'explorer_3': {
      'name': 'Explorador',
      'description': 'Visita 3 spots de pesca diferentes',
    },
    'explorer_10': {
      'name': 'Gran Explorador',
      'description': 'Visita 10 spots de pesca diferentes',
    },
    'explorer_25': {
      'name': 'Explorador Legendario',
      'description': 'Visita 25 spots de pesca diferentes',
    },
    'streak_3': {
      'name': 'Constante',
      'description': '3 días consecutivos de avistamientos',
    },
    'streak_7': {
      'name': 'Dedicado',
      'description': '7 días consecutivos de avistamientos',
    },
    'streak_30': {
      'name': 'Imparable',
      'description': '30 días consecutivos de avistamientos',
    },
    'old_friend': {
      'name': 'Viejo Amigo',
      'description': 'Re-avista un pez que ya habías visto',
    },
    'fish_tracker': {
      'name': 'Rastreador',
      'description': 'Re-avista 5 peces diferentes',
    },
    'fish_stalker': {
      'name': 'Seguidor Experto',
      'description': 'Re-avista 20 peces diferentes',
    },
    'xp_1000': {
      'name': 'Mil Puntos',
      'description': 'Acumula 1,000 XP',
    },
    'xp_5000': {
      'name': 'Cinco Mil',
      'description': 'Acumula 5,000 XP',
    },
    'xp_10000': {
      'name': 'Diez Mil',
      'description': 'Acumula 10,000 XP',
    },
  };
}
