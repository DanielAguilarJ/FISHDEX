import 'dart:math';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/enums/user_role.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../data/repositories/captures_repository.dart';
import '../../../data/services/role_guard_service.dart';

// =============================================================================
// MODELO DE DATOS - Fishing Spot
// =============================================================================

/// Datos de un spot de pesca
class FishingSpotData {
  final String id;
  final String name;
  final double latitude;
  final double longitude;
  final String waterType;
  final int totalCatches;
  final List<String> commonSpecies;
  final bool hasRareFish;
  final String? lastCatchPhoto;
  final DateTime? lastCatchDate;
  final String? description;

  const FishingSpotData({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.waterType,
    required this.totalCatches,
    required this.commonSpecies,
    required this.hasRareFish,
    this.lastCatchPhoto,
    this.lastCatchDate,
    this.description,
  });
}

// =============================================================================
// PROVIDER DE UBICACIÓN DEL USUARIO
// =============================================================================

/// Provider que obtiene y actualiza la ubicación del usuario en tiempo real
final userLocationProvider = StreamProvider<LatLng?>((ref) async* {
  // Verificar permisos
  bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
  if (!serviceEnabled) {
    yield null;
    return;
  }

  LocationPermission permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
    if (permission == LocationPermission.denied) {
      yield null;
      return;
    }
  }

  if (permission == LocationPermission.deniedForever) {
    yield null;
    return;
  }

  // Obtener ubicación inicial
  try {
    final position = await Geolocator.getCurrentPosition(
      desiredAccuracy: LocationAccuracy.high,
    );
    yield LatLng(position.latitude, position.longitude);
  } catch (e) {
    yield null;
  }

  // Escuchar actualizaciones de ubicación
  yield* Geolocator.getPositionStream(
    locationSettings: const LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 10, // Actualizar cada 10 metros
    ),
  ).map((position) => LatLng(position.latitude, position.longitude));
});

// =============================================================================
// PROVIDER DE FISHING SPOTS
// =============================================================================

/// Provider que carga los fishing spots desde Appwrite.
/// Usa datos reales de la base de datos; si falla, devuelve spots de ejemplo.
final fishingSpotsProvider = FutureProvider<List<FishingSpotData>>((ref) async {
  try {
    final databases = ref.read(appwriteDatabasesProvider);
    final response = await databases.listDocuments(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.fishingSpotsCollection,
    );

    if (response.documents.isEmpty) return _generateMockSpots(ref);

    return response.documents.map((doc) {
      final data = doc.data;
      return FishingSpotData(
        id: doc.$id,
        name: data['name'] ?? '',
        latitude: (data['latitude'] as num).toDouble(),
        longitude: (data['longitude'] as num).toDouble(),
        waterType: data['water_type'] ?? 'rio',
        totalCatches: (data['total_catches'] as num?)?.toInt() ?? 0,
        commonSpecies: _parseSpecies(data['common_species']),
        hasRareFish: data['has_rare_fish'] ?? false,
        lastCatchPhoto: data['last_catch_photo'] as String?,
        lastCatchDate: data['last_catch_date'] != null
            ? DateTime.tryParse(data['last_catch_date'] as String)
            : null,
        description: data['description'] as String?,
      );
    }).toList();
  } catch (e) {
    // Si falla Appwrite (sin autenticación, red, etc.) devolver spots de ejemplo
    return _generateMockSpots(ref);
  }
});

/// Parsea el campo common_species que puede ser List o String JSON
List<String> _parseSpecies(dynamic data) {
  if (data == null) return [];
  if (data is List) return data.cast<String>();
  if (data is String) {
    return data
        .replaceAll('[', '')
        .replaceAll(']', '')
        .replaceAll('"', '')
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toList();
  }
  return [];
}

/// Genera spots de prueba cerca de la ubicación del usuario
List<FishingSpotData> _generateMockSpots(Ref ref) {
  // Obtener la ubicación actual del usuario para generar spots cercanos
  final userLocation = ref.read(userLocationProvider).valueOrNull;
  
  // Si no hay ubicación del usuario, no mostrar spots de ejemplo
  if (userLocation == null) return [];
  
  final baseLat = userLocation.latitude;
  final baseLng = userLocation.longitude;

  // Spots de ejemplo generados dinámicamente cerca de la ubicación del usuario
  final spots = <FishingSpotData>[
    FishingSpotData(
      id: 'spot_001',
      name: 'Embalse cercano',
      latitude: baseLat + 0.05,
      longitude: baseLng - 0.03,
      waterType: 'embalse',
      totalCatches: 47,
      commonSpecies: const ['Trucha Arcoíris', 'Carpa Común', 'Black Bass'],
      hasRareFish: true,
      description: 'Gran embalse con variedad de especies.',
    ),
    FishingSpotData(
      id: 'spot_002',
      name: 'Río - Sector 3',
      latitude: baseLat - 0.02,
      longitude: baseLng + 0.01,
      waterType: 'rio',
      totalCatches: 23,
      commonSpecies: const ['Barbo', 'Carpa Común'],
      hasRareFish: false,
      description: 'Tramo del río ideal para principiantes.',
    ),
    FishingSpotData(
      id: 'spot_003',
      name: 'Embalse Norte',
      latitude: baseLat + 0.08,
      longitude: baseLng - 0.06,
      waterType: 'embalse',
      totalCatches: 89,
      commonSpecies: const ['Lucio', 'Carpa Común', 'Perca'],
      hasRareFish: true,
      description: 'Excelente para lucios. Zona de cola especialmente productiva.',
    ),
    FishingSpotData(
      id: 'spot_004',
      name: 'Río - Puente de Viveros',
      latitude: baseLat + 0.01,
      longitude: baseLng + 0.04,
      waterType: 'rio',
      totalCatches: 34,
      commonSpecies: const ['Barbo', 'Lucio', 'Black Bass'],
      hasRareFish: false,
      description: 'Buen acceso, pozas profundas con barbos grandes.',
    ),
    FishingSpotData(
      id: 'spot_005',
      name: 'Embalse Sur',
      latitude: baseLat - 0.06,
      longitude: baseLng - 0.08,
      waterType: 'embalse',
      totalCatches: 156,
      commonSpecies: const ['Black Bass', 'Lucio', 'Carpa', 'Siluro'],
      hasRareFish: true,
      description: 'El mejor spot de la zona para Black Bass.',
    ),
    FishingSpotData(
      id: 'spot_006',
      name: 'Río - Tramo regulado',
      latitude: baseLat + 0.10,
      longitude: baseLng + 0.02,
      waterType: 'rio',
      totalCatches: 67,
      commonSpecies: const ['Trucha Marrón', 'Trucha Arcoíris'],
      hasRareFish: false,
      description: 'Tramo de trucha con regulación sin muerte. Aguas cristalinas.',
    ),
  ];

  return spots;
}

// =============================================================================
// GEOFENCING PROVIDER
// =============================================================================

/// Provider que monitorea si el usuario se acerca a un spot con peces raros
final nearbyRareSpotProvider = Provider<FishingSpotData?>((ref) {
  final userLocationAsync = ref.watch(userLocationProvider);
  final spotsAsync = ref.watch(fishingSpotsProvider);

  final userLocation = userLocationAsync.valueOrNull;
  final spots = spotsAsync.valueOrNull;

  if (userLocation == null || spots == null) return null;

  // Buscar spots con peces raros dentro del radio de geofencing
  for (final spot in spots) {
    if (!spot.hasRareFish) continue;

    final distance = _calculateDistance(
      userLocation.latitude,
      userLocation.longitude,
      spot.latitude,
      spot.longitude,
    );

    if (distance <= AppConstants.geofenceRadiusMeters) {
      return spot;
    }
  }

  return null;
});

// =============================================================================
// CAPTURAS EN EL MAPA (FILTRADAS POR ROL)
// =============================================================================

/// Datos de una captura para mostrar en el mapa
class MapCaptureData {
  final String captureId;
  final String fishId;
  final String species;
  final String rarity;
  final double latitude;
  final double longitude;
  final DateTime capturedAt;
  final String? userId;
  final bool isOwn;          // Si la captura es del usuario actual
  final bool isAnonymous;    // Si debe mostrarse como marker anónimo

  const MapCaptureData({
    required this.captureId,
    required this.fishId,
    required this.species,
    required this.rarity,
    required this.latitude,
    required this.longitude,
    required this.capturedAt,
    this.userId,
    required this.isOwn,
    required this.isAnonymous,
  });
}

/// Provider que carga las capturas filtradas según el rol del usuario actual.
/// - Fisherman: solo sus capturas + markers anónimos donde hay coincidencias
/// - Researcher/Admin: todas las capturas con datos completos
final mapCapturesProvider = FutureProvider<List<MapCaptureData>>((ref) async {
  try {
    final roleAsync = ref.watch(currentUserRoleProvider);
    final roleModel = roleAsync.valueOrNull;

    if (roleModel == null) return [];

    final capturesRepo = ref.read(capturesRepositoryProvider);

    final role = roleModel.role;
    final userId = roleModel.userId;

    if (role == UserRole.fisherman) {
      // Fisherman: obtener solo sus capturas
      final myCaptures = await capturesRepo.getCapturesForUser(
        userId: userId,
        userRole: 'fisherman',
        limit: 100,
      );

      final mapData = <MapCaptureData>[];

      for (final capture in myCaptures) {
        mapData.add(MapCaptureData(
          captureId: capture.captureId,
          fishId: capture.fishId,
          species: capture.species,
          rarity: capture.rarity,
          latitude: capture.latitude,
          longitude: capture.longitude,
          capturedAt: capture.capturedAt,
          userId: capture.userId,
          isOwn: true,
          isAnonymous: false,
        ));
      }

      // Buscar fish_ids que también fueron capturados por otros
      // para mostrar markers anónimos
      final othersFishIds =
          await capturesRepo.getOtherUsersFishIds(userId);

      for (final fishId in othersFishIds) {
        // Solo agregar un marker anónimo si no tenemos ya un marker
        // propio en la misma ubicación
        final existing = mapData.where((m) => m.fishId == fishId);
        if (existing.isNotEmpty) {
          // Agregar un marker anónimo cerca del propio (offset aleatorio)
          final own = existing.first;
          mapData.add(MapCaptureData(
            captureId: 'anon_$fishId',
            fishId: fishId,
            species: own.species,
            rarity: own.rarity,
            // Use raw coordinates — no random noise applied
            latitude: own.latitude,
            longitude: own.longitude,
            capturedAt: own.capturedAt,
            isOwn: false,
            isAnonymous: true,
          ));
        }
      }

      return mapData;
    } else {
      // Researcher/Admin: todas las capturas
      final allCaptures = await capturesRepo.getCapturesForUser(
        userId: userId,
        userRole: role.name,
        limit: 200,
      );

      return allCaptures.map((capture) => MapCaptureData(
        captureId: capture.captureId,
        fishId: capture.fishId,
        species: capture.species,
        rarity: capture.rarity,
        latitude: capture.latitude,
        longitude: capture.longitude,
        capturedAt: capture.capturedAt,
        userId: capture.userId,
        isOwn: capture.userId == userId,
        isAnonymous: false,
      )).toList();
    }
  } catch (e) {
    return [];
  }
});

/// Calcula la distancia en metros entre dos coordenadas (fórmula de Haversine)
double _calculateDistance(
  double lat1, double lon1,
  double lat2, double lon2,
) {
  const double earthRadius = 6371000; // Radio de la Tierra en metros
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

double _degreesToRadians(double degrees) {
  return degrees * pi / 180;
}
