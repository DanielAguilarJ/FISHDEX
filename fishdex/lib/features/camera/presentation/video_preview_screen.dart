import 'dart:io';
import 'package:appwrite/appwrite.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/services/media_upload_service.dart';
import '../../../data/repositories/identification_job_repository.dart';
import '../../auth/providers/auth_provider.dart';
import '../../camera/providers/capture_metadata_provider.dart';
import '../../identify/presentation/identifying_screen.dart';

/// Pantalla de preview del video grabado
/// Permite al usuario revisar el video y decidir si enviarlo o regrabarlo
class VideoPreviewScreen extends ConsumerStatefulWidget {
  final String videoPath;

  const VideoPreviewScreen({super.key, required this.videoPath});

  @override
  ConsumerState<VideoPreviewScreen> createState() => _VideoPreviewScreenState();
}

class _VideoPreviewScreenState extends ConsumerState<VideoPreviewScreen> {
  late VideoPlayerController _videoController;
  bool _isInitialized = false;

  @override
  void initState() {
    super.initState();
    _initializeVideo();
  }

  Future<void> _initializeVideo() async {
    _videoController = VideoPlayerController.file(File(widget.videoPath));
    await _videoController.initialize();
    await _videoController.setLooping(true);
    await _videoController.play();

    if (mounted) {
      setState(() => _isInitialized = true);
    }
  }

  @override
  void dispose() {
    _videoController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // Video preview
          if (_isInitialized)
            Center(
              child: AspectRatio(
                aspectRatio: _videoController.value.aspectRatio,
                child: VideoPlayer(_videoController),
              ),
            )
          else
            const Center(
              child: CircularProgressIndicator(color: AppTheme.accentBlue),
            ),

          // Top bar con botón de volver
          Positioned(
            top: MediaQuery.of(context).padding.top + 16,
            left: 16,
            child: GestureDetector(
              onTap: () => Navigator.pop(context),
              child: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.black.withOpacity(0.5),
                ),
                child: const Icon(Icons.close, color: Colors.white),
              ),
            ),
          ),

          // Controles inferiores
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: _buildBottomControls(context),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomControls(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        left: 24,
        right: 24,
        bottom: MediaQuery.of(context).padding.bottom + 24,
        top: 24,
      ),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Colors.transparent,
            Colors.black.withOpacity(0.8),
          ],
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Título
          Text(
            context.l10n.videoPreviewTitle,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            context.l10n.videoPreviewSubtitle,
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 24),

          // Botones de acción
          Row(
            children: [
              // Botón REGRABAR
              Expanded(
                child: SizedBox(
                  height: 52,
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.refresh),
                    label: Text(context.l10n.videoPreviewRetake),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: const BorderSide(color: Colors.white54),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              // Botón IDENTIFICAR
              Expanded(
                flex: 2,
                child: SizedBox(
                  height: 52,
                  child: ElevatedButton.icon(
                    onPressed: () => _submitVideo(context),
                    icon: const Icon(Icons.search),
                    label: Text(context.l10n.videoPreviewIdentify),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.accentBlue,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      textStyle: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _submitVideo(BuildContext context) async {
    // Show loading state
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(
        child: CircularProgressIndicator(color: AppTheme.accentBlue),
      ),
    );

    try {
      final authUser = ref.read(authStateProvider).valueOrNull;
      if (authUser == null) {
        if (context.mounted) Navigator.pop(context); // dismiss loading
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Error: Not authenticated')),
        );
        return;
      }

      final mediaService = ref.read(mediaUploadServiceProvider);
      final jobRepo = ref.read(identificationJobRepositoryProvider);
      final captureMetadata = ref.read(captureMetadataProvider);

      // 1. Upload raw video to Appwrite Storage
      final jobId = ID.unique();
      final videoFileId = await mediaService.uploadRawVideo(
        videoPath: widget.videoPath,
        userId: authUser.$id,
        jobId: jobId,
      );

      // 2. Create identification job document
      final createdJobId = await jobRepo.createJob(
        userId: authUser.$id,
        rawVideoFileId: videoFileId,
        areaCode: captureMetadata?.areaCode,
        areaName: captureMetadata?.areaName,
        latitude: captureMetadata?.lat,
        longitude: captureMetadata?.lon,
      );

      // 3. Trigger AI Server processing (fire-and-forget)
      // Get JWT for auth
      final account = ref.read(appwriteAccountProvider);
      String? jwt;
      try {
        final jwtResponse = await account.createJWT();
        jwt = jwtResponse.jwt;
      } catch (_) {}
      
      jobRepo.triggerProcessing(jobId: createdJobId, jwt: jwt);

      // 4. Navigate to identifying screen with job ID
      if (context.mounted) {
        Navigator.pop(context); // dismiss loading
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => IdentifyingScreen(jobId: createdJobId),
          ),
        );
      }
    } catch (e) {
      if (context.mounted) {
        Navigator.pop(context); // dismiss loading
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: ${e.toString()}')),
        );
      }
    }
  }
}
