import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:camera/camera.dart';

/// Provider que lista las cámaras disponibles
final availableCamerasProvider = FutureProvider<List<CameraDescription>>((ref) async {
  return await availableCameras();
});

/// Provider del estado de la cámara (futura mejora)
final cameraStateProvider = StateProvider<CameraState>((ref) {
  return CameraState.idle;
});

enum CameraState {
  idle,
  initializing,
  ready,
  recording,
  processing,
  error,
}
