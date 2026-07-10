import 'env_config.dart';

/// Constantes de configuración de FishDex
class AppConstants {
  AppConstants._();

  // ===========================================================================
  // APPWRITE  (values come from compile-time --dart-define flags)
  // ===========================================================================
  
  /// Endpoint de Appwrite (cambiar para producción via --dart-define)
  static const String appwriteEndpoint = EnvConfig.appwriteEndpoint;
  
  /// Project ID en Appwrite
  static const String appwriteProjectId = EnvConfig.appwriteProjectId;
  
  /// Database ID
  static const String databaseId = EnvConfig.databaseId;

  // ===========================================================================
  // COLECCIONES (Collection IDs)
  // ===========================================================================
  
  static const String usersCollection = 'users';
  static const String fishIndividualsCollection = 'fish_individuals';
  static const String fishSightingsCollection = 'fish_sightings';
  static const String achievementsCollection = 'achievements';
  static const String userAchievementsCollection = 'user_achievements';
  static const String leaderboardsCollection = 'leaderboards';
  static const String fishingSpotsCollection = 'fishing_spots';
  static const String modelVersionsCollection = 'model_versions';

  /// Identification jobs collection (v2 job-based flow)
  static const String identificationJobsCollection = 'identification_jobs';
  
  /// Media files tracking collection
  static const String mediaFilesCollection = 'media_files';
  
  /// Fishing areas collection  
  static const String fishingAreasCollection = 'fishing_areas';

  // ===========================================================================
  // STORAGE BUCKETS
  // Legacy (v1) - kept for backward compatibility
  // ===========================================================================
  
  /// Bucket único para videos y fotos (límite plan gratuito)
  static const String fishVideosBucket = 'fish_photos';
  static const String fishPhotosBucket = 'fish_photos';
  @Deprecated('Use userAvatarsBucketV2 instead')
  static const String userAvatarsBucket = 'fish_photos';

  // ===========================================================================
  // STORAGE BUCKETS (v2 - separated by purpose)
  // NOTE: Free plan only allows 1 bucket. All point to 'fish_photos' for now.
  // When you upgrade to a paid plan, create separate buckets and update these.
  // ===========================================================================
  
  /// Bucket for raw capture videos (before AI processing)
  static const String captureRawVideosBucket = 'fish_photos';
  
  /// Bucket for processed frames (cropped fish images)
  static const String captureFramesBucket = 'fish_photos';
  
  /// Bucket for fish reference images (best frames per individual)
  static const String fishReferenceImagesBucket = 'fish_photos';
  
  /// Bucket for user avatar images
  static const String userAvatarsBucketV2 = 'fish_photos';
  
  /// Bucket for data exports
  static const String exportsBucket = 'fish_photos';

  // ===========================================================================
  // AI SERVER (value comes from compile-time --dart-define)
  // ===========================================================================
  
  /// URL del servidor AI, configurable vía --dart-define=AI_SERVER_URL=...
  static const String aiServerUrl = EnvConfig.aiServerUrl;

  /// Secreto de cliente para el servidor AI, configurable vía --dart-define=AI_SERVER_SECRET=...
  static const String aiServerSecret = EnvConfig.aiServerSecret;
  
  /// Endpoint de identificación
  static const String identifyEndpoint = '/api/v1/identify';

  /// Endpoint for searching nearby fishing areas
  static const String areasSearchEndpoint = '/api/v1/areas/search';

  /// Endpoint for getting all species list
  static const String speciesListEndpoint = '/api/v1/species';

  // ===========================================================================
  // GAMIFICACIÓN
  // ===========================================================================
  
  /// XP base por avistamiento de pez común
  static const int xpBaseCommon = 10;
  static const int xpBaseUncommon = 25;
  static const int xpBaseRare = 50;
  static const int xpBaseLegendary = 100;
  
  /// Bonus XP por pez nuevo
  static const int xpNewFishBonus = 50;
  
  /// Fórmula de XP para siguiente nivel: baseXP * nivel^factor
  static const int xpBaseForLevel = 100;
  static const double xpLevelFactor = 1.5;
  
  /// Duración máxima de video (segundos)
  static const int maxVideoDurationSeconds = 10;
  
  /// Tamaño máximo de video (MB)
  static const int maxVideoSizeMB = 50;

  // ===========================================================================
  // MAPA
  // ===========================================================================
  
  /// Radio de geofencing para notificación de pez raro (metros)
  static const double geofenceRadiusMeters = 500.0;
  
  /// Zoom inicial del mapa
  static const double mapDefaultZoom = 14.0;
  
  /// Zoom mínimo
  static const double mapMinZoom = 5.0;
  
  /// Zoom máximo
  static const double mapMaxZoom = 18.0;

  // ===========================================================================
  // SISTEMA DE ROLES
  // ===========================================================================
  
  /// Radio máximo para matching de fish_id (metros) — reduced from 5 km to 2 km
  static const double fishMatchRadiusMeters = 2000.0;

  /// Umbral de confianza de IA para auto-rellenar campos
  /// Si confidence < este valor, se muestra formulario manual
  static const double aiConfidenceThreshold = 0.70;

  /// Colección de solicitudes de aprobación
  static const String approvalRequestsCollection = 'approval_requests';

  // ===========================================================================
  // APPWRITE FUNCTIONS
  // ===========================================================================

  /// ID de la función de matching de fish_id
  static const String matchFishIdFunctionId = 'match-fish-id';

  /// ID de la función de capturas filtradas por rol
  static const String getCapturesByRoleFunctionId = 'get-captures-by-role';

  /// ID de la función de gestión de aprobaciones
  static const String manageApprovalFunctionId = 'manage-approval';

  /// ID of the XP awarding function
  static const String awardXpFunctionId = 'award-xp';
}
