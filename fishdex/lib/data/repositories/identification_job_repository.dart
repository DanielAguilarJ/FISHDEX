import 'dart:async';
import 'dart:convert';
import 'package:appwrite/appwrite.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;
import '../../core/constants/app_constants.dart';
import '../../core/providers/appwrite_providers.dart';

/// Job statuses
class JobStatus {
  static const String uploaded = 'uploaded';
  static const String processing = 'processing';
  static const String completed = 'completed';
  static const String needsReview = 'needs_review';
  static const String failed = 'failed';
}

/// Repository for managing identification jobs.
/// Creates jobs in Appwrite, triggers AI processing, and watches status.
class IdentificationJobRepository {
  final Databases _databases;
  final Realtime _realtime;

  IdentificationJobRepository({
    required Databases databases,
    required Realtime realtime,
  })  : _databases = databases,
        _realtime = realtime;

  /// Create a new identification job document in Appwrite.
  /// Returns the job_id (document ID).
  Future<String> createJob({
    required String userId,
    required String rawVideoFileId,
    String? areaCode,
    String? areaName,
    double? latitude,
    double? longitude,
    String? speciesSlug,
    String? notes,
  }) async {
    final jobId = ID.unique();
    final now = DateTime.now().toIso8601String();

    await _databases.createDocument(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.identificationJobsCollection,
      documentId: jobId,
      data: {
        'user_id': userId,
        'status': JobStatus.uploaded,
        'raw_video_file_id': rawVideoFileId,
        'area_code': areaCode,
        'area_name': areaName,
        'latitude': latitude,
        'longitude': longitude,
        'species_slug': speciesSlug,
        'notes': notes,
        'created_at': now,
        'updated_at': now,
      },
    );

    return jobId;
  }

  /// Get a job document by ID.
  Future<Map<String, dynamic>?> getJob(String jobId) async {
    try {
      final doc = await _databases.getDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.identificationJobsCollection,
        documentId: jobId,
      );
      return doc.data;
    } catch (e) {
      return null;
    }
  }

  /// Trigger the AI Server to process a job.
  /// Calls POST /api/v1/jobs/{job_id}/process
  Future<bool> triggerProcessing({
    required String jobId,
    String? jwt,
  }) async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}/api/v1/jobs/$jobId/process',
      );

      final headers = <String, String>{
        'Content-Type': 'application/json',
      };
      if (jwt != null && jwt.isNotEmpty) {
        headers['Authorization'] = 'Bearer $jwt';
      }

      final response = await http.post(uri, headers: headers).timeout(
        const Duration(seconds: 10),
      );

      return response.statusCode == 200 || response.statusCode == 202;
    } catch (e) {
      return false;
    }
  }

  /// Watch a job's status changes via Appwrite Realtime.
  /// Returns a stream of job data maps.
  Stream<Map<String, dynamic>> watchJob(String jobId) {
    final channel =
        'databases.${AppConstants.databaseId}.collections.${AppConstants.identificationJobsCollection}.documents.$jobId';

    final subscription = _realtime.subscribe([channel]);

    return subscription.stream.map((event) => event.payload);
  }

  /// Poll job status (fallback when Realtime is unavailable).
  Stream<Map<String, dynamic>> pollJob(String jobId, {Duration interval = const Duration(seconds: 2)}) async* {
    while (true) {
      await Future.delayed(interval);
      final job = await getJob(jobId);
      if (job != null) {
        yield job;
        final status = job['status'] as String?;
        if (status == JobStatus.completed ||
            status == JobStatus.needsReview ||
            status == JobStatus.failed) {
          break;
        }
      }
    }
  }
}

/// Riverpod provider
final identificationJobRepositoryProvider = Provider<IdentificationJobRepository>((ref) {
  final databases = ref.watch(appwriteDatabasesProvider);
  final realtime = ref.watch(appwriteRealtimeProvider);
  return IdentificationJobRepository(databases: databases, realtime: realtime);
});
