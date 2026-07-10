import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/local_api_client.dart';
import '../constants/app_constants.dart';

/// Provider for the single local HTTP API client instance.
final localApiClientProvider = Provider<LocalApiClient>((ref) {
  return LocalApiClient(
    baseUrl: AppConstants.aiServerUrl,
    clientSecret: 'change-me', // Matches FISHDEX_AI_SERVER_SECRET in server
  );
});
