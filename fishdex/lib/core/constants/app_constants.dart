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
  // AI SERVER - LOCAL
  // ===========================================================================
  
  /// IP LAN de la computadora donde corre el servidor AI.
  /// Cambiar a la IP de tu máquina si cambia la red WiFi.
  static const String _serverLanIp = '192.168.103.145';
  static const int _serverPort = 8000;

  /// URL para emulador Android (10.0.2.2 redirige a localhost del host)
  static const String _emulatorUrl = 'http://10.0.2.2:$_serverPort';

  /// URL para teléfono físico en la misma red WiFi
  static const String _physicalDeviceUrl = 'http://$_serverLanIp:$_serverPort';

  /// Detección automática: si corre en emulador usa 10.0.2.2,
  /// si corre en dispositivo físico usa la IP LAN del servidor.
  /// Para forzar una u otra, cambia [_forcePhysicalDevice].
  ///
  /// NOTA: Pon esto en true para instalar en tu teléfono real.
  static const bool _forcePhysicalDevice = true;

  /// URL activa del servidor de IA (se resuelve según entorno)
  static String get aiServerUrl {
    if (_forcePhysicalDevice) return _physicalDeviceUrl;
    // En Android podríamos detectar el emulador, pero como constante
    // usamos la URL de dispositivo físico por defecto.
    return _physicalDeviceUrl;
  }

  // PRODUCCIÓN (Hugging Face - descomentar para deploy remoto)
  // static const String aiServerUrl = 'https://danielaguilarr-fishdex-fish-detector.hf.space';
  
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
  
  /// Radio máximo para matching de fish_id (metros) - 5km
  static const double fishMatchRadiusMeters = 5000.0;

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
}
