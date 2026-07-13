import 'dart:async';
import 'dart:io';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/local_api_client.dart';
import '../../core/providers/api_providers.dart';

/// Statuses matching local server states
class JobStatus {
  static const String uploaded = 'uploaded';
  static const String processing = 'processing';
  static const String completed = 'completed';
  static const String needsReview = 'needs_review';
  static const String pendingCrop = 'pending_crop';
  static const String needsManualReview = 'needs_manual_review';
  static const String failed = 'failed';
}

/// Repository for managing identification jobs.
/// Uploads videos directly to local backend and triggers/polls processing jobs.
class IdentificationJobRepository {
  final LocalApiClient _apiClient;

  IdentificationJobRepository({
    required LocalApiClient apiClient,
  }) : _apiClient = apiClient;

  /// Uploads raw capture video + metadata to local server and creates the job.
  /// Returns the job_id.
  Future<String> uploadAndStartJob({
    required String videoPath,
    required String userId,
    String? areaCode,
    String? areaName,
    double? latitude,
    double? longitude,
    String? speciesSlug,
    String? notes,
    String? weather,
    String? bite,
    double? sizeCm,
    String? fishState,
    String? customName,
  }) async {
    final fields = <String, String>{
      'user_id': userId,
    };
    if (areaCode != null) fields['area_code'] = areaCode;
    if (areaName != null) fields['area_name'] = areaName;
    if (latitude != null) fields['latitude'] = latitude.toString();
    if (longitude != null) fields['longitude'] = longitude.toString();
    if (speciesSlug != null) fields['species_slug'] = speciesSlug;
    if (notes != null) fields['notes'] = notes;
    if (weather != null) fields['weather'] = weather;
    if (bite != null) fields['bite'] = bite;
    if (sizeCm != null) fields['size_cm'] = sizeCm.toString();
    if (fishState != null) fields['fish_state'] = fishState;
    if (customName != null) fields['custom_name'] = customName;

    final response = await _apiClient.multipartPost(
      '/api/v1/jobs/upload',
      file: File(videoPath),
      fields: fields,
    );

    return response['job_id'] as String;
  }

  /// Get a job document by ID.
  Future<Map<String, dynamic>?> getJob(String jobId) async {
    try {
      final response = await _apiClient.get('/api/v1/jobs/$jobId');
      return response as Map<String, dynamic>;
    } catch (e) {
      return null;
    }
  }

  /// Trigger processing for a job on the local AI server.
  Future<Map<String, dynamic>> triggerProcessing({
    required String jobId,
  }) async {
    final response = await _apiClient.post('/api/v1/jobs/$jobId/process', {});
    return response as Map<String, dynamic>;
  }

  /// Get the fish sighting result for a job.
  Future<Map<String, dynamic>?> getJobResult(String jobId) async {
    try {
      final response = await _apiClient.get('/api/v1/jobs/$jobId/result');
      return response as Map<String, dynamic>;
    } catch (e) {
      return null;
    }
  }

  /// Watch a job's status changes. Implemented via polling for local backend compatibility.
  Stream<Map<String, dynamic>> watchJob(String jobId) {
    return pollJob(jobId);
  }

  /// Poll job status.
  Stream<Map<String, dynamic>> pollJob(String jobId, {Duration interval = const Duration(seconds: 2)}) async* {
    while (true) {
      await Future.delayed(interval);
      final job = await getJob(jobId);
      if (job != null) {
        yield job;
        final status = job['status'] as String?;
        if (status == JobStatus.completed ||
            status == JobStatus.needsReview ||
            status == JobStatus.pendingCrop ||
            status == JobStatus.needsManualReview ||
            status == JobStatus.failed) {
          break;
        }
      }
    }
  }
}

/// Riverpod provider
final identificationJobRepositoryProvider = Provider<IdentificationJobRepository>((ref) {
  final apiClient = ref.watch(localApiClientProvider);
  return IdentificationJobRepository(apiClient: apiClient);
});
