import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/enums/user_role.dart';
import '../models/user_role_model.dart';
import '../repositories/roles_repository.dart';
import '../../features/auth/providers/auth_provider.dart';

// =============================================================================
// SERVICIO DE CONTROL DE ACCESO POR ROL
// =============================================================================

/// Servicio que controla el acceso basado en roles.
/// Cachea el rol del usuario en memoria y SharedPreferences para acceso rápido.
class RoleGuardService {
  UserRoleModel? _currentUserRole;

  /// Rol actual del usuario en caché
  UserRoleModel? get currentRole => _currentUserRole;

  /// Si el usuario actual es fisherman
  bool get isFisherman => _currentUserRole?.role == UserRole.fisherman;

  /// Si el usuario actual es researcher aprobado
  bool get isResearcher =>
      _currentUserRole?.role == UserRole.researcher &&
      _currentUserRole?.approvalStatus == ApprovalStatus.approved;

  /// Si el usuario actual es admin
  bool get isAdmin => _currentUserRole?.role == UserRole.admin;

  /// Si el usuario está pendiente de aprobación
  bool get isPendingApproval => _currentUserRole?.isPendingApproval ?? false;

  /// Si tiene acceso completo a la app
  bool get hasFullAccess => _currentUserRole?.hasFullAccess ?? false;

  /// Si puede ver ubicaciones exactas de otros usuarios
  bool get canViewAllLocations =>
      _currentUserRole?.role.canViewAllLocations ?? false;

  /// Si puede ver datos extendidos de capturas
  bool get canViewExtendedData =>
      _currentUserRole?.role.canViewExtendedData ?? false;

  /// Si puede gestionar usuarios (aprobar/rechazar)
  bool get canManageUsers =>
      _currentUserRole?.role.canManageUsers ?? false;

  // ===========================================================================
  // INICIALIZACIÓN Y CACHE
  // ===========================================================================

  /// Inicializa el servicio cargando el rol del usuario desde Appwrite o caché
  Future<UserRoleModel> initialize(
    String userId,
    RolesRepository rolesRepository,
  ) async {
    try {
      // Intentar obtener del servidor
      _currentUserRole = await rolesRepository.getUserRole(userId);
      // Cachear localmente
      await _cacheRole(_currentUserRole!);
    } catch (e) {
      debugPrint('⚠️ Error al inicializar RoleGuardService: $e');
      // Intentar cargar de caché local
      _currentUserRole = await _loadCachedRole(userId);
    }

    return _currentUserRole ?? UserRoleModel.fisherman(userId);
  }

  /// Actualiza el rol en caché (ej: cuando se aprueba un researcher)
  Future<void> updateRole(UserRoleModel newRole) async {
    _currentUserRole = newRole;
    await _cacheRole(newRole);
  }

  /// Limpia el caché de rol (al hacer logout)
  Future<void> clear() async {
    _currentUserRole = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('cached_user_role');
    await prefs.remove('cached_approval_status');
    await prefs.remove('cached_role_user_id');
  }

  // ===========================================================================
  // VERIFICACIÓN DE PERMISOS
  // ===========================================================================

  /// Verifica si el usuario actual puede ver los datos completos de una captura
  bool canViewCaptureDetails(String captureUserId) {
    if (_currentUserRole == null) return false;

    // Admin y researcher ven todo
    if (canViewAllLocations) return true;

    // Fisherman solo ve sus propias capturas
    return _currentUserRole!.userId == captureUserId;
  }

  /// Verifica si se debe mostrar un marker anónimo para una captura
  bool shouldShowAnonymousMarker(String captureUserId) {
    if (_currentUserRole == null) return true;

    // Si no es fisherman, no necesita markers anónimos
    if (canViewAllLocations) return false;

    // Fisherman: marker anónimo si la captura es de otro usuario
    return _currentUserRole!.userId != captureUserId;
  }

  // ===========================================================================
  // PERSISTENCIA LOCAL
  // ===========================================================================

  Future<void> _cacheRole(UserRoleModel role) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('cached_user_role', role.role.name);
    await prefs.setString('cached_approval_status', role.approvalStatus.name);
    await prefs.setString('cached_role_user_id', role.userId);
  }

  Future<UserRoleModel?> _loadCachedRole(String userId) async {
    final prefs = await SharedPreferences.getInstance();
    final cachedUserId = prefs.getString('cached_role_user_id');

    if (cachedUserId != userId) return null;

    final roleStr = prefs.getString('cached_user_role');
    final statusStr = prefs.getString('cached_approval_status');

    if (roleStr == null) return null;

    return UserRoleModel(
      userId: userId,
      role: UserRole.fromString(roleStr),
      approvalStatus: ApprovalStatus.fromString(statusStr ?? 'approved'),
    );
  }
}

// =============================================================================
// PROVIDERS
// =============================================================================

/// Provider singleton del RoleGuardService
final roleGuardServiceProvider = Provider<RoleGuardService>((ref) {
  return RoleGuardService();
});

/// Provider del rol del usuario actual (se inicializa en login/splash)
final currentUserRoleProvider = FutureProvider<UserRoleModel>((ref) async {
  try {
    final user = ref.watch(authStateProvider).value;
    if (user == null) {
      return UserRoleModel.fisherman('unknown');
    }
    final rolesRepo = ref.read(rolesRepositoryProvider);
    final roleGuard = ref.read(roleGuardServiceProvider);

    return await roleGuard.initialize(user.id, rolesRepo);
  } catch (e) {
    debugPrint('⚠️ Error en currentUserRoleProvider: $e');
    return UserRoleModel.fisherman('unknown');
  }
});
