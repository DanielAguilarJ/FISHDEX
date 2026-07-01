import 'dart:math';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import '../../../core/constants/app_constants.dart';

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

/// Provider que carga los fishing spots desde Appwrite
/// NOTA: Por ahora usa datos simulados. Se conectará a Appwrite en la integración.
final fishingSpotsProvider = FutureProvider<List<FishingSpotData>>((ref) async {
  // TODO: Conectar con Appwrite Databases cuando esté configurado
  // final databases = ref.watch(appwriteDatabasesProvider);
  // final response = await databases.listDocuments(
  //   databaseId: AppConstants.databaseId,
  //   collectionId: AppConstants.fishingSpotsCollection,
  // );
  
  // Por ahora, devolver datos simulados para testing
  return _generateMockSpots(ref);
});

/// Genera spots de prueba cerca de la ubicación del usuario
List<FishingSpotData> _generateMockSpots(Ref ref) {
  // Spots de ejemplo (Madrid y alrededores - ajustar según ubicación real)
  final spots = <FishingSpotData>[
    const FishingSpotData(
      id: 'spot_001',
      name: 'Embalse de El Atazar',
      latitude: 40.9120,
      longitude: -3.4890,
      waterType: 'embalse',
      totalCatches: 47,
      commonSpecies: ['Trucha Arcoíris', 'Carpa Común', 'Black Bass'],
      hasRareFish: true,
      description: 'Gran embalse con variedad de especies. Zona norte ideal para truchas.',
    ),
    const FishingSpotData(
      id: 'spot_002',
      name: 'Río Manzanares - Sector 3',
      latitude: 40.3950,
      longitude: -3.7200,
      waterType: 'rio',
      totalCatches: 23,
      commonSpecies: ['Barbo', 'Carpa Común'],
      hasRareFish: false,
      description: 'Tramo urbano del Manzanares, ideal para principiantes.',
    ),
    const FishingSpotData(
      id: 'spot_003',
      name: 'Embalse de Santillana',
      latitude: 40.7200,
      longitude: -3.8300,
      waterType: 'embalse',
      totalCatches: 89,
      commonSpecies: ['Lucio', 'Carpa Común', 'Perca'],
      hasRareFish: true,
      description: 'Excelente para lucios. Zona de cola especialmente productiva.',
    ),
    const FishingSpotData(
      id: 'spot_004',
      name: 'Río Jarama - Puente de Viveros',
      latitude: 40.4600,
      longitude: -3.5100,
      waterType: 'rio',
      totalCatches: 34,
      commonSpecies: ['Barbo', 'Lucio', 'Black Bass'],
      hasRareFish: false,
      description: 'Buen acceso, pozas profundas con barbos grandes.',
    ),
    const FishingSpotData(
      id: 'spot_005',
      name: 'Embalse de Valmayor',
      latitude: 40.5500,
      longitude: -4.0200,
      waterType: 'embalse',
      totalCatches: 156,
      commonSpecies: ['Black Bass', 'Lucio', 'Carpa', 'Siluro'],
      hasRareFish: true,
      description: 'El mejor spot de la zona para Black Bass. Se han avistado siluros.',
    ),
    const FishingSpotData(
      id: 'spot_006',
      name: 'Río Lozoya - Tramo regulado',
      latitude: 40.9500,
      longitude: -3.6400,
      waterType: 'rio',
      totalCatches: 67,
      commonSpecies: ['Trucha Marrón', 'Trucha Arcoíris'],
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
