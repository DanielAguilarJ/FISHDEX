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
  /// [areaCode] - Czech fishing area code (required)
  /// [fishermanId] - UUID of the user from Appwrite (required)
  /// [userRole] - 'fisherman' or 'researcher'
  /// [species] - Species name if already known
  /// [fishState] - Injury notes or distinguishing marks
  /// [name] - Custom name for the fish
  /// [weather] - Weather conditions
  /// [bite] - Bait or lure used
  /// [size] - Measured size in cm
  /// [latitude] - Latitud GPS opcional
  /// [longitude] - Longitud GPS opcional
  /// [confidenceThreshold] - Umbral de confianza para formulario manual
  Future<IdentifyResult> identifyFish({
    required String videoPath,
    required String areaCode,
    required String fishermanId,
    String userRole = 'fisherman',
    String? species,
    String? fishState,
    String? name,
    String? weather,
    String? bite,
    double? size,
    double? latitude,
    double? longitude,
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

      // Required fields
      request.fields['area_code'] = areaCode;
      request.fields['fisherman_id'] = fishermanId;
      request.fields['user_role'] = userRole;

      // Optional metadata fields
      if (species != null) request.fields['species'] = species;
      if (fishState != null) request.fields['fish_state'] = fishState;
      if (name != null) request.fields['name'] = name;
      if (weather != null) request.fields['weather'] = weather;
      if (bite != null) request.fields['bite'] = bite;
      if (size != null) request.fields['size'] = size.toString();

      // GPS coordinates
      if (latitude != null) {
        request.fields['latitude'] = latitude.toString();
      }
      if (longitude != null) {
        request.fields['longitude'] = longitude.toString();
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
