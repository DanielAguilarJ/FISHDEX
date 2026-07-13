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

  /// Fetch sightings list for user from local SQLite via HTTP
  Future<List<FishCapture>> getCapturesForUser({
    required String userId,
    required String userRole,
    int limit = 100,
    int offset = 0,
  }) async {
    try {
      final response = await _apiClient.get('/api/v1/sightings/user/$userId');
      if (response == null) return [];
      
      final list = response as List;
      final captures = <FishCapture>[];
      
      for (final item in list) {
        final map = item as Map<String, dynamic>;
        
        // Build absolute image URL — prefer annotated preview (has bbox + AI labels),
        // then plain preview, then legacy frame_filename.
        final annotatedPreview = map['annotated_preview_filename'] as String?;
        final previewFilename  = map['preview_filename'] as String?;
        final frameFilename    = map['frame_filename'] as String?;
        final bestImage        = annotatedPreview ?? previewFilename ?? frameFilename;
        final imageUrl = bestImage != null
            ? '${AppConstants.aiServerUrl}/storage/$bestImage'
            : null;
            
        final videoFilename = map['raw_video_filename'] as String?;
        final videoUrl = videoFilename != null 
            ? '${AppConstants.aiServerUrl}/storage/$videoFilename' 
            : null;

        // Map species name from Czech/English columns or slug
        final speciesName = map['species_czech'] as String? ?? 
                            map['species_english'] as String? ?? 
                            (map['species_slug'] as String?)?.replaceAll('_', ' ') ?? 
                            'Desconocido';

        captures.add(FishCapture(
          captureId: map['id'] as String? ?? '',
          fishId: map['fish_id'] as String? ?? 'Desconocido',
          userId: map['user_id'] as String? ?? '',
          latitude: (map['location_lat'] as num?)?.toDouble() ?? 0.0,
          longitude: (map['location_lng'] as num?)?.toDouble() ?? 0.0,
          capturedAt: map['captured_at'] != null 
              ? DateTime.parse(map['captured_at'] as String) 
              : DateTime.now(),
          species: speciesName,
          scientificName: map['species_latin'] as String?,
          family: null,
          lengthCm: (map['size_cm'] as num?)?.toDouble(),
          weightKg: null,
          condition: 'released',
          videoUrl: videoUrl,
          imageUrl: imageUrl,
          confidence: (map['confidence'] as num?)?.toDouble() ?? 0.0,
          predominantColor: null,
          physicalFeatures: null,
          notes: map['notes'] as String?,
          rarity: map['rarity'] as String? ?? 'common',
          isManualEntry: false,
          xpEarned: (map['xp_earned'] as num?)?.toInt() ?? 10,
          isNewFish: (map['is_new_fish'] as num?)?.toInt() == 1,
        ));
      }
      return captures;
    } catch (e) {
      debugPrint('❌ Error getCapturesForUser: $e');
      return [];
    }
  }

  /// Get list of unique fish IDs seen by other users (stubbed)
  Future<List<String>> getOtherUsersFishIds(String userId) async {
    return [];
  }

  /// Get history of a specific fish ID (stubbed or query local server)
  Future<List<FishCapture>> getFishHistory(String fishId) async {
    return [];
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
