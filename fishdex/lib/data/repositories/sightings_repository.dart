import 'package:appwrite/appwrite.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../../core/constants/app_constants.dart';
import '../services/gamification_service.dart';

// =============================================================================
// REPOSITORIO DE AVISTAMIENTOS
// =============================================================================

/// Repositorio que gestiona los avistamientos de peces.
/// Guarda en Appwrite cuando hay conexión, o localmente si no hay.
/// Actualiza las colecciones relacionadas: fish_individuals, user stats, fishing_spots.
class SightingsRepository {
  final dynamic _databases;
  final GamificationService _gamificationService;

  SightingsRepository({
    required dynamic databases,
    GamificationService? gamificationService,
  })  : _databases = databases,
        _gamificationService = gamificationService ?? GamificationService();

  // ===========================================================================
  // GUARDAR AVISTAMIENTO
  // ===========================================================================

  /// Guardar un nuevo avistamiento completo.
  /// Intenta guardar en Appwrite; si falla, guarda localmente para sincronizar después.
  ///
  /// [userId] - ID del usuario que registra el avistamiento
  /// [fishId] - ID único del pez individual
  /// [species] - Nombre de la especie identificada
  /// [rarity] - Rareza del pez: 'common', 'uncommon', 'rare', 'legendary'
  /// [confidence] - Confianza de la identificación (0.0 a 1.0)
  /// [isNew] - Si es la primera vez que se ve este pez individual
  /// [estimatedSizeCm] - Tamaño estimado en centímetros
  /// [latitude] - Latitud GPS del avistamiento
  /// [longitude] - Longitud GPS del avistamiento
  /// [videoFileId] - ID del video subido al storage (opcional)
  /// [photoFileId] - ID de la foto subida al storage (opcional)
  /// [spotId] - ID del spot de pesca asociado (opcional)
  ///
  /// Retorna un [SightingResult] con el resultado de la operación
  Future<SightingResult> saveSighting({
    required String userId,
    required String fishId,
    required String species,
    required String rarity,
    required double confidence,
    required bool isNew,
    required double estimatedSizeCm,
    double? latitude,
    double? longitude,
    String? videoFileId,
    String? photoFileId,
    String? spotId,
  }) async {
    // Calcular XP ganada
    final xpEarned = _gamificationService.calculateXP(rarity, isNew);
    final now = DateTime.now().toIso8601String();

    // Datos del avistamiento
    final sightingData = {
      'user_id': userId,
      'fish_id': fishId,
      'species': species,
      'rarity': rarity,
      'confidence': confidence,
      'is_new': isNew,
      'estimated_size_cm': estimatedSizeCm,
      'latitude': latitude,
      'longitude': longitude,
      'video_file_id': videoFileId,
      'photo_file_id': photoFileId,
      'spot_id': spotId,
      'xp_earned': xpEarned,
      'created_at': now,
    };

    try {
      // Intentar guardar en Appwrite
      final sightingDoc = await _databases.createDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        documentId: ID.unique(),
        data: sightingData,
      );

      // Actualizar el pez individual en paralelo
      await _updateFishIndividual(
        fishId: fishId,
        species: species,
        rarity: rarity,
        isNew: isNew,
        estimatedSizeCm: estimatedSizeCm,
        userId: userId,
        latitude: latitude,
        longitude: longitude,
        timestamp: now,
      );

      // Actualizar XP y estadísticas del usuario
      await _updateUserStats(
        userId: userId,
        xpEarned: xpEarned,
        isNewFish: isNew,
        rarity: rarity,
      );

      // Actualizar el spot de pesca si se proporcionó uno
      if (spotId != null) {
        await _updateFishingSpot(
          spotId: spotId,
          species: species,
          rarity: rarity,
          photoFileId: photoFileId,
        );
      }

      return SightingResult(
        success: true,
        savedOnline: true,
        sightingId: sightingDoc.$id,
        xpEarned: xpEarned,
      );
    } catch (e) {
      // Si falla la conexión, guardar localmente
      await _saveLocally(sightingData);

      return SightingResult(
        success: true,
        savedOnline: false,
        sightingId: null,
        xpEarned: xpEarned,
        offlineMessage: 'Guardado localmente. Se sincronizará al reconectar.',
      );
    }
  }

  // ===========================================================================
  // ACTUALIZAR PEZ INDIVIDUAL
  // ===========================================================================

  /// Actualiza o crea el registro del pez individual en la colección fish_individuals
  Future<void> _updateFishIndividual({
    required String fishId,
    required String species,
    required String rarity,
    required bool isNew,
    required double estimatedSizeCm,
    required String userId,
    double? latitude,
    double? longitude,
    required String timestamp,
  }) async {
    try {
      if (isNew) {
        // Crear nuevo registro de pez individual
        await _databases.createDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishIndividualsCollection,
          documentId: fishId,
          data: {
            'species': species,
            'rarity': rarity,
            'first_seen_date': timestamp,
            'last_seen_date': timestamp,
            'first_seen_by': userId,
            'total_sightings': 1,
            'estimated_size_cm': estimatedSizeCm,
            'first_latitude': latitude,
            'first_longitude': longitude,
            'last_latitude': latitude,
            'last_longitude': longitude,
          },
        );
      } else {
        // Actualizar registro existente
        final existingDoc = await _databases.getDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishIndividualsCollection,
          documentId: fishId,
        );

        final currentSightings = existingDoc.data['total_sightings'] ?? 0;

        await _databases.updateDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishIndividualsCollection,
          documentId: fishId,
          data: {
            'last_seen_date': timestamp,
            'total_sightings': currentSightings + 1,
            'estimated_size_cm': estimatedSizeCm,
            'last_latitude': latitude,
            'last_longitude': longitude,
          },
        );
      }
    } catch (e) {
      // Error al actualizar pez individual - no interrumpir el flujo principal
    }
  }

  // ===========================================================================
  // ACTUALIZAR ESTADÍSTICAS DEL USUARIO
  // ===========================================================================

  /// Actualiza la XP y estadísticas del usuario en la colección users
  Future<void> _updateUserStats({
    required String userId,
    required int xpEarned,
    required bool isNewFish,
    required String rarity,
  }) async {
    try {
      // Obtener datos actuales del usuario
      final userDoc = await _databases.getDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: userId,
      );

      final currentXP = userDoc.data['total_xp'] as int? ?? 0;
      final currentSightings = userDoc.data['total_sightings'] as int? ?? 0;
      final currentUniqueSpecies =
          userDoc.data['unique_species'] as int? ?? 0;
      final currentRareCount = userDoc.data['rare_fish_count'] as int? ?? 0;
      final currentLegendaryCount =
          userDoc.data['legendary_fish_count'] as int? ?? 0;

      // Calcular nuevos valores
      final newXP = currentXP + xpEarned;
      final newLevel = _gamificationService.calculateLevel(newXP);
      final newSightings = currentSightings + 1;
      final newUniqueSpecies =
          isNewFish ? currentUniqueSpecies + 1 : currentUniqueSpecies;

      // Actualizar contadores de rareza
      int newRareCount = currentRareCount;
      int newLegendaryCount = currentLegendaryCount;
      if (rarity == 'rare') newRareCount++;
      if (rarity == 'legendary') newLegendaryCount++;

      // Guardar actualizaciones
      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: userId,
        data: {
          'total_xp': newXP,
          'level': newLevel,
          'total_sightings': newSightings,
          'unique_species': newUniqueSpecies,
          'rare_fish_count': newRareCount,
          'legendary_fish_count': newLegendaryCount,
          'last_activity': DateTime.now().toIso8601String(),
        },
      );

      // Actualizar posición en el leaderboard
      await _updateLeaderboard(userId: userId, newXP: newXP, newLevel: newLevel);
    } catch (e) {
      // Error al actualizar stats del usuario - no interrumpir flujo principal
    }
  }

  // ===========================================================================
  // ACTUALIZAR SPOT DE PESCA
  // ===========================================================================

  /// Actualiza el spot de pesca con la nueva captura
  Future<void> _updateFishingSpot({
    required String spotId,
    required String species,
    required String rarity,
    String? photoFileId,
  }) async {
    try {
      final spotDoc = await _databases.getDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishingSpotsCollection,
        documentId: spotId,
      );

      final currentCatches = spotDoc.data['total_catches'] as int? ?? 0;
      final hasRareFish = spotDoc.data['has_rare_fish'] as bool? ?? false;

      // Actualizar si el pez es raro o legendario
      final isRareOrBetter =
          rarity == 'rare' || rarity == 'legendary';

      final updateData = <String, dynamic>{
        'total_catches': currentCatches + 1,
        'last_catch_date': DateTime.now().toIso8601String(),
      };

      // Marcar como spot con peces raros si aplica
      if (isRareOrBetter && !hasRareFish) {
        updateData['has_rare_fish'] = true;
      }

      // Actualizar foto de última captura si se proporcionó
      if (photoFileId != null) {
        updateData['last_catch_photo'] = photoFileId;
      }

      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishingSpotsCollection,
        documentId: spotId,
        data: updateData,
      );
    } catch (e) {
      // Error al actualizar fishing spot - no interrumpir flujo principal
    }
  }

  // ===========================================================================
  // CREAR SPOT DE PESCA
  // ===========================================================================

  /// Crea un nuevo spot de pesca a partir de un avistamiento
  Future<String?> createFishingSpotFromSighting({
    required String name,
    required double latitude,
    required double longitude,
    required String waterType,
    required String createdBy,
    String? species,
    String? description,
  }) async {
    try {
      final doc = await _databases.createDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishingSpotsCollection,
        documentId: ID.unique(),
        data: {
          'name': name,
          'latitude': latitude,
          'longitude': longitude,
          'water_type': waterType,
          'total_catches': 1,
          'common_species': species != null ? '["$species"]' : '[]',
          'has_rare_fish': false,
          'created_by': createdBy,
          'description': description,
          'last_catch_date': DateTime.now().toIso8601String(),
        },
      );

      return doc.$id;
    } catch (e) {
      // Error al crear spot - retornar null
      return null;
    }
  }

  // ===========================================================================
  // ACTUALIZAR LEADERBOARD
  // ===========================================================================

  /// Actualiza o crea la entrada del usuario en el leaderboard
  Future<void> _updateLeaderboard({
    required String userId,
    required int newXP,
    required int newLevel,
  }) async {
    try {
      // Intentar actualizar la entrada existente del leaderboard
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.leaderboardsCollection,
        queries: [
          Query.equal('user_id', userId),
          Query.limit(1),
        ],
      );

      if (response.documents.isNotEmpty) {
        // Actualizar existente
        await _databases.updateDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.leaderboardsCollection,
          documentId: response.documents.first.$id,
          data: {
            'xp_total': newXP,
            'level': newLevel,
            'updated_at': DateTime.now().toIso8601String(),
          },
        );
      } else {
        // Crear nueva entrada
        await _databases.createDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.leaderboardsCollection,
          documentId: ID.unique(),
          data: {
            'user_id': userId,
            'xp_total': newXP,
            'level': newLevel,
            'updated_at': DateTime.now().toIso8601String(),
          },
        );
      }
    } catch (e) {
      // Error al actualizar leaderboard - no interrumpir flujo principal
    }
  }

  // ===========================================================================
  // ALMACENAMIENTO LOCAL (OFFLINE)
  // ===========================================================================

  /// Guardar avistamiento localmente para sincronización posterior
  Future<void> _saveLocally(Map<String, dynamic> sightingData) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final pendingList = prefs.getStringList('pending_sightings') ?? [];
      pendingList.add(json.encode(sightingData));
      await prefs.setStringList('pending_sightings', pendingList);
    } catch (e) {
      // Error al guardar localmente - datos perdidos
    }
  }

  /// Obtener avistamientos pendientes de sincronización
  Future<List<Map<String, dynamic>>> getPendingSightings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final pendingList = prefs.getStringList('pending_sightings') ?? [];
      return pendingList
          .map((s) => json.decode(s) as Map<String, dynamic>)
          .toList();
    } catch (e) {
      return [];
    }
  }

  /// Sincronizar avistamientos pendientes con el servidor
  /// Retorna el número de avistamientos sincronizados exitosamente
  Future<int> syncPendingSightings() async {
    int synced = 0;

    try {
      final prefs = await SharedPreferences.getInstance();
      final pendingList = prefs.getStringList('pending_sightings') ?? [];

      if (pendingList.isEmpty) return 0;

      final remaining = <String>[];

      for (final sightingJson in pendingList) {
        try {
          final data = json.decode(sightingJson) as Map<String, dynamic>;

          // Intentar subir al servidor
          await _databases.createDocument(
            databaseId: AppConstants.databaseId,
            collectionId: AppConstants.fishSightingsCollection,
            documentId: ID.unique(),
            data: data,
          );

          synced++;
        } catch (e) {
          // Este avistamiento no se pudo sincronizar, mantener para después
          remaining.add(sightingJson);
        }
      }

      // Actualizar la lista local con los que no se pudieron sincronizar
      await prefs.setStringList('pending_sightings', remaining);
    } catch (e) {
      // Error general en la sincronización
    }

    return synced;
  }

  /// Limpiar todos los avistamientos pendientes (usar con cuidado)
  Future<void> clearPendingSightings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('pending_sightings');
    } catch (e) {
      // Error al limpiar pendientes
    }
  }

  // ===========================================================================
  // CONSULTAS
  // ===========================================================================

  /// Obtener historial de avistamientos del usuario
  Future<List<Map<String, dynamic>>> getUserSightings(String userId,
      {int limit = 25, int offset = 0}) async {
    try {
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        queries: [
          Query.equal('user_id', userId),
          Query.orderDesc('created_at'),
          Query.limit(limit),
          Query.offset(offset),
        ],
      );

      return response.documents.map((doc) => doc.data).toList();
    } catch (e) {
      // Si falla, devolver lista vacía
      return [];
    }
  }

  /// Obtener todos los avistamientos de un pez individual
  Future<List<Map<String, dynamic>>> getFishSightings(String fishId) async {
    try {
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        queries: [
          Query.equal('fish_id', fishId),
          Query.orderDesc('created_at'),
        ],
      );

      return response.documents.map((doc) => doc.data).toList();
    } catch (e) {
      return [];
    }
  }

  /// Obtener estadísticas rápidas del usuario
  Future<Map<String, dynamic>> getUserStats(String userId) async {
    try {
      final userDoc = await _databases.getDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: userId,
      );
      return userDoc.data;
    } catch (e) {
      // Devolver stats vacías si no se puede conectar
      return {
        'total_xp': 0,
        'level': 1,
        'total_sightings': 0,
        'unique_species': 0,
        'rare_fish_count': 0,
        'legendary_fish_count': 0,
      };
    }
  }
}

// =============================================================================
// MODELO DE RESULTADO
// =============================================================================

/// Resultado de guardar un avistamiento
class SightingResult {
  /// Si la operación fue exitosa (incluyendo guardado offline)
  final bool success;

  /// Si se guardó en el servidor (true) o localmente (false)
  final bool savedOnline;

  /// ID del documento creado en Appwrite (null si se guardó offline)
  final String? sightingId;

  /// XP ganada por este avistamiento
  final int xpEarned;

  /// Mensaje informativo si se guardó offline
  final String? offlineMessage;

  const SightingResult({
    required this.success,
    required this.savedOnline,
    this.sightingId,
    required this.xpEarned,
    this.offlineMessage,
  });
}
