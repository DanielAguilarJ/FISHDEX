/// Constantes de configuración de FishDex
class AppConstants {
  AppConstants._();

  // ===========================================================================
  // APPWRITE
  // ===========================================================================
  
  /// Endpoint de Appwrite (cambiar para producción)
  static const String appwriteEndpoint = 'https://fra.cloud.appwrite.io/v1';
  
  /// Project ID en Appwrite
  static const String appwriteProjectId = '6a43bdeb0026006ff2f8';
  
  /// Database ID
  static const String databaseId = 'fishdex_db';

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

  // ===========================================================================
  // STORAGE BUCKETS
  // ===========================================================================
  
  /// Bucket único para videos y fotos (límite plan gratuito)
  static const String fishVideosBucket = 'fish_photos';
  static const String fishPhotosBucket = 'fish_photos';
  static const String userAvatarsBucket = 'fish_photos';

  // ===========================================================================
  // AI SERVER
  // ===========================================================================
  
  /// URL del servidor de IA en Hugging Face Spaces (producción)
  /// El Space puede tardar ~30s en despertar si estuvo inactivo 48h
  static const String aiServerUrl =
      'https://danielaguilarr-fishdex-fish-detector.hf.space';
  
  /// Endpoint de identificación
  static const String identifyEndpoint = '/api/v1/identify';

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
}
