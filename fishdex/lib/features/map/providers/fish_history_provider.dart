import 'dart:math';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../data/models/fish_capture.dart';
import '../../../data/repositories/captures_repository.dart';

// =============================================================================
// PROVIDER DE HISTORIAL DE PEZ
// =============================================================================

/// Provider que carga el historial completo de capturas de un fish_id específico.
/// Se usa en el mapa cuando un Researcher toca un marcador de captura
/// para ver todas las veces que ese pez fue capturado.
final fishHistoryProvider =
    FutureProvider.family<List<FishCapture>, String>((ref, fishId) async {
  final repo = ref.read(capturesRepositoryProvider);
  return repo.getFishHistory(fishId);
});

/// Provider que agrupa las capturas del historial por ubicación.
/// Capturas dentro de 500m se consideran "misma ubicación".
final fishHistoryGroupedProvider =
    FutureProvider.family<List<LocationGroup>, String>((ref, fishId) async {
  final history = await ref.watch(fishHistoryProvider(fishId).future);

  if (history.isEmpty) return [];

  final groups = <LocationGroup>[];

  for (final capture in history) {
    bool addedToGroup = false;

    for (final group in groups) {
      final distance = _haversineDistance(
        group.centerLat,
        group.centerLng,
        capture.latitude,
        capture.longitude,
      );

      if (distance <= 500) {
        group.captures.add(capture);
        addedToGroup = true;
        break;
      }
    }

    if (!addedToGroup) {
      groups.add(LocationGroup(
        centerLat: capture.latitude,
        centerLng: capture.longitude,
        captures: [capture],
      ));
    }
  }

  // Ordenar grupos por la fecha de la primera captura
  groups.sort((a, b) =>
      a.captures.last.capturedAt.compareTo(b.captures.last.capturedAt));

  return groups;
});

// =============================================================================
// MODELO DE GRUPO POR UBICACIÓN
// =============================================================================

/// Agrupa capturas que están en la misma ubicación (±500m)
class LocationGroup {
  final double centerLat;
  final double centerLng;
  final List<FishCapture> captures;

  LocationGroup({
    required this.centerLat,
    required this.centerLng,
    required this.captures,
  });

  /// Nombre descriptivo de la ubicación (coordenadas simplificadas)
  String get locationLabel =>
      '${centerLat.toStringAsFixed(4)}, ${centerLng.toStringAsFixed(4)}';

  /// Primera captura en esta ubicación
  FishCapture get firstCapture => captures.last;

  /// Última captura en esta ubicación
  FishCapture get lastCapture => captures.first;

  /// Número de capturas en esta ubicación
  int get count => captures.length;
}

// =============================================================================
// UTILIDAD - DISTANCIA HAVERSINE
// =============================================================================

double _haversineDistance(
  double lat1, double lon1,
  double lat2, double lon2,
) {
  const double earthRadius = 6371000;
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
