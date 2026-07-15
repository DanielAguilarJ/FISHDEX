import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';
import '../../../core/l10n/l10n_extension.dart';

import '../../../core/theme/app_theme.dart';

import '../../capture/presentation/capture_detail_screen.dart';

/// Pantalla de preview del video grabado
/// Permite al usuario revisar el video y decidir si enviarlo o regrabarlo
class VideoPreviewScreen extends ConsumerStatefulWidget {
  final String videoPath;
  final bool hasRecordedLocation;

  const VideoPreviewScreen({
    super.key,
    required this.videoPath,
    this.hasRecordedLocation = false,
  });

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

  /// Computes the correct aspect ratio for display, compensating for
  /// the rotation metadata embedded in the video file.
  ///
  /// On many Android devices, portrait videos are stored internally as
  /// landscape + 90°/270° rotation metadata. The video_player plugin
  /// exposes this as [VideoPlayerValue.rotationCorrection].
  /// Without compensation the [AspectRatio] widget uses the raw (landscape)
  /// ratio, making the preview appear as a narrow horizontal strip.
  double _effectiveVideoAspectRatio() {
    final value = _videoController.value;
    final rawAspectRatio = value.aspectRatio;

    if (rawAspectRatio <= 0) return 9 / 16; // safe fallback for portrait

    final rotation = value.rotationCorrection % 360;

    // If the file is stored as landscape but will be displayed rotated,
    // the layout must use the inverse ratio to appear portrait.
    if (rotation == 90 || rotation == 270) {
      return 1.0 / rawAspectRatio;
    }

    return rawAspectRatio;
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
                aspectRatio: _effectiveVideoAspectRatio(),
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

  void _submitVideo(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CaptureDetailScreen(
          videoPath: widget.videoPath,
          hasRecordedLocation: widget.hasRecordedLocation,
        ),
      ),
    );
  }
}
