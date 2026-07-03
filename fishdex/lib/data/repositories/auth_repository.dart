import 'package:appwrite/appwrite.dart';
import 'package:appwrite/models.dart' as models;

/// Repositorio de autenticación - abstrae las llamadas a Appwrite Auth
class AuthRepository {
  final Account _account;

  AuthRepository({required Account account}) : _account = account;

  /// Obtener el usuario actual (null si no hay sesión).
  /// Lanza excepción si el error NO es 401 (problemas de red o servidor).
  Future<models.User?> getCurrentUser() async {
    try {
      return await _account.get();
    } on AppwriteException catch (e) {
      if (e.code == 401) return null; // Sin sesión activa — respuesta esperada
      rethrow; // Otro error (500, red) → auth_provider lo convierte en NetworkAuthException
    }
  }

  /// Iniciar sesión con email y contraseña
  Future<models.Session> login({
    required String email,
    required String password,
  }) async {
    return await _account.createEmailPasswordSession(
      email: email,
      password: password,
    );
  }

  /// Registrar un nuevo usuario
  Future<models.User> register({
    required String email,
    required String password,
    required String name,
  }) async {
    return await _account.create(
      userId: ID.unique(),
      email: email,
      password: password,
      name: name,
    );
  }

  /// Cerrar sesión actual
  Future<void> logout() async {
    await _account.deleteSession(sessionId: 'current');
  }

  /// Cerrar todas las sesiones
  Future<void> logoutAll() async {
    await _account.deleteSessions();
  }
}
