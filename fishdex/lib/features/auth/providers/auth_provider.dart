import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/providers/api_providers.dart';
import '../../../data/repositories/auth_repository.dart';
import '../../../core/models/local_models.dart';

/// Excepción personalizada para errores de red/timeout
class NetworkAuthException implements Exception {
  final String message;
  const NetworkAuthException(this.message);
  @override
  String toString() => 'NetworkAuthException: $message';
}

/// Estado de autenticación - observa la sesión actual del usuario
/// Maneja timeout de 6s y diferencia entre error de red vs sin sesión.
final authStateProvider = FutureProvider<LocalUser?>((ref) async {
  final apiClient = ref.watch(localApiClientProvider);
  
  // Ensure ApiClient finishes loading token from SharedPreferences on startup
  await apiClient.init();
  
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
  } on HttpException catch (e) {
    debugPrint('🔐 Auth check HttpException: ${e.message}');
    if (e.message.contains('401')) {
      return null;
    }
    throw NetworkAuthException('Error de servidor: ${e.message}');
  } on TimeoutException {
    throw const NetworkAuthException('Timeout al contactar servidor');
  } catch (e) {
    debugPrint('🔐 Auth check error inesperado: $e');
    throw NetworkAuthException('Error de conexión: $e');
  }
});

/// Provider del repositorio de autenticación
final authRepositoryProvider = Provider<AuthRepository>((ref) {
  final apiClient = ref.watch(localApiClientProvider);
  return AuthRepository(apiClient: apiClient);
});

/// Provider para la acción de login
final loginProvider = FutureProvider.family<LocalSession, LoginParams>(
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
final registerProvider = FutureProvider.family<LocalUser, RegisterParams>(
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
