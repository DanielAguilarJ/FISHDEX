import 'dart:convert';
import 'dart:math';
import 'package:appwrite/appwrite.dart';
import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';
import '../../core/constants/app_constants.dart';
import '../../core/enums/user_role.dart';
import '../models/fish_capture.dart';
import '../services/gamification_service.dart';

// =============================================================================
// REPOSITORIO DE CAPTURAS CON FISH_ID MATCHING
// =============================================================================

/// Repositorio que gestiona las capturas de peces con lógica de:
/// - Matching de fish_id por proximidad (5km) y especie
/// - Filtrado de datos según rol del usuario
/// - Guardado completo con datos manuales y de IA
class CapturesRepository {
  final Databases _databases;
  final Functions _functions;
  final GamificationService _gamificationService;

  CapturesRepository({
    required Databases databases,
    required Functions functions,
    GamificationService? gamificationService,
  })  : _databases = databases,
        _functions = functions,
        _gamificationService = gamificationService ?? GamificationService();

  // ===========================================================================
  // MATCHING DE FISH_ID
  // ===========================================================================

  /// Busca un fish_id existente que coincida por especie y proximidad (5km).
  /// Si no encuentra coincidencia, genera un nuevo UUID.
  ///
  /// Intenta usar la Cloud Function `match-fish-id` primero.
  /// Si falla (función no deployada), hace el cálculo localmente.
  Future<FishMatchResult> matchOrCreateFishId({
    required String species,
    required double latitude,
    required double longitude,
  }) async {
    try {
      // Intentar llamar la Cloud Function
      final execution = await _functions.createExecution(
        functionId: AppConstants.matchFishIdFunctionId,
        body: json.encode({
          'species': species,
          'latitude': latitude,
          'longitude': longitude,
        }),
      );

      if (execution.responseStatusCode == 200) {
        final result = json.decode(execution.responseBody) as Map<String, dynamic>;
        return FishMatchResult(
          fishId: result['fish_id'] as String,
          isNewFish: result['is_new'] as bool? ?? true,
          matchDistance: (result['distance'] as num?)?.toDouble(),
        );
      }
    } catch (e) {
      debugPrint('⚠️ Cloud Function match-fish-id no disponible, usando fallback local: $e');
    }

    // Fallback: matching local
    return _localFishIdMatching(species, latitude, longitude);
  }

  /// Matching local de fish_id (cuando la Cloud Function no está disponible)
  Future<FishMatchResult> _localFishIdMatching(
    String species,
    double latitude,
    double longitude,
  ) async {
    try {
      // Buscar peces de la misma especie
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishIndividualsCollection,
        queries: [
          Query.equal('species', species),
          Query.limit(100),
        ],
      );

      if (response.documents.isEmpty) {
        return FishMatchResult(
          fishId: const Uuid().v4(),
          isNewFish: true,
        );
      }

      // Calcular distancia Haversine para cada match
      for (final doc in response.documents) {
        final fishLat = (doc.data['last_latitude'] as num?)?.toDouble() ??
            (doc.data['first_latitude'] as num?)?.toDouble();
        final fishLng = (doc.data['last_longitude'] as num?)?.toDouble() ??
            (doc.data['first_longitude'] as num?)?.toDouble();

        if (fishLat == null || fishLng == null) continue;

        final distance = _calculateHaversineDistance(
          latitude, longitude, fishLat, fishLng,
        );

        if (distance <= AppConstants.fishMatchRadiusMeters) {
          return FishMatchResult(
            fishId: doc.$id,
            isNewFish: false,
            matchDistance: distance,
          );
        }
      }

      // No hay match en 5km
      return FishMatchResult(
        fishId: const Uuid().v4(),
        isNewFish: true,
      );
    } catch (e) {
      debugPrint('⚠️ Error en matching local, generando nuevo ID: $e');
      return FishMatchResult(
        fishId: const Uuid().v4(),
        isNewFish: true,
      );
    }
  }

  // ===========================================================================
  // GUARDAR CAPTURA COMPLETA
  // ===========================================================================

  /// Guarda una captura completa (datos IA + manuales) en la base de datos.
  /// Actualiza fish_individuals, stats del usuario, y fishing spots.
  Future<CaptureResult> saveCapture(FishCapture capture) async {
    try {
      // Guardar el documento de captura
      final doc = await _databases.createDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        documentId: ID.unique(),
        data: capture.toMap(),
      );

      // Actualizar el pez individual
      await _updateFishIndividual(capture);

      // Actualizar stats del usuario
      await _updateUserStats(capture);

      return CaptureResult(
        success: true,
        captureId: doc.$id,
        fishId: capture.fishId,
        xpEarned: capture.xpEarned,
        isNewFish: capture.isNewFish,
      );
    } catch (e) {
      debugPrint('⚠️ Error al guardar captura: $e');
      return CaptureResult(
        success: false,
        captureId: null,
        fishId: capture.fishId,
        xpEarned: 0,
        isNewFish: capture.isNewFish,
        errorMessage: 'Error al guardar la captura: $e',
      );
    }
  }

  /// Actualiza o crea el registro del pez individual
  Future<void> _updateFishIndividual(FishCapture capture) async {
    try {
      if (capture.isNewFish) {
        await _databases.createDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishIndividualsCollection,
          documentId: capture.fishId,
          data: {
            'species': capture.species,
            'scientific_name': capture.scientificName,
            'family': capture.family,
            'rarity': capture.rarity,
            'first_seen_date': capture.capturedAt.toIso8601String(),
            'last_seen_date': capture.capturedAt.toIso8601String(),
            'first_seen_by': capture.userId,
            'total_sightings': 1,
            'estimated_size_cm': capture.lengthCm,
            'first_latitude': capture.latitude,
            'first_longitude': capture.longitude,
            'last_latitude': capture.latitude,
            'last_longitude': capture.longitude,
          },
        );
      } else {
        // Actualizar registro existente
        try {
          final existing = await _databases.getDocument(
            databaseId: AppConstants.databaseId,
            collectionId: AppConstants.fishIndividualsCollection,
            documentId: capture.fishId,
          );
          final sightings = (existing.data['total_sightings'] as num?)?.toInt() ?? 0;

          await _databases.updateDocument(
            databaseId: AppConstants.databaseId,
            collectionId: AppConstants.fishIndividualsCollection,
            documentId: capture.fishId,
            data: {
              'last_seen_date': capture.capturedAt.toIso8601String(),
              'total_sightings': sightings + 1,
              if (capture.lengthCm != null)
                'estimated_size_cm': capture.lengthCm,
              'last_latitude': capture.latitude,
              'last_longitude': capture.longitude,
            },
          );
        } catch (_) {}
      }
    } catch (e) {
      debugPrint('⚠️ Error al actualizar fish_individual: $e');
    }
  }

  /// Actualiza las estadísticas del usuario
  Future<void> _updateUserStats(FishCapture capture) async {
    try {
      final userDoc = await _databases.getDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: capture.userId,
      );

      final currentXP = (userDoc.data['total_xp'] as num?)?.toInt() ?? 0;
      final currentSightings =
          (userDoc.data['total_sightings'] as num?)?.toInt() ?? 0;
      final currentUnique =
          (userDoc.data['unique_species'] as num?)?.toInt() ?? 0;
      final currentRare =
          (userDoc.data['rare_fish_count'] as num?)?.toInt() ?? 0;
      final currentLegendary =
          (userDoc.data['legendary_fish_count'] as num?)?.toInt() ?? 0;

      final newXP = currentXP + capture.xpEarned;
      final newLevel = _gamificationService.calculateLevel(newXP);

      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: capture.userId,
        data: {
          'total_xp': newXP,
          'level': newLevel,
          'total_sightings': currentSightings + 1,
          'unique_species':
              capture.isNewFish ? currentUnique + 1 : currentUnique,
          'rare_fish_count':
              capture.rarity == 'rare' ? currentRare + 1 : currentRare,
          'legendary_fish_count': capture.rarity == 'legendary'
              ? currentLegendary + 1
              : currentLegendary,
          'last_activity': DateTime.now().toIso8601String(),
        },
      );
    } catch (e) {
      debugPrint('⚠️ Error al actualizar stats del usuario: $e');
    }
  }

  // ===========================================================================
  // CONSULTAS FILTRADAS POR ROL
  // ===========================================================================

  /// Obtiene las capturas filtradas según el rol del usuario.
  /// - Fisherman: solo sus propias capturas + indicadores anónimos
  /// - Researcher/Admin: todas las capturas con datos completos
  Future<List<FishCapture>> getCapturesForUser({
    required String userId,
    required UserRole role,
    int limit = 50,
    int offset = 0,
  }) async {
    try {
      if (role == UserRole.fisherman) {
        return _getFishermanCaptures(userId, limit, offset);
      } else {
        return _getAllCaptures(limit, offset);
      }
    } catch (e) {
      debugPrint('⚠️ Error obteniendo capturas: $e');
      return [];
    }
  }

  /// Capturas solo del fisherman actual
  Future<List<FishCapture>> _getFishermanCaptures(
    String userId,
    int limit,
    int offset,
  ) async {
    final response = await _databases.listDocuments(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.fishSightingsCollection,
      queries: [
        Query.equal('user_id', userId),
        Query.orderDesc('captured_at'),
        Query.limit(limit),
        Query.offset(offset),
      ],
    );

    return response.documents
        .map((doc) => FishCapture.fromMap(doc.data))
        .toList();
  }

  /// Todas las capturas (para researcher/admin)
  Future<List<FishCapture>> _getAllCaptures(int limit, int offset) async {
    final response = await _databases.listDocuments(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.fishSightingsCollection,
      queries: [
        Query.orderDesc('captured_at'),
        Query.limit(limit),
        Query.offset(offset),
      ],
    );

    return response.documents
        .map((doc) => FishCapture.fromMap(doc.data))
        .toList();
  }

  /// Verifica si un fish_id ya fue registrado por otros usuarios
  /// (para mostrar markers anónimos al fisherman)
  Future<List<String>> getOtherUsersFishIds(String userId) async {
    try {
      // Obtener fish_ids del usuario actual
      final myCaptures = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        queries: [
          Query.equal('user_id', userId),
          Query.limit(500),
        ],
      );

      final myFishIds = myCaptures.documents
          .map((doc) => doc.data['fish_id'] as String)
          .toSet();

      if (myFishIds.isEmpty) return [];

      // Para cada fish_id mío, ver si hay capturas de otros
      final othersFishIds = <String>[];
      for (final fishId in myFishIds) {
        final others = await _databases.listDocuments(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishSightingsCollection,
          queries: [
            Query.equal('fish_id', fishId),
            Query.notEqual('user_id', userId),
            Query.limit(1),
          ],
        );
        if (others.documents.isNotEmpty) {
          othersFishIds.add(fishId);
        }
      }

      return othersFishIds;
    } catch (e) {
      debugPrint('⚠️ Error buscando fish_ids de otros: $e');
      return [];
    }
  }

  /// Obtiene el historial completo de un fish_id (solo researcher/admin)
  Future<List<FishCapture>> getFishHistory(String fishId) async {
    try {
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        queries: [
          Query.equal('fish_id', fishId),
          Query.orderDesc('captured_at'),
        ],
      );

      return response.documents
          .map((doc) => FishCapture.fromMap(doc.data))
          .toList();
    } catch (e) {
      debugPrint('⚠️ Error obteniendo historial del pez: $e');
      return [];
    }
  }

  // ===========================================================================
  // EDITAR CAPTURA
  // ===========================================================================

  /// Actualiza una captura existente con datos adicionales
  Future<bool> updateCapture({
    required String captureId,
    required String userId,
    Map<String, dynamic>? updates,
  }) async {
    try {
      // Verificar que el capture pertenece al usuario
      final doc = await _databases.getDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        documentId: captureId,
      );

      if (doc.data['user_id'] != userId) {
        return false; // No puede editar capturas de otros
      }

      if (updates != null && updates.isNotEmpty) {
        await _databases.updateDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishSightingsCollection,
          documentId: captureId,
          data: updates,
        );
      }

      return true;
    } catch (e) {
      debugPrint('⚠️ Error al actualizar captura: $e');
      return false;
    }
  }

  // ===========================================================================
  // UTILIDAD - HAVERSINE
  // ===========================================================================

  /// Calcula distancia en metros entre dos puntos usando Haversine
  double _calculateHaversineDistance(
    double lat1, double lon1,
    double lat2, double lon2,
  ) {
    const double earthRadius = 6371000; // metros
    final dLat = _degreesToRadians(lat2 - lat1);
    final dLon = _degreesToRadians(lon2 - lon1);

    final a = sin(dLat / 2) * sin(dLat / 2) +
        cos(_degreesToRadians(lat1)) *
            cos(_degreesToRadians(lat2)) *
            sin(dLon / 2) *
            sin(dLon / 2);

    final c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }

  double _degreesToRadians(double degrees) => degrees * pi / 180;
}

// =============================================================================
// MODELOS DE RESULTADO
// =============================================================================

/// Resultado del matching de fish_id
class FishMatchResult {
  final String fishId;
  final bool isNewFish;
  final double? matchDistance;

  const FishMatchResult({
    required this.fishId,
    required this.isNewFish,
    this.matchDistance,
  });
}

/// Resultado de guardar una captura
class CaptureResult {
  final bool success;
  final String? captureId;
  final String fishId;
  final int xpEarned;
  final bool isNewFish;
  final String? errorMessage;

  const CaptureResult({
    required this.success,
    this.captureId,
    required this.fishId,
    required this.xpEarned,
    required this.isNewFish,
    this.errorMessage,
  });
}
