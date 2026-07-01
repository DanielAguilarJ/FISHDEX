import 'package:flutter_local_notifications/flutter_local_notifications.dart';

// =============================================================================
// SERVICIO DE NOTIFICACIONES LOCALES
// =============================================================================

/// Servicio singleton para gestionar notificaciones locales en FishDex.
/// Muestra notificaciones de logros, subidas de nivel, avistamientos y peces raros.
class NotificationService {
  // Instancia singleton
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  // Plugin de notificaciones
  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  // Estado de inicialización
  bool _isInitialized = false;
  bool get isInitialized => _isInitialized;

  // IDs de canales de notificación (Android)
  static const String _channelIdAchievements = 'fishdex_achievements';
  static const String _channelIdLevelUp = 'fishdex_level_up';
  static const String _channelIdFishSpotted = 'fishdex_fish_spotted';
  static const String _channelIdRareFish = 'fishdex_rare_fish';

  // Contadores auto-incrementales para IDs de notificación
  int _notificationIdCounter = 0;

  // ===========================================================================
  // INICIALIZACIÓN
  // ===========================================================================

  /// Inicializar el servicio de notificaciones.
  /// Debe llamarse una vez al inicio de la app (en main.dart o similar).
  Future<void> initialize() async {
    if (_isInitialized) return;

    try {
      // Configuración para Android
      const androidSettings = AndroidInitializationSettings(
        '@mipmap/ic_launcher',
      );

      // Configuración para iOS/macOS
      const darwinSettings = DarwinInitializationSettings(
        requestAlertPermission: true,
        requestBadgePermission: true,
        requestSoundPermission: true,
      );

      // Configuración general
      const initSettings = InitializationSettings(
        android: androidSettings,
        iOS: darwinSettings,
        macOS: darwinSettings,
      );

      // Inicializar el plugin
      await _plugin.initialize(
        initSettings,
        onDidReceiveNotificationResponse: _onNotificationTapped,
      );

      _isInitialized = true;
    } catch (e) {
      // Si falla la inicialización, no crashear la app
      _isInitialized = false;
    }
  }

  /// Callback cuando el usuario toca una notificación
  void _onNotificationTapped(NotificationResponse response) {
    // Se puede usar el payload para navegar a la pantalla correspondiente
    // Por ejemplo: 'achievement:achievement_id' o 'fish:fish_id'
    final payload = response.payload;
    if (payload != null) {
      // TODO: Implementar navegación según payload
      // Se podría usar un StreamController para emitir eventos de navegación
    }
  }

  // ===========================================================================
  // NOTIFICACIONES DE LOGROS
  // ===========================================================================

  /// Mostrar notificación de logro desbloqueado
  Future<void> showAchievementUnlocked({
    required String achievementName,
    required String description,
    String? achievementId,
  }) async {
    if (!_isInitialized) return;

    try {
      const androidDetails = AndroidNotificationDetails(
        _channelIdAchievements,
        'Logros',
        channelDescription: 'Notificaciones de logros desbloqueados',
        importance: Importance.high,
        priority: Priority.high,
        icon: '@mipmap/ic_launcher',
        channelShowBadge: true,
        category: AndroidNotificationCategory.social,
      );

      const darwinDetails = DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      );

      const details = NotificationDetails(
        android: androidDetails,
        iOS: darwinDetails,
        macOS: darwinDetails,
      );

      await _plugin.show(
        _nextNotificationId(),
        '🏆 ¡Logro desbloqueado!',
        '$achievementName - $description',
        details,
        payload: achievementId != null ? 'achievement:$achievementId' : null,
      );
    } catch (e) {
      // Error al mostrar notificación de logro
    }
  }

  // ===========================================================================
  // NOTIFICACIONES DE SUBIDA DE NIVEL
  // ===========================================================================

  /// Mostrar notificación de subida de nivel
  Future<void> showLevelUp({
    required int newLevel,
    int? totalXP,
  }) async {
    if (!_isInitialized) return;

    try {
      const androidDetails = AndroidNotificationDetails(
        _channelIdLevelUp,
        'Subida de nivel',
        channelDescription: 'Notificaciones cuando subes de nivel',
        importance: Importance.high,
        priority: Priority.high,
        icon: '@mipmap/ic_launcher',
        channelShowBadge: true,
      );

      const darwinDetails = DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      );

      const details = NotificationDetails(
        android: androidDetails,
        iOS: darwinDetails,
        macOS: darwinDetails,
      );

      final body = totalXP != null
          ? '¡Has alcanzado el nivel $newLevel! XP total: $totalXP'
          : '¡Has alcanzado el nivel $newLevel!';

      await _plugin.show(
        _nextNotificationId(),
        '⬆️ ¡Subida de nivel!',
        body,
        details,
        payload: 'level_up:$newLevel',
      );
    } catch (e) {
      // Error al mostrar notificación de nivel
    }
  }

  // ===========================================================================
  // NOTIFICACIONES DE PEZ AVISTADO POR OTRO USUARIO
  // ===========================================================================

  /// Mostrar notificación cuando otro usuario avista un pez que el usuario identificó
  Future<void> showFishSpottedByOther({
    required String fishSpecies,
    required String spottedByUserName,
    String? fishId,
    String? locationName,
  }) async {
    if (!_isInitialized) return;

    try {
      const androidDetails = AndroidNotificationDetails(
        _channelIdFishSpotted,
        'Pez avistado',
        channelDescription:
            'Notificaciones cuando otro usuario ve tu pez',
        importance: Importance.defaultImportance,
        priority: Priority.defaultPriority,
        icon: '@mipmap/ic_launcher',
      );

      const darwinDetails = DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      );

      const details = NotificationDetails(
        android: androidDetails,
        iOS: darwinDetails,
        macOS: darwinDetails,
      );

      final location =
          locationName != null ? ' en $locationName' : '';
      final body =
          '$spottedByUserName ha avistado tu $fishSpecies$location';

      await _plugin.show(
        _nextNotificationId(),
        '🐟 ¡Tu pez fue avistado!',
        body,
        details,
        payload: fishId != null ? 'fish:$fishId' : null,
      );
    } catch (e) {
      // Error al mostrar notificación de pez avistado
    }
  }

  // ===========================================================================
  // NOTIFICACIONES DE PEZ RARO CERCANO
  // ===========================================================================

  /// Mostrar notificación cuando hay un pez raro cerca de la ubicación del usuario
  Future<void> showRareFishNearby({
    required String spotName,
    required List<String> rareSpecies,
    double? distanceMeters,
    String? spotId,
  }) async {
    if (!_isInitialized) return;

    try {
      const androidDetails = AndroidNotificationDetails(
        _channelIdRareFish,
        'Pez raro cercano',
        channelDescription:
            'Notificaciones cuando hay un pez raro cerca',
        importance: Importance.high,
        priority: Priority.high,
        icon: '@mipmap/ic_launcher',
        channelShowBadge: true,
        category: AndroidNotificationCategory.locationSharing,
      );

      const darwinDetails = DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
      );

      const details = NotificationDetails(
        android: androidDetails,
        iOS: darwinDetails,
        macOS: darwinDetails,
      );

      final speciesText = rareSpecies.isNotEmpty
          ? rareSpecies.join(', ')
          : 'especies raras';
      final distanceText = distanceMeters != null
          ? ' (${distanceMeters.toInt()}m)'
          : '';
      final body =
          'Cerca de $spotName$distanceText se han visto: $speciesText';

      await _plugin.show(
        _nextNotificationId(),
        '✨ ¡Pez raro cercano!',
        body,
        details,
        payload: spotId != null ? 'spot:$spotId' : null,
      );
    } catch (e) {
      // Error al mostrar notificación de pez raro
    }
  }

  // ===========================================================================
  // UTILIDADES
  // ===========================================================================

  /// Cancelar todas las notificaciones pendientes
  Future<void> cancelAll() async {
    try {
      await _plugin.cancelAll();
    } catch (e) {
      // Error al cancelar notificaciones
    }
  }

  /// Cancelar una notificación específica por ID
  Future<void> cancel(int id) async {
    try {
      await _plugin.cancel(id);
    } catch (e) {
      // Error al cancelar notificación
    }
  }

  /// Generar un ID único para cada notificación
  int _nextNotificationId() {
    _notificationIdCounter++;
    return _notificationIdCounter;
  }
}
