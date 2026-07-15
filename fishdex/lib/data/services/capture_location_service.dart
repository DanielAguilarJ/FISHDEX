import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

class CaptureCoordinates {
  final double latitude;
  final double longitude;
  final double accuracyMeters;

  const CaptureCoordinates({
    required this.latitude,
    required this.longitude,
    required this.accuracyMeters,
  });

  bool get isValid =>
      latitude.isFinite &&
      longitude.isFinite &&
      latitude >= -90 &&
      latitude <= 90 &&
      longitude >= -180 &&
      longitude <= 180 &&
      (latitude != 0.0 || longitude != 0.0);
}

class CaptureLocationException implements Exception {
  final String message;

  const CaptureLocationException(this.message);

  @override
  String toString() => message;
}

class CaptureLocationService {
  const CaptureLocationService._();

  static Future<CaptureCoordinates> getCurrentCoordinates() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      if (kDebugMode) {
        return const CaptureCoordinates(
          latitude: 50.088,
          longitude: 14.435,
          accuracyMeters: 10,
        );
      }
      throw const CaptureLocationException(
        'Activa la ubicación del dispositivo para guardar el punto exacto de la captura.',
      );
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied) {
      if (kDebugMode) {
        return const CaptureCoordinates(
          latitude: 50.088,
          longitude: 14.435,
          accuracyMeters: 10,
        );
      }
      throw const CaptureLocationException(
        'Se necesita permiso de ubicación para guardar la captura en el mapa.',
      );
    }

    if (permission == LocationPermission.deniedForever) {
      if (kDebugMode) {
        return const CaptureCoordinates(
          latitude: 50.088,
          longitude: 14.435,
          accuracyMeters: 10,
        );
      }
      throw const CaptureLocationException(
        'El permiso de ubicación está bloqueado. Actívalo desde los ajustes del dispositivo.',
      );
    }

    Position? position;
    try {
      position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.best,
        timeLimit: const Duration(seconds: 5),
      );
    } catch (e) {
      try {
        position = await Geolocator.getLastKnownPosition();
      } catch (_) {}
    }

    if (position == null) {
      if (kDebugMode) {
        return const CaptureCoordinates(
          latitude: 50.088,
          longitude: 14.435,
          accuracyMeters: 10,
        );
      }
      throw const CaptureLocationException(
        'No se pudo determinar la ubicación del dispositivo. Asegúrate de tener el GPS activo.',
      );
    }

    final coordinates = CaptureCoordinates(
      latitude: position.latitude,
      longitude: position.longitude,
      accuracyMeters: position.accuracy,
    );

    if (!coordinates.isValid) {
      if (kDebugMode) {
        return const CaptureCoordinates(
          latitude: 50.088,
          longitude: 14.435,
          accuracyMeters: 10,
        );
      }
      throw const CaptureLocationException(
        'El dispositivo devolvió una ubicación inválida. Intenta nuevamente al aire libre.',
      );
    }

    return coordinates;
  }
}
