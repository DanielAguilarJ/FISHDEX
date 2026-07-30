import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:flutter/foundation.dart';

import '../storage/secure_token_store.dart';

/// HTTP client for the FishDex AI server.
///
/// Sends both credentials the server understands:
/// * `X-FishDex-Client-Secret` — identifies the application build.
/// * `Authorization: Bearer <token>` — identifies the signed-in user.
///
/// The client secret alone is not sufficient for per-user endpoints; the server
/// requires the session token for anything that reads or writes user data.
class LocalApiClient {
  final String baseUrl;
  final String clientSecret;
  final SecureTokenStore _tokenStore;

  String? _token;

  LocalApiClient({
    required this.baseUrl,
    required this.clientSecret,
    SecureTokenStore? tokenStore,
  }) : _tokenStore = tokenStore ?? SecureTokenStore();

  /// Loads the persisted session token from encrypted storage.
  ///
  /// Migrates a token left in `SharedPreferences` by an earlier build.
  Future<void> init() async {
    _token = await _tokenStore.read();
    debugPrint('LocalApiClient initialised (session ${_token != null ? "restored" : "absent"})');
  }

  bool get isAuthenticated => _token != null;
  String? get token => _token;

  /// Persists [token] to encrypted storage, or clears it when `null`.
  Future<void> setToken(String? token) async {
    _token = token;
    if (token == null) {
      await _tokenStore.clear();
    } else {
      await _tokenStore.write(token);
    }
  }

  /// Builds request headers, including both credentials when available.
  Map<String, String> _getHeaders({bool isJson = true}) {
    final headers = <String, String>{
      'X-FishDex-Client-Secret': clientSecret,
    };
    if (isJson) {
      headers['Content-Type'] = 'application/json';
    }
    if (_token != null) {
      headers['Authorization'] = 'Bearer $_token';
    }
    return headers;
  }

  /// GET request
  Future<dynamic> get(String path) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final response = await http.get(uri, headers: _getHeaders());
      return _handleResponse(response);
    } catch (e) {
      debugPrint('❌ LocalApiClient GET error ($path): $e');
      rethrow;
    }
  }

  /// POST request
  Future<dynamic> post(String path, Map<String, dynamic> body) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final response = await http.post(
        uri,
        headers: _getHeaders(),
        body: jsonEncode(body),
      );
      return _handleResponse(response);
    } catch (e) {
      debugPrint('❌ LocalApiClient POST error ($path): $e');
      rethrow;
    }
  }

  /// Multipart POST request (for video uploading)
  Future<dynamic> multipartPost(
    String path, {
    required File file,
    required Map<String, String> fields,
  }) async {
    final uri = Uri.parse('$baseUrl$path');
    try {
      final request = http.MultipartRequest('POST', uri);
      request.headers.addAll(_getHeaders(isJson: false));

      // Add text fields
      request.fields.addAll(fields);

      // Infer correct MIME type from file extension so the server
      // never receives a generic application/octet-stream.
      final ext = file.path.split('.').last.toLowerCase();
      final videoExtensions = {
        'mp4': MediaType('video', 'mp4'),
        'mov': MediaType('video', 'quicktime'),
        'avi': MediaType('video', 'x-msvideo'),
        'mkv': MediaType('video', 'x-matroska'),
        '3gp': MediaType('video', '3gpp'),
        'webm': MediaType('video', 'webm'),
      };
      final imageExtensions = {
        'jpg': MediaType('image', 'jpeg'),
        'jpeg': MediaType('image', 'jpeg'),
        'png': MediaType('image', 'png'),
        'webp': MediaType('image', 'webp'),
        'heic': MediaType('image', 'heic'),
      };
      final contentType = videoExtensions[ext] ??
          imageExtensions[ext] ??
          MediaType('video', 'mp4'); // safe default: camera always records video

      debugPrint('📹 Uploading file: ${file.path.split('/').last}'
          ' | ext=$ext | contentType=$contentType');

      final stream = http.ByteStream(file.openRead());
      final length = await file.length();
      final multipartFile = http.MultipartFile(
        'video',
        stream,
        length,
        filename: file.path.split('/').last,
        contentType: contentType,
      );
      request.files.add(multipartFile);

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);
      return _handleResponse(response);
    } catch (e) {
      debugPrint('❌ LocalApiClient Multipart POST error ($path): $e');
      rethrow;
    }
  }

  dynamic _handleResponse(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return null;
      return jsonDecode(response.body);
    } else {
      String errMsg = 'Status code: ${response.statusCode}';
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map && decoded.containsKey('detail')) {
          errMsg = decoded['detail'].toString();
        }
      } catch (_) {}
      
      throw HttpException(
        'Server Error: $errMsg (code ${response.statusCode})',
        uri: response.request?.url,
      );
    }
  }
}
