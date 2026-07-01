import 'package:appwrite/appwrite.dart';
import 'package:appwrite/models.dart' as models;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../data/repositories/auth_repository.dart';

/// Estado de autenticación - observa la sesión actual del usuario
final authStateProvider = FutureProvider<models.User?>((ref) async {
  final authRepo = ref.watch(authRepositoryProvider);
  try {
    return await authRepo.getCurrentUser();
  } catch (e) {
    return null;
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
