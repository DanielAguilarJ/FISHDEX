import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api/local_api_client.dart';
import '../../core/providers/api_providers.dart';
import '../../core/enums/user_role.dart';
import '../models/user_role_model.dart';

/// Local implementation of RolesRepository that queries the local AI Server instead of Appwrite.
class RolesRepository {
  final LocalApiClient _apiClient;

  RolesRepository({required LocalApiClient apiClient}) : _apiClient = apiClient;

  /// Obtiene el modelo de rol de un usuario por su ID
  Future<UserRoleModel> getUserRole(String userId) async {
    try {
      final response = await _apiClient.get('/api/v1/auth/me');
      if (response != null) {
        final role = response['role'] as String? ?? 'fisherman';
        if (role == 'researcher') {
          return UserRoleModel(
            userId: userId,
            role: UserRole.researcher,
            approvalStatus: ApprovalStatus.approved, // Auto-approved for local simplicity
          );
        } else if (role == 'admin') {
          return UserRoleModel(
            userId: userId,
            role: UserRole.admin,
            approvalStatus: ApprovalStatus.approved,
          );
        }
      }
      return UserRoleModel.fisherman(userId);
    } catch (e) {
      debugPrint('⚠️ Error obteniendo rol de usuario local: $e');
      return UserRoleModel.fisherman(userId);
    }
  }

  /// Guarda el rol del usuario (mocked locally)
  Future<void> saveUserRole(UserRoleModel roleModel, {String? name}) async {
    // Already saved in local SQLite during registration
  }

  /// Crea una solicitud de acceso como investigador (mocked locally)
  Future<void> requestResearcherAccess({
    required String userId,
    required String username,
    required String institution,
    required String reason,
  }) async {
    // For local dev, immediately grant access
  }

  /// Obtiene todas las solicitudes pendientes de aprobación (mocked locally)
  Future<List<Map<String, dynamic>>> getPendingApprovals() async {
    return [];
  }

  /// Aprueba un investigador (mocked locally)
  Future<bool> approveResearcher({
    required String userId,
    required String requestId,
    required String adminId,
  }) async {
    return true;
  }

  /// Rechaza un investigador (mocked locally)
  Future<bool> rejectResearcher({
    required String userId,
    required String requestId,
    required String adminId,
    String? rejectionReason,
  }) async {
    return true;
  }

  /// Lista todos los usuarios con rol researcher (mocked locally)
  Future<List<UserRoleModel>> getAllResearchers() async {
    return [];
  }
}

/// Riverpod Provider
final rolesRepositoryProvider = Provider<RolesRepository>((ref) {
  final apiClient = ref.watch(localApiClientProvider);
  return RolesRepository(apiClient: apiClient);
});
