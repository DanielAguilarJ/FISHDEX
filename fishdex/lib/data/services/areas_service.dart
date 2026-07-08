import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/fishing_area.dart';
import '../../core/constants/app_constants.dart';

/// Service that fetches nearby fishing areas and species list from the AI server.
class AreasService {
  /// Get nearby fishing areas based on GPS coordinates.
  ///
  /// [lat] - Current latitude
  /// [lon] - Current longitude
  /// [radiusKm] - Search radius in kilometers (default 10.0)
  ///
  /// Returns list of FishingArea sorted by distance.
  /// Falls back to empty list on error (doesn't crash the app).
  Future<List<FishingArea>> getNearbyAreas(
    double lat,
    double lon, {
    double radiusKm = 10.0,
  }) async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.areasSearchEndpoint}'
        '?lat=$lat&lon=$lon&radius_km=$radiusKm',
      );

      final response = await http.get(uri).timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body) as Map<String, dynamic>;
        final areasList = jsonData['areas'] as List<dynamic>? ?? [];
        return areasList
            .map((a) => FishingArea.fromJson(a as Map<String, dynamic>))
            .toList();
      }
      return [];
    } catch (e) {
      // Don't crash the app - return empty list on error
      return [];
    }
  }

  /// Get the complete list of all Czech fish species from the server.
  ///
  /// Returns list of English species names for dropdown population.
  /// Falls back to empty list on error.
  Future<List<String>> getAllSpecies() async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.speciesListEndpoint}',
      );

      final response = await http.get(uri).timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body) as Map<String, dynamic>;
        final speciesList = jsonData['species'] as List<dynamic>? ?? [];
        return speciesList
            .map((s) => (s as Map<String, dynamic>)['english_name'] as String)
            .toList();
      }
      return [];
    } catch (e) {
      return [];
    }
  }

  /// Get full species data including Czech, English, and Latin names.
  Future<List<Map<String, dynamic>>> getAllSpeciesFull() async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.speciesListEndpoint}',
      );

      final response = await http.get(uri).timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body) as Map<String, dynamic>;
        final speciesList = jsonData['species'] as List<dynamic>? ?? [];
        return speciesList
            .map((s) => s as Map<String, dynamic>)
            .toList();
      }
      return [];
    } catch (e) {
      return [];
    }
  }
}
