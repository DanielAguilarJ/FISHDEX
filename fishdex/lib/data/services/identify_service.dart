import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';
import '../models/identify_result.dart';
import '../../core/constants/app_constants.dart';

/// Helper to retrieve a JWT from the current Appwrite session.
/// Import this where needed, or pass the JWT string directly.
import 'package:appwrite/appwrite.dart' show Account;

/// Servicio que se comunica con el servidor de IA local.
/// Envía el video/imagen capturado al servidor corriendo en la misma red
/// y recibe la identificación del pez con todos sus metadatos.
class IdentifyService {
  /// Envía un video (o una imagen extraída de él) al servidor de IA local.
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
  /// [userId] - ID del usuario (legacy field)
  /// [notes] - Notas adicionales del pescador
  /// [confidenceThreshold] - Umbral de confianza para formulario manual
  /// [jwt] - Optional JWT token for server-side auth
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
    String? userId,
    String? notes,
    double? confidenceThreshold,
    String? jwt,
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

      // ── JWT auth header ──────────────────────────────────────────────
      if (jwt != null && jwt.isNotEmpty) {
        request.headers['Authorization'] = 'Bearer $jwt';
      }

      // ── Correlation ID for distributed tracing ──────────────────────
      final correlationId = const Uuid().v4();
      request.headers['X-Request-ID'] = correlationId;

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
      if (userId != null) request.fields['user_id'] = userId;
      if (notes != null) request.fields['notes'] = notes;

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
    } on TimeoutException {
      throw IdentifyException(
        'El servidor tardó demasiado en responder',
        detail:
            'La solicitud superó los 90 segundos. '
            'Verifica que el servidor en ${AppConstants.aiServerUrl} '
            'esté funcionando correctamente y que tu conexión sea estable.',
      );
    } on SocketException {
      throw IdentifyException(
        'No se pudo conectar al servidor de IA',
        detail:
            'Verifica que el servidor local esté corriendo en ${AppConstants.aiServerUrl} '
            'y que tu teléfono esté en la misma red WiFi.',
      );
    } on http.ClientException catch (e) {
      throw IdentifyException(
        'Error de conexión con el servidor',
        detail: 'No se pudo enviar el video: ${e.message}',
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
  /// [jwt] - Optional JWT token for server-side auth
  Future<IdentifyResult> identifyTest({String? jwt}) async {
    try {
      final uri = Uri.parse(
        '${AppConstants.aiServerUrl}${AppConstants.identifyEndpoint}/test',
      );

      final headers = <String, String>{};
      if (jwt != null && jwt.isNotEmpty) {
        headers['Authorization'] = 'Bearer $jwt';
      }

      final response = await http.get(uri, headers: headers).timeout(
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
