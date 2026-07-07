import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/identify_result.dart';
import '../../core/constants/app_constants.dart';

/// Servicio que se comunica con el servidor de IA en Hugging Face Spaces.
/// Extrae un frame del video localmente y lo envía como imagen JPEG
/// (más eficiente que subir el video completo).
class IdentifyService {
  /// Envía un video (o una imagen extraída de él) al servidor de IA.
  ///
  /// [videoPath] - Ruta local del video/imagen
  /// [latitude] - Latitud GPS opcional
  /// [longitude] - Longitud GPS opcional
  /// [userId] - ID del usuario actual
  /// [confidenceThreshold] - Umbral de confianza para formulario manual
  ///
  /// El servidor acepta tanto video como imagen, pero enviar la imagen
  /// es ~20× más rápido por el tamaño reducido.
  Future<IdentifyResult> identifyFish({
    required String videoPath,
    double? latitude,
    double? longitude,
    String? userId,
    double? confidenceThreshold,
  }) async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.identifyEndpoint}',
      );

      final request = http.MultipartRequest('POST', uri);

      // Enviar el archivo directamente (el servidor acepta video e imagen)
      final file = File(videoPath);
      final extension = videoPath.split('.').last.toLowerCase();

      // Determinar filename según extensión
      String filename;
      if (['jpg', 'jpeg', 'png', 'webp'].contains(extension)) {
        filename = 'fish_capture.$extension';
      } else {
        filename = 'fish_video.$extension';
      }

      final multipartFile = await http.MultipartFile.fromPath(
        'video', // Nombre del campo que espera el servidor
        file.path,
        filename: filename,
      );
      request.files.add(multipartFile);

      // Campos opcionales
      if (latitude != null) {
        request.fields['latitude'] = latitude.toString();
      }
      if (longitude != null) {
        request.fields['longitude'] = longitude.toString();
      }
      if (userId != null) {
        request.fields['user_id'] = userId;
      }
      // Enviar el umbral de confianza
      request.fields['confidence_threshold'] =
          (confidenceThreshold ?? AppConstants.aiConfidenceThreshold).toString();

      // Timeout 90s: los Spaces gratuitos pueden tardar ~30s en despertar
      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 90),
      );
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 200) {
        final jsonData = json.decode(response.body) as Map<String, dynamic>;
        return IdentifyResult.fromJson(jsonData);
      } else {
        // Intentar parsear el error del servidor
        String errorDetail = response.body;
        try {
          final errorJson = json.decode(response.body) as Map<String, dynamic>;
          errorDetail = errorJson['detail'] ?? response.body;
        } catch (_) {}

        throw IdentifyException(
          response.statusCode == 400
              ? errorDetail
              : 'Error del servidor (${response.statusCode})',
          detail: errorDetail,
        );
      }
    } on SocketException {
      throw IdentifyException(
        'No se pudo conectar al servidor de IA',
        detail:
            'Verifica tu conexión a internet. El servidor puede estar despertando (~30s).',
      );
    } catch (e) {
      if (e is IdentifyException) rethrow;
      throw IdentifyException(
        'Error al identificar el pez',
        detail: e.toString(),
      );
    }
  }

  /// Endpoint de prueba (sin archivo, para testing rápido)
  Future<IdentifyResult> identifyTest() async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.identifyEndpoint}/test',
      );

      final response = await http.get(uri).timeout(
        const Duration(seconds: 60),
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
  String toString() =>
      'IdentifyException: $message${detail != null ? ' ($detail)' : ''}';
}
