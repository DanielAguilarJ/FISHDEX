import 'dart:io';
import 'package:appwrite/appwrite.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/constants/app_constants.dart';
import '../../core/providers/appwrite_providers.dart';

/// Service responsible for uploading media files to Appwrite Storage.
/// Handles raw videos, processed frames, and user avatars.
class MediaUploadService {
  final dynamic _storage;

  MediaUploadService({required dynamic storage}) : _storage = storage;

  /// Upload a raw capture video to the capture_raw_videos bucket.
  /// Returns the file ID on success.
  Future<String> uploadRawVideo({
    required String videoPath,
    required String userId,
    required String jobId,
  }) async {
    final file = await _storage.createFile(
      bucketId: AppConstants.captureRawVideosBucket,
      fileId: ID.unique(),
      file: InputFile.fromPath(
        path: videoPath,
        filename: '${userId}_${jobId}_raw.mp4',
      ),
    );
    return file.$id;
  }

  /// Upload a user avatar image.
  /// Returns the file ID on success.
  Future<String> uploadAvatar({
    required String imagePath,
    required String userId,
  }) async {
    final extension = imagePath.split('.').last;
    final file = await _storage.createFile(
      bucketId: AppConstants.userAvatarsBucket,
      fileId: ID.unique(),
      file: InputFile.fromPath(
        path: imagePath,
        filename: '${userId}_avatar.$extension',
      ),
    );
    return file.$id;
  }

  /// Get the view URL for a file in any bucket.
  String getFileViewUrl({
    required String bucketId,
    required String fileId,
  }) {
    return '${AppConstants.appwriteEndpoint}/storage/buckets/$bucketId/files/$fileId/view?project=${AppConstants.appwriteProjectId}';
  }

  /// Get a preview URL for an image file (with optional dimensions).
  String getFilePreviewUrl({
    required String bucketId,
    required String fileId,
    int? width,
    int? height,
  }) {
    var url = '${AppConstants.appwriteEndpoint}/storage/buckets/$bucketId/files/$fileId/preview?project=${AppConstants.appwriteProjectId}';
    if (width != null) url += '&width=$width';
    if (height != null) url += '&height=$height';
    return url;
  }
}

/// Riverpod provider for MediaUploadService
final mediaUploadServiceProvider = Provider<MediaUploadService>((ref) {
  final storage = ref.watch(appwriteStorageProvider);
  return MediaUploadService(storage: storage);
});
