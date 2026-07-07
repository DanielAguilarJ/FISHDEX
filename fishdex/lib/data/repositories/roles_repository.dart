import 'package:appwrite/appwrite.dart';
import 'package:flutter/foundation.dart';
import '../../core/constants/app_constants.dart';
import '../models/user_role_model.dart';

// =============================================================================
// REPOSITORIO DE ROLES Y APROBACIONES
// =============================================================================

/// Repositorio que gestiona los roles de usuario y el flujo de aprobación
/// de investigadores. Interactúa con la colección `users` y
/// `approval_requests` en Appwrite.
class RolesRepository {
  final Databases _databases;

  RolesRepository({required Databases databases}) : _databases = databases;

  // ===========================================================================
  // CONSULTAR ROL DEL USUARIO
  // ===========================================================================

  /// Obtiene el modelo de rol de un usuario por su ID
  Future<UserRoleModel> getUserRole(String userId) async {
    try {
      final doc = await _databases.getDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: userId,
      );

      return UserRoleModel.fromMap(doc.data);
    } catch (e) {
      debugPrint('⚠️ Error obteniendo rol de usuario: $e');
      // Default: fisherman aprobado (fallback seguro)
      return UserRoleModel.fisherman(userId);
    }
  }

  // ===========================================================================
  // REGISTRAR CON ROL
  // ===========================================================================

  /// Guarda el rol del usuario al registrarse.
  /// Para fisherman: approval_status = approved (acceso inmediato)
  /// Para researcher: approval_status = pending (requiere aprobación)
  Future<void> saveUserRole(UserRoleModel roleModel) async {
    try {
      // Intentar actualizar si ya existe
      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: roleModel.userId,
        data: roleModel.toMap(),
      );
    } on AppwriteException catch (e) {
      if (e.code == 404) {
        // No existe, crear nuevo
        await _databases.createDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.usersCollection,
          documentId: roleModel.userId,
          data: {
            ...roleModel.toMap(),
            'createdAt': DateTime.now().toIso8601String(),
            'total_xp': 0,
            'level': 1,
            'total_sightings': 0,
            'unique_species': 0,
            'rare_fish_count': 0,
            'legendary_fish_count': 0,
            'last_activity': DateTime.now().toIso8601String(),
          },
        );
      } else {
        rethrow;
      }
    }
  }

  // ===========================================================================
  // SOLICITAR ACCESO COMO INVESTIGADOR
  // ===========================================================================

  /// Crea una solicitud de acceso como investigador
  Future<void> requestResearcherAccess({
    required String userId,
    required String username,
    required String institution,
    required String reason,
  }) async {
    try {
      await _databases.createDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.approvalRequestsCollection,
        documentId: ID.unique(),
        data: {
          'user_id': userId,
          'username': username,
          'institution': institution,
          'reason': reason,
          'status': 'pending',
          'requested_at': DateTime.now().toIso8601String(),
        },
      );
    } catch (e) {
      debugPrint('⚠️ Error al solicitar acceso como researcher: $e');
      rethrow;
    }
  }

  // ===========================================================================
  // GESTIÓN DE APROBACIONES (ADMIN)
  // ===========================================================================

  /// Obtiene todas las solicitudes pendientes de aprobación
  Future<List<Map<String, dynamic>>> getPendingApprovals() async {
    try {
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.approvalRequestsCollection,
        queries: [
          Query.equal('status', 'pending'),
          Query.orderDesc('requested_at'),
        ],
      );

      return response.documents.map((doc) {
        final data = doc.data;
        data['\$id'] = doc.$id;
        return data;
      }).toList();
    } catch (e) {
      debugPrint('⚠️ Error obteniendo solicitudes pendientes: $e');
      return [];
    }
  }

  /// Aprueba un investigador
  Future<bool> approveResearcher({
    required String userId,
    required String requestId,
    required String adminId,
  }) async {
    try {
      // Actualizar el estado del usuario
      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: userId,
        data: {
          'approval_status': 'approved',
          'approved_at': DateTime.now().toIso8601String(),
          'approved_by': adminId,
        },
      );

      // Actualizar la solicitud
      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.approvalRequestsCollection,
        documentId: requestId,
        data: {
          'status': 'approved',
          'reviewed_at': DateTime.now().toIso8601String(),
          'reviewed_by': adminId,
        },
      );

      return true;
    } catch (e) {
      debugPrint('⚠️ Error al aprobar investigador: $e');
      return false;
    }
  }

  /// Rechaza un investigador
  Future<bool> rejectResearcher({
    required String userId,
    required String requestId,
    required String adminId,
    String? rejectionReason,
  }) async {
    try {
      // Actualizar el estado del usuario
      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: userId,
        data: {
          'approval_status': 'rejected',
          'approved_at': DateTime.now().toIso8601String(),
          'approved_by': adminId,
        },
      );

      // Actualizar la solicitud
      await _databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.approvalRequestsCollection,
        documentId: requestId,
        data: {
          'status': 'rejected',
          'reviewed_at': DateTime.now().toIso8601String(),
          'reviewed_by': adminId,
          if (rejectionReason != null) 'rejection_reason': rejectionReason,
        },
      );

      return true;
    } catch (e) {
      debugPrint('⚠️ Error al rechazar investigador: $e');
      return false;
    }
  }

  // ===========================================================================
  // OBTENER TODOS LOS RESEARCHERS (ADMIN)
  // ===========================================================================

  /// Lista todos los usuarios con rol researcher
  Future<List<UserRoleModel>> getAllResearchers() async {
    try {
      final response = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        queries: [
          Query.equal('role', 'researcher'),
          Query.orderDesc('createdAt'),
        ],
      );

      return response.documents
          .map((doc) => UserRoleModel.fromMap(doc.data))
          .toList();
    } catch (e) {
      debugPrint('⚠️ Error obteniendo researchers: $e');
      return [];
    }
  }
}
