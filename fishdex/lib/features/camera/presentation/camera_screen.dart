import 'dart:async';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../data/services/capture_location_service.dart';
import '../widgets/ar_overlay.dart';
import '../widgets/recording_controls.dart';
import '../providers/capture_metadata_provider.dart';
import 'video_preview_screen.dart';

/// Pantalla de Cámara con preview en vivo y AR overlay
/// Permite grabar video de 5-10 segundos del pez para identificación
class CameraScreen extends ConsumerStatefulWidget {
  const CameraScreen({super.key});

  @override
  ConsumerState<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends ConsumerState<CameraScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  bool _isInitialized = false;
  bool _isRecording = false;
  double _recordingProgress = 0.0;
  Timer? _recordingTimer;
  Timer? _progressTimer;
  String? _errorMessage;

  // Duración máxima de grabación en segundos
  static const int _maxDurationSeconds = 10;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initializeCamera();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    _recordingTimer?.cancel();
    _progressTimer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_controller == null || !_controller!.value.isInitialized) return;

    if (state == AppLifecycleState.inactive) {
      _controller?.dispose();
    } else if (state == AppLifecycleState.resumed) {
      _initializeCamera();
    }
  }

  Future<void> _initializeCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) {
        setState(() => _errorMessage = context.l10n.cameraNoCameras);
        return;
      }

      // Usar la cámara trasera
      final camera = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );

      _controller = CameraController(
        camera,
        ResolutionPreset.high, // 720p para buen balance calidad/tamaño
        enableAudio: false, // Sin audio para reducir tamaño
        imageFormatGroup: ImageFormatGroup.yuv420,
      );

      await _controller!.initialize();

      // Configurar exposición y enfoque automáticos
      await _controller!.setFlashMode(FlashMode.off);

      if (mounted) {
        setState(() {
          _isInitialized = true;
          _errorMessage = null;
        });
      }
    } catch (e) {
      setState(() {
        _errorMessage = context.l10n.cameraInitError(e.toString());
      });
    }
  }

  Future<void> _startRecording() async {
    if (_controller == null || _isRecording) return;

    try {
      // Intentar obtener la ubicación, pero no bloquear la grabación si falla
      try {
        final coordinates = await CaptureLocationService.getCurrentCoordinates();
        if (mounted) {
          ref.read(captureMetadataProvider.notifier).setLocation(
                coordinates.latitude,
                coordinates.longitude,
              );
        }
      } catch (e) {
        debugPrint('⚠️ Error obteniendo ubicación al iniciar grabación: $e');
      }

      final controller = _controller;
      if (!mounted || controller == null || !controller.value.isInitialized) {
        return;
      }

      // Lock orientation before starting so rotation metadata is stable.
      await controller.lockCaptureOrientation();
      await controller.startVideoRecording();

      setState(() {
        _isRecording = true;
        _recordingProgress = 0.0;
        _errorMessage = null;
      });

      // Iniciar el temporizador para la barra de progreso
      _progressTimer = Timer.periodic(
        const Duration(milliseconds: 100),
        (timer) {
          setState(() {
            _recordingProgress += 0.1 / _maxDurationSeconds;
            if (_recordingProgress >= 1.0) {
              _stopRecording();
            }
          });
        },
      );

      // Auto-stop después del tiempo máximo
      _recordingTimer = Timer(
        const Duration(seconds: _maxDurationSeconds),
        _stopRecording,
      );
    } catch (e) {
      // Make sure the orientation lock is released if recording never started.
      try {
        await _controller?.unlockCaptureOrientation();
      } catch (_) {}

      if (mounted) {
        setState(() => _errorMessage = context.l10n.cameraRecordError);
      }
    }
  }

  Future<void> _stopRecording() async {
    if (_controller == null || !_isRecording) return;

    _recordingTimer?.cancel();
    _progressTimer?.cancel();

    try {
      final videoFile = await _controller!.stopVideoRecording();

      // Release the orientation lock after the file is written.
      try {
        await _controller!.unlockCaptureOrientation();
      } catch (_) {}

      setState(() {
        _isRecording = false;
        _recordingProgress = 0.0;
      });

      // Navegar a la pantalla de preview
      if (mounted) {
        Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => VideoPreviewScreen(
              videoPath: videoFile.path,
              hasRecordedLocation: true,
            ),
          ),
        );
      }
    } catch (e) {
      // Also unlock if stopVideoRecording() itself fails.
      try {
        await _controller?.unlockCaptureOrientation();
      } catch (_) {}

      setState(() {
        _isRecording = false;
        _recordingProgress = 0.0;
        _errorMessage = context.l10n.cameraStopError;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // Preview de cámara
          _buildCameraPreview(),

          // AR Overlay (guías visuales)
          if (_isInitialized) const AROverlay(),

          // Indicadores superiores
          if (_isInitialized) _buildTopIndicators(),

          // Controles de grabación (abajo)
          if (_isInitialized)
            Positioned(
              bottom: 0,
              left: 0,
              right: 0,
              child: RecordingControls(
                isRecording: _isRecording,
                progress: _recordingProgress,
                maxDurationSeconds: _maxDurationSeconds,
                onStartRecording: _startRecording,
                onStopRecording: _stopRecording,
              ),
            ),

          // Error overlay
          if (_errorMessage != null) _buildErrorOverlay(),
        ],
      ),
    );
  }

  Widget _buildCameraPreview() {
    if (!_isInitialized || _controller == null) {
      return Container(
        color: Colors.black,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(color: AppTheme.accentBlue),
              const SizedBox(height: 16),
              Text(
                context.l10n.cameraLoading,
                style: const TextStyle(color: Colors.white70),
              ),
            ],
          ),
        ),
      );
    }

    // Ajustar aspect ratio del preview
    final size = MediaQuery.of(context).size;
    final scale = size.aspectRatio * _controller!.value.aspectRatio;
    final adjustedScale = scale < 1 ? 1 / scale : scale;

    return Transform.scale(
      scale: adjustedScale,
      child: Center(
        child: CameraPreview(_controller!),
      ),
    );
  }

  Widget _buildTopIndicators() {
    return Positioned(
      top: MediaQuery.of(context).padding.top + 16,
      left: 16,
      right: 16,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Indicador de grabación
          if (_isRecording)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.red,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      shape: BoxShape.circle,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    '${(_recordingProgress * _maxDurationSeconds).toInt()}s / ${_maxDurationSeconds}s',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            )
          else
            const SizedBox.shrink(),

          // Botón de flash
          if (!_isRecording)
            _buildCircleButton(
              icon: Icons.flash_off,
              onTap: () async {
                final currentMode = _controller!.value.flashMode;
                final newMode = currentMode == FlashMode.off
                    ? FlashMode.torch
                    : FlashMode.off;
                await _controller!.setFlashMode(newMode);
                setState(() {});
              },
            ),
        ],
      ),
    );
  }

  Widget _buildCircleButton({required IconData icon, VoidCallback? onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.black.withOpacity(0.5),
        ),
        child: Icon(icon, color: Colors.white, size: 20),
      ),
    );
  }

  Widget _buildErrorOverlay() {
    return Container(
      color: Colors.black87,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.error_outline,
                color: Colors.red,
                size: 48,
              ),
              const SizedBox(height: 16),
              Text(
                _errorMessage!,
                style: const TextStyle(color: Colors.white, fontSize: 16),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              ElevatedButton(
                onPressed: _initializeCamera,
                child: Text(context.l10n.cameraRetry),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
