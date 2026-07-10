import 'dart:io';
import '../../core/api/local_api_client.dart';
import '../../core/models/local_models.dart';

/// Repositorio de autenticación local - abstrae las llamadas HTTP al servidor local de IA
class AuthRepository {
  final LocalApiClient _apiClient;

  AuthRepository({required LocalApiClient apiClient}) : _apiClient = apiClient;

  /// Obtener el usuario actual (null si no hay sesión).
  Future<LocalUser?> getCurrentUser() async {
    // If not authenticated (no token loaded/saved), return null immediately
    if (!_apiClient.isAuthenticated) return null;
    
    try {
      final response = await _apiClient.get('/api/v1/auth/me');
      if (response != null) {
        return LocalUser.fromJson(response as Map<String, dynamic>);
      }
      return null;
    } catch (e) {
      if (e is HttpException && e.message.contains('401')) {
        // Token has expired or is invalid
        await _apiClient.setToken(null);
        return null;
      }
      rethrow;
    }
  }

  /// Iniciar sesión con email y contraseña
  Future<LocalSession> login({
    required String email,
    required String password,
  }) async {
    final response = await _apiClient.post('/api/v1/auth/login', {
      'email': email,
      'password': password,
    });

    final token = response['token'] as String;
    final userMap = response['user'] as Map<String, dynamic>;
    final userId = userMap['id'] as String;

    // Persist session token in memory and local storage
    await _apiClient.setToken(token);

    return LocalSession(
      id: token,
      userId: userId,
    );
  }

  /// Registrar un nuevo usuario
  Future<LocalUser> register({
    required String email,
    required String password,
    required String name,
  }) async {
    final response = await _apiClient.post('/api/v1/auth/register', {
      'email': email,
      'password': password,
      'name': name,
      'role': 'fisherman', // Default role is fisherman
    });

    return LocalUser.fromJson(response as Map<String, dynamic>);
  }

  /// Cerrar sesión actual
  Future<void> logout() async {
    await _apiClient.setToken(null);
  }

  /// Cerrar todas las sesiones (mocked locally)
  Future<void> logoutAll() async {
    await _apiClient.setToken(null);
  }
}
