import '../../core/enums/user_role.dart';

/// Modelo extendido de usuario con rol y estado de aprobación
class UserRoleModel {
  final String userId;
  final UserRole role;
  final ApprovalStatus approvalStatus;
  final String? institution;
  final String? requestReason;
  final DateTime? approvedAt;
  final String? approvedBy;
  final DateTime? requestedAt;

  const UserRoleModel({
    required this.userId,
    required this.role,
    required this.approvalStatus,
    this.institution,
    this.requestReason,
    this.approvedAt,
    this.approvedBy,
    this.requestedAt,
  });

  /// Si el usuario tiene acceso completo a la app
  bool get hasFullAccess {
    if (role == UserRole.fisherman) return true;
    if (role == UserRole.admin) return true;
    return role == UserRole.researcher &&
        approvalStatus == ApprovalStatus.approved;
  }

  /// Si está esperando aprobación
  bool get isPendingApproval =>
      role == UserRole.researcher && approvalStatus == ApprovalStatus.pending;

  /// Si fue rechazado
  bool get isRejected =>
      role == UserRole.researcher && approvalStatus == ApprovalStatus.rejected;

  /// Crear desde un mapa (documento Appwrite)
  factory UserRoleModel.fromMap(Map<String, dynamic> map) {
    return UserRoleModel(
      userId: map['userId'] as String? ?? '',
      role: UserRole.fromString(map['role'] as String? ?? 'fisherman'),
      approvalStatus: ApprovalStatus.fromString(
          map['approval_status'] as String? ?? 'approved'),
      institution: map['institution'] as String?,
      requestReason: map['request_reason'] as String?,
      approvedAt: map['approved_at'] != null
          ? DateTime.tryParse(map['approved_at'] as String)
          : null,
      approvedBy: map['approved_by'] as String?,
      requestedAt: map['requested_at'] != null
          ? DateTime.tryParse(map['requested_at'] as String)
          : null,
    );
  }

  /// Convertir a mapa para guardar en Appwrite
  Map<String, dynamic> toMap() {
    return {
      'userId': userId,
      'role': role.name,
      'approval_status': approvalStatus.name,
      if (institution != null) 'institution': institution,
      if (requestReason != null) 'request_reason': requestReason,
      if (approvedAt != null) 'approved_at': approvedAt!.toIso8601String(),
      if (approvedBy != null) 'approved_by': approvedBy,
      if (requestedAt != null) 'requested_at': requestedAt!.toIso8601String(),
    };
  }

  /// Crear un fisherman aprobado (default para onboarding)
  factory UserRoleModel.fisherman(String userId) {
    return UserRoleModel(
      userId: userId,
      role: UserRole.fisherman,
      approvalStatus: ApprovalStatus.approved,
    );
  }

  /// Crear un researcher pendiente (al registrarse)
  factory UserRoleModel.pendingResearcher({
    required String userId,
    required String institution,
    required String reason,
  }) {
    return UserRoleModel(
      userId: userId,
      role: UserRole.researcher,
      approvalStatus: ApprovalStatus.pending,
      institution: institution,
      requestReason: reason,
      requestedAt: DateTime.now(),
    );
  }

  UserRoleModel copyWith({
    String? userId,
    UserRole? role,
    ApprovalStatus? approvalStatus,
    String? institution,
    String? requestReason,
    DateTime? approvedAt,
    String? approvedBy,
    DateTime? requestedAt,
  }) {
    return UserRoleModel(
      userId: userId ?? this.userId,
      role: role ?? this.role,
      approvalStatus: approvalStatus ?? this.approvalStatus,
      institution: institution ?? this.institution,
      requestReason: requestReason ?? this.requestReason,
      approvedAt: approvedAt ?? this.approvedAt,
      approvedBy: approvedBy ?? this.approvedBy,
      requestedAt: requestedAt ?? this.requestedAt,
    );
  }
}
