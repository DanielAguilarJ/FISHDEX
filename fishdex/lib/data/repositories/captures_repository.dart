import 'package:flutter/foundation.dart';
import '../../core/constants/app_constants.dart';
import '../../core/api/local_api_client.dart';
import '../../core/providers/api_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/fish_capture.dart';

/// Local implementation of CapturesRepository that queries the local AI Server instead of Appwrite.
class CapturesRepository {
  final LocalApiClient _apiClient;

  CapturesRepository({
    required LocalApiClient apiClient,
  }) : _apiClient = apiClient;

  /// Returns a mock/fallback matching result locally.
  /// (In v2 OBB flow, matching is handled entirely server-side, so this is rarely called)
  Future<FishMatchResult> matchOrCreateFishId({
    required String species,
    required double latitude,
    required double longitude,
  }) async {
    return FishMatchResult(
      fishId: 'CZ-LOCAL-MOCK-${DateTime.now().millisecondsSinceEpoch}',
      isNewFish: true,
    );
  }

  /// Save capture manual entry (rarely used in v2 job pipeline).
  Future<CaptureResult> saveCapture(FishCapture capture) async {
    try {
      // Stub implementation since server registers captures during job processing
      return const CaptureResult(success: true, captureId: 'local_save');
    } catch (e) {
      return CaptureResult(success: false, errorMessage: e.toString());
    }
  }

  /// Fetch sightings owned by one user for collection/profile screens.
  Future<List<FishCapture>> getCapturesForUser({
    required String userId,
    required String userRole,
    int limit = 100,
    int offset = 0,
  }) async {
    try {
      final encodedUserId = Uri.encodeComponent(userId);
      final response = await _apiClient.get(
        '/api/v1/sightings/user/$encodedUserId?limit=$limit&offset=$offset',
      );
      return _parseCaptureList(response);
    } catch (e) {
      debugPrint('❌ Error getCapturesForUser: $e');
      return [];
    }
  }

  /// Fetch the exact geolocated captures visible to the authenticated role.
  /// The server is authoritative: fishermen receive only their own captures,
  /// while researchers/admins receive every geolocated capture.
  Future<List<FishCapture>> getCapturesForMap({int limit = 500}) async {
    final response = await _apiClient.get('/api/v1/sightings/map?limit=$limit');
    return _parseCaptureList(response);
  }

  /// Get the chronological history of one fish individual.
  /// The server restricts this endpoint to researchers/admins.
  Future<List<FishCapture>> getFishHistory(String fishId) async {
    final encodedFishId = Uri.encodeComponent(fishId);
    final response = await _apiClient.get(
      '/api/v1/sightings/fish/$encodedFishId/history',
    );
    return _parseCaptureList(response);
  }

  List<FishCapture> _parseCaptureList(dynamic response) {
    if (response == null) return [];
    if (response is! List) {
      throw const FormatException('La respuesta de capturas no es una lista');
    }

    return response
        .map((item) => _captureFromServer(
              Map<String, dynamic>.from(item as Map),
            ))
        .toList();
  }

  FishCapture _captureFromServer(Map<String, dynamic> map) {
    final previewFilename = map['preview_filename'] as String?;
    final frameFilename = map['frame_filename'] as String?;
    final annotatedPreview = map['annotated_preview_filename'] as String?;
    final bestImage = previewFilename ?? frameFilename ?? annotatedPreview;
    final imageUrl = _storageUrl(bestImage);

    final videoFilename = map['video_filename'] as String? ??
        map['raw_video_filename'] as String?;
    final videoUrl = _storageUrl(videoFilename);

    final speciesName = map['species_czech'] as String? ??
        map['species_english'] as String? ??
        (map['species_slug'] as String?)?.replaceAll('_', ' ') ??
        'Desconocido';

    final capturedAtValue =
        map['captured_at'] as String? ?? map['created_at'] as String?;
    final capturedAt = capturedAtValue == null
        ? DateTime.now()
        : DateTime.tryParse(capturedAtValue) ?? DateTime.now();

    return FishCapture(
      captureId: map['id'] as String? ?? map[r'$id'] as String? ?? '',
      fishId: map['fish_id'] as String? ?? 'Desconocido',
      userId: map['user_id'] as String? ?? '',
      latitude: (map['location_lat'] as num?)?.toDouble() ?? 0.0,
      longitude: (map['location_lng'] as num?)?.toDouble() ?? 0.0,
      capturedAt: capturedAt,
      species: speciesName,
      scientificName: map['species_latin'] as String?,
      lengthCm: (map['size_cm'] as num?)?.toDouble(),
      condition: map['fish_state'] as String? ?? 'released',
      videoUrl: videoUrl,
      imageUrl: imageUrl,
      confidence: (map['confidence'] as num?)?.toDouble() ?? 0.0,
      notes: map['notes'] as String?,
      rarity: map['rarity'] as String? ?? 'common',
      isManualEntry: false,
      xpEarned: (map['xp_earned'] as num?)?.toInt() ?? 10,
      isNewFish: _parseBool(map['is_new_fish'], defaultValue: true),
    );
  }

  String? _storageUrl(String? filename) {
    if (filename == null || filename.isEmpty) return null;
    final normalized = filename.replaceAll('\\', '/');
    return '${AppConstants.aiServerUrl}/storage/$normalized';
  }

  bool _parseBool(dynamic value, {required bool defaultValue}) {
    if (value is bool) return value;
    if (value is num) return value.toInt() == 1;
    if (value is String) {
      final normalized = value.trim().toLowerCase();
      return normalized == '1' || normalized == 'true';
    }
    return defaultValue;
  }

  /// Update capture manual entry (stubbed)
  Future<bool> updateCapture({
    required String captureId,
    required Map<String, dynamic> data,
  }) async {
    return true;
  }
}

/// Helper classes matching captures_repository interface
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

class CaptureResult {
  final bool success;
  final String? captureId;
  final String? errorMessage;

  const CaptureResult({
    required this.success,
    this.captureId,
    this.errorMessage,
  });
}

/// Riverpod Provider
final capturesRepositoryProvider = Provider<CapturesRepository>((ref) {
  final apiClient = ref.watch(localApiClientProvider);
  return CapturesRepository(apiClient: apiClient);
});
