import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/identify_result.dart';
import '../../core/constants/app_constants.dart';

/// Servicio que se comunica con el servidor FastAPI de IA
/// Envía el video y recibe la identificación del pez
class IdentifyService {
  /// Envía un video al servidor de IA para identificar al pez
  /// 
  /// [videoPath] - Ruta local del video grabado
  /// [latitude] - Latitud GPS opcional
  /// [longitude] - Longitud GPS opcional
  /// [userId] - ID del usuario actual
  /// 
  /// Retorna un [IdentifyResult] con todos los datos de la identificación
  Future<IdentifyResult> identifyFish({
    required String videoPath,
    double? latitude,
    double? longitude,
    String? userId,
  }) async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.identifyEndpoint}',
      );

      // Crear multipart request
      final request = http.MultipartRequest('POST', uri);

      // Añadir el archivo de video
      final videoFile = await http.MultipartFile.fromPath(
        'video',
        videoPath,
        filename: 'fish_video.mp4',
      );
      request.files.add(videoFile);

      // Añadir campos adicionales
      if (latitude != null) {
        request.fields['latitude'] = latitude.toString();
      }
      if (longitude != null) {
        request.fields['longitude'] = longitude.toString();
      }
      if (userId != null) {
        request.fields['user_id'] = userId;
      }

      // Enviar request — timeout 90s porque HF Spaces gratuitos
      // pueden tardar ~30s en despertar tras 48h de inactividad
      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 90),
      );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body) as Map<String, dynamic>;
        return IdentifyResult.fromJson(jsonData);
      } else {
        throw IdentifyException(
          'Error del servidor: ${response.statusCode}',
          detail: response.body,
        );
      }
    } on SocketException {
      throw IdentifyException(
        'No se pudo conectar al servidor de IA',
        detail: 'Verifica que el servidor esté corriendo en ${AppConstants.aiServerUrl}',
      );
    } catch (e) {
      if (e is IdentifyException) rethrow;
      throw IdentifyException(
        'Error al identificar el pez',
        detail: e.toString(),
      );
    }
  }

  /// Endpoint de prueba (sin video, para testing rápido)
  Future<IdentifyResult> identifyTest() async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.identifyEndpoint}/test',
      );

      final response = await http.get(uri).timeout(
        const Duration(seconds: 30),
      );

      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body) as Map<String, dynamic>;
        return IdentifyResult.fromJson(jsonData);
      } else {
        throw IdentifyException('Error en test: ${response.statusCode}');
      }
    } catch (e) {
      if (e is IdentifyException) rethrow;
      throw IdentifyException('Error de conexión', detail: e.toString());
    }
  }
}

/// Excepción personalizada para errores de identificación
class IdentifyException implements Exception {
  final String message;
  final String? detail;

  IdentifyException(this.message, {this.detail});

  @override
  String toString() => 'IdentifyException: $message${detail != null ? ' ($detail)' : ''}';
}
