/// Roles de usuario en FishDex
enum UserRole {
  fisherman,
  researcher,
  admin;

  /// Nombre para mostrar en la UI (español)
  String get displayName {
    switch (this) {
      case UserRole.fisherman:
        return 'Pescador';
      case UserRole.researcher:
        return 'Investigador';
      case UserRole.admin:
        return 'Administrador';
    }
  }

  /// Descripción del rol
  String get description {
    switch (this) {
      case UserRole.fisherman:
        return 'Registra tus capturas y contribuye a la ciencia';
      case UserRole.researcher:
        return 'Accede a datos completos para investigación';
      case UserRole.admin:
        return 'Gestiona usuarios y acceso al sistema';
    }
  }

  /// Si puede ver ubicaciones exactas de todos los usuarios
  bool get canViewAllLocations =>
      this == UserRole.researcher || this == UserRole.admin;

  /// Si puede ver datos extendidos de capturas
  bool get canViewExtendedData =>
      this == UserRole.researcher || this == UserRole.admin;

  /// Si puede aprobar/rechazar usuarios
  bool get canManageUsers => this == UserRole.admin;

  /// Si puede ver el historial completo de un fish_id
  bool get canViewFishHistory =>
      this == UserRole.researcher || this == UserRole.admin;

  /// Convierte un string a UserRole
  static UserRole fromString(String value) {
    switch (value.toLowerCase()) {
      case 'researcher':
        return UserRole.researcher;
      case 'admin':
        return UserRole.admin;
      case 'fisherman':
      default:
        return UserRole.fisherman;
    }
  }
}

/// Estado de aprobación del usuario
enum ApprovalStatus {
  approved,
  pending,
  rejected;

  /// Nombre para mostrar
  String get displayName {
    switch (this) {
      case ApprovalStatus.approved:
        return 'Aprobado';
      case ApprovalStatus.pending:
        return 'Pendiente';
      case ApprovalStatus.rejected:
        return 'Rechazado';
    }
  }

  /// Convierte un string a ApprovalStatus
  static ApprovalStatus fromString(String value) {
    switch (value.toLowerCase()) {
      case 'pending':
        return ApprovalStatus.pending;
      case 'rejected':
        return ApprovalStatus.rejected;
      case 'approved':
      default:
        return ApprovalStatus.approved;
    }
  }
}
