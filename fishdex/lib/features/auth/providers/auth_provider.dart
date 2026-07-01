import 'dart:async';
import 'package:appwrite/appwrite.dart';
import 'package:appwrite/models.dart' as models;
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../data/repositories/auth_repository.dart';

/// Excepción personalizada para errores de red/timeout
class NetworkAuthException implements Exception {
  final String message;
  const NetworkAuthException(this.message);
  @override
  String toString() => 'NetworkAuthException: $message';
}

/// Estado de autenticación - observa la sesión actual del usuario
/// Maneja timeout de 6s y diferencia entre error 401 (sin sesión) vs error de red.
final authStateProvider = FutureProvider<models.User?>((ref) async {
  final authRepo = ref.watch(authRepositoryProvider);
  try {
    final user = await authRepo.getCurrentUser().timeout(
      const Duration(seconds: 6),
      onTimeout: () {
        throw const NetworkAuthException(
          'Timeout al verificar sesión (6s)',
        );
      },
    );
    return user;
  } on AppwriteException catch (e) {
    debugPrint('🔐 Auth check AppwriteException: [${e.code}] ${e.message}');
    if (e.code == 401) {
      // 401 = El servidor respondió pero no hay sesión activa
      return null;
    }
    // Otros códigos (500, etc.) → posible error de red/servidor
    throw NetworkAuthException('Appwrite error [${e.code}]: ${e.message}');
  } on NetworkAuthException {
    // Re-lanzar para que Splash la maneje diferente
    rethrow;
  } on TimeoutException {
    throw const NetworkAuthException('Timeout al contactar servidor');
  } catch (e) {
    debugPrint('🔐 Auth check error inesperado: $e');
    // Errores de red (SocketException, etc.) → lanzar NetworkAuthException
    throw NetworkAuthException('Error de conexión: $e');
  }
});

/// Provider del repositorio de autenticación
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final account = ref.watch(appwriteAccountProvider);
  return AuthRepository(account: account);
});

/// Provider para la acción de login
final loginProvider = FutureProvider.family<models.Session, LoginParams>(
  (ref, params) async {
    final authRepo = ref.watch(authRepositoryProvider);
    final session = await authRepo.login(
      email: params.email,
      password: params.password,
    );
    // Invalidar el estado de auth para que se actualice
    ref.invalidate(authStateProvider);
    return session;
  },
);

/// Provider para la acción de registro
final registerProvider = FutureProvider.family<models.User, RegisterParams>(
  (ref, params) async {
    final authRepo = ref.watch(authRepositoryProvider);
    final user = await authRepo.register(
      email: params.email,
      password: params.password,
      name: params.name,
    );
    // Auto-login después del registro
    await authRepo.login(email: params.email, password: params.password);
    ref.invalidate(authStateProvider);
    return user;
  },
);

/// Provider para logout
final logoutProvider = FutureProvider<void>((ref) async {
  final authRepo = ref.watch(authRepositoryProvider);
  await authRepo.logout();
  ref.invalidate(authStateProvider);
});

/// Parámetros para login
class LoginParams {
  final String email;
  final String password;

  const LoginParams({required this.email, required this.password});
}

/// Parámetros para registro
class RegisterParams {
  final String email;
  final String password;
  final String name;

  const RegisterParams({
    required this.email,
    required this.password,
    required this.name,
  });
}
