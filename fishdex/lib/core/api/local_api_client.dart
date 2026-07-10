import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/foundation.dart';
import '../../core/constants/app_constants.dart';

class LocalApiClient {
  final String baseUrl;
  final String clientSecret;
  String? _token;

  LocalApiClient({
    required this.baseUrl,
    required this.clientSecret,
  });

  /// Initialize the client by loading the saved auth token from SharedPreferences.
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('local_auth_token');
    debugPrint('🔑 LocalApiClient initialized with token: ${_token != null ? "exists" : "none"}');
  }

  bool get isAuthenticated => _token != null;
  String? get token => _token;

  /// Save token to memory and SharedPreferences.
  Future<void> setToken(String? token) async {
    _token = token;
    final prefs = await SharedPreferences.getInstance();
    if (token != null) {
      await prefs.setString('local_auth_token', token);
    } else {
      await prefs.remove('local_auth_token');
    }
  }

  /// Get headers for request.
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
      
      // Add video file
      final stream = http.ByteStream(file.openRead());
      final length = await file.length();
      final multipartFile = http.MultipartFile(
        'video',
        stream,
        length,
        filename: file.path.split('/').last,
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
