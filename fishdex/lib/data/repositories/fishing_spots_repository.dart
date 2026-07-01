import 'package:appwrite/appwrite.dart';
import '../../core/constants/app_constants.dart';
import '../../features/map/providers/map_providers.dart';

/// Repositorio de Fishing Spots - conecta con Appwrite Databases
class FishingSpotsRepository {
  final Databases _databases;

  FishingSpotsRepository({required Databases databases})
      : _databases = databases;

  /// Obtener todos los spots de pesca
  Future<List<FishingSpotData>> getAll() async {
    try {
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishingSpotsCollection,
      );

      return response.documents.map((doc) {
        final data = doc.data;
        return FishingSpotData(
          id: doc.$id,
          name: data['name'] ?? '',
          latitude: (data['latitude'] as num).toDouble(),
          longitude: (data['longitude'] as num).toDouble(),
          waterType: data['water_type'] ?? 'rio',
          totalCatches: data['total_catches'] ?? 0,
          commonSpecies: _parseSpecies(data['common_species']),
          hasRareFish: data['has_rare_fish'] ?? false,
          lastCatchPhoto: data['last_catch_photo'],
          lastCatchDate: data['last_catch_date'] != null
              ? DateTime.parse(data['last_catch_date'])
              : null,
          description: data['description'],
        );
      }).toList();
    } catch (e) {
      // Si falla (ej: Appwrite no configurado), devolver lista vacía
      return [];
    }
  }

  /// Obtener spots cercanos a una ubicación
  Future<List<FishingSpotData>> getNearby({
    required double latitude,
    required double longitude,
    double radiusKm = 50.0,
  }) async {
    // Appwrite no tiene consultas geoespaciales nativas,
    // así que filtramos por un bounding box aproximado
    final latDelta = radiusKm / 111.0; // ~111km por grado de latitud
    final lngDelta = radiusKm / (111.0 * 0.7); // Aproximación

    try {
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishingSpotsCollection,
        queries: [
          Query.greaterThan('latitude', latitude - latDelta),
          Query.lessThan('latitude', latitude + latDelta),
          Query.greaterThan('longitude', longitude - lngDelta),
          Query.lessThan('longitude', longitude + lngDelta),
        ],
      );

      return response.documents.map((doc) {
        final data = doc.data;
        return FishingSpotData(
          id: doc.$id,
          name: data['name'] ?? '',
          latitude: (data['latitude'] as num).toDouble(),
          longitude: (data['longitude'] as num).toDouble(),
          waterType: data['water_type'] ?? 'rio',
          totalCatches: data['total_catches'] ?? 0,
          commonSpecies: _parseSpecies(data['common_species']),
          hasRareFish: data['has_rare_fish'] ?? false,
          lastCatchPhoto: data['last_catch_photo'],
          lastCatchDate: data['last_catch_date'] != null
              ? DateTime.parse(data['last_catch_date'])
              : null,
          description: data['description'],
        );
      }).toList();
    } catch (e) {
      return [];
    }
  }

  /// Crear un nuevo spot de pesca
  Future<void> createSpot({
    required String name,
    required double latitude,
    required double longitude,
    required String waterType,
    required String createdBy,
    String? description,
  }) async {
    await _databases.createDocument(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.fishingSpotsCollection,
      documentId: ID.unique(),
      data: {
        'name': name,
        'latitude': latitude,
        'longitude': longitude,
        'water_type': waterType,
        'total_catches': 0,
        'common_species': '[]',
        'has_rare_fish': false,
        'created_by': createdBy,
        'description': description,
      },
    );
  }

  /// Actualizar conteo de capturas de un spot
  Future<void> incrementCatches(String spotId) async {
    final doc = await _databases.getDocument(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.fishingSpotsCollection,
      documentId: spotId,
    );
    
    final currentCatches = doc.data['total_catches'] ?? 0;
    
    await _databases.updateDocument(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.fishingSpotsCollection,
      documentId: spotId,
      data: {
        'total_catches': currentCatches + 1,
        'last_catch_date': DateTime.now().toIso8601String(),
      },
    );
  }

  List<String> _parseSpecies(dynamic speciesData) {
    if (speciesData == null) return [];
    if (speciesData is List) return speciesData.cast<String>();
    if (speciesData is String) {
      try {
        // Intentar parsear como JSON
        return (speciesData)
            .replaceAll('[', '')
            .replaceAll(']', '')
            .replaceAll('"', '')
            .split(',')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList();
      } catch (_) {
        return [];
      }
    }
    return [];
  }
}
