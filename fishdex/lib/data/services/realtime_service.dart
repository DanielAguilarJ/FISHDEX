import 'dart:async';
import 'package:appwrite/appwrite.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/constants/app_constants.dart';

// =============================================================================
// MODELOS DE EVENTOS REALTIME
// =============================================================================

/// Evento de actualización del ranking
class RankingUpdateEvent {
  final String userId;
  final String userName;
  final int newPosition;
  final int xpTotal;
  final String? fishSpecies;

  const RankingUpdateEvent({
    required this.userId,
    required this.userName,
    required this.newPosition,
    required this.xpTotal,
    this.fishSpecies,
  });
}

/// Evento cuando alguien más avista un pez del usuario
class FishSpottedEvent {
  final String fishId;
  final String species;
  final String spottedByUserId;
  final String spottedByUserName;
  final double? latitude;
  final double? longitude;
  final DateTime timestamp;

  const FishSpottedEvent({
    required this.fishId,
    required this.species,
    required this.spottedByUserId,
    required this.spottedByUserName,
    this.latitude,
    this.longitude,
    required this.timestamp,
  });
}

/// Evento de nuevo spot de pesca
class NewFishingSpotEvent {
  final String spotId;
  final String name;
  final double latitude;
  final double longitude;
  final String waterType;
  final String createdByUserId;

  const NewFishingSpotEvent({
    required this.spotId,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.waterType,
    required this.createdByUserId,
  });
}

// =============================================================================
// SERVICIO REALTIME
// =============================================================================

/// Servicio que gestiona las suscripciones en tiempo real con Appwrite.
/// Proporciona streams de eventos para rankings, avistamientos y spots nuevos.
class RealtimeService {
  final Realtime _realtime;
  final String _currentUserId;

  // Controladores de streams internos
  final _rankingController = StreamController<RankingUpdateEvent>.broadcast();
  final _fishSpottedController = StreamController<FishSpottedEvent>.broadcast();
  final _newSpotController = StreamController<NewFishingSpotEvent>.broadcast();

  // Suscripciones activas de Appwrite
  RealtimeSubscription? _rankingSub;
  RealtimeSubscription? _sightingsSub;
  RealtimeSubscription? _spotsSub;

  // Estado de conexión
  bool _isConnected = false;
  bool get isConnected => _isConnected;

  RealtimeService({
    required Realtime realtime,
    required String currentUserId,
  })  : _realtime = realtime,
        _currentUserId = currentUserId;

  // ===========================================================================
  // STREAMS PÚBLICOS
  // ===========================================================================

  /// Stream de actualizaciones del ranking
  Stream<RankingUpdateEvent> get rankingUpdates => _rankingController.stream;

  /// Stream de cuando alguien avista un pez que el usuario identificó primero
  Stream<FishSpottedEvent> get fishSpottedByOthers =>
      _fishSpottedController.stream;

  /// Stream de nuevos spots de pesca
  Stream<NewFishingSpotEvent> get newFishingSpots => _newSpotController.stream;

  // ===========================================================================
  // SUSCRIPCIONES
  // ===========================================================================

  /// Iniciar todas las suscripciones en tiempo real.
  /// Envuelto en try/catch para no fallar si Appwrite no está disponible.
  void subscribeAll() {
    _subscribeToRankingUpdates();
    _subscribeToFishSightings();
    _subscribeToNewSpots();
  }

  /// Suscribirse a cambios en la colección de leaderboards
  void _subscribeToRankingUpdates() {
    try {
      final channel =
          'databases.${AppConstants.databaseId}.collections.${AppConstants.leaderboardsCollection}.documents';

      _rankingSub = _realtime.subscribe([channel]);
      _isConnected = true;

      _rankingSub!.stream.listen(
        (event) {
          try {
            final data = event.payload;
            final rankingEvent = RankingUpdateEvent(
              userId: data['user_id'] ?? '',
              userName: data['user_name'] ?? 'Usuario',
              newPosition: data['position'] ?? 0,
              xpTotal: data['xp_total'] ?? 0,
              fishSpecies: data['last_fish_species'],
            );
            _rankingController.add(rankingEvent);
          } catch (e) {
            // Error al parsear evento de ranking, ignorar silenciosamente
          }
        },
        onError: (error) {
          // Error en la suscripción de ranking
          _isConnected = false;
        },
      );
    } catch (e) {
      // No se pudo suscribir a rankings (Appwrite no disponible)
      _isConnected = false;
    }
  }

  /// Suscribirse a nuevos avistamientos para detectar si alguien ve un pez del usuario
  void _subscribeToFishSightings() {
    try {
      final channel =
          'databases.${AppConstants.databaseId}.collections.${AppConstants.fishSightingsCollection}.documents';

      _sightingsSub = _realtime.subscribe([channel]);

      _sightingsSub!.stream.listen(
        (event) {
          try {
            final data = event.payload;

            // Solo notificar si el avistamiento es de un pez del usuario actual
            // y fue avistado por otra persona
            final originalDiscoverer = data['original_discoverer_id'] ?? '';
            final spottedBy = data['user_id'] ?? '';

            if (originalDiscoverer == _currentUserId &&
                spottedBy != _currentUserId) {
              final fishEvent = FishSpottedEvent(
                fishId: data['fish_id'] ?? '',
                species: data['species'] ?? 'Pez desconocido',
                spottedByUserId: spottedBy,
                spottedByUserName: data['user_name'] ?? 'Otro usuario',
                latitude: data['latitude'] != null
                    ? (data['latitude'] as num).toDouble()
                    : null,
                longitude: data['longitude'] != null
                    ? (data['longitude'] as num).toDouble()
                    : null,
                timestamp: data['created_at'] != null
                    ? DateTime.tryParse(data['created_at']) ?? DateTime.now()
                    : DateTime.now(),
              );
              _fishSpottedController.add(fishEvent);
            }
          } catch (e) {
            // Error al parsear evento de avistamiento, ignorar
          }
        },
        onError: (error) {
          // Error en la suscripción de avistamientos
        },
      );
    } catch (e) {
      // No se pudo suscribir a avistamientos
    }
  }

  /// Suscribirse a nuevos spots de pesca creados
  void _subscribeToNewSpots() {
    try {
      final channel =
          'databases.${AppConstants.databaseId}.collections.${AppConstants.fishingSpotsCollection}.documents';

      _spotsSub = _realtime.subscribe([channel]);

      _spotsSub!.stream.listen(
        (event) {
          try {
            // Solo notificar sobre creaciones (no actualizaciones)
            final events = event.events;
            final isCreate =
                events.any((e) => e.contains('.create'));

            if (!isCreate) return;

            final data = event.payload;
            final spotEvent = NewFishingSpotEvent(
              spotId: data['\$id'] ?? '',
              name: data['name'] ?? 'Spot sin nombre',
              latitude: (data['latitude'] as num?)?.toDouble() ?? 0.0,
              longitude: (data['longitude'] as num?)?.toDouble() ?? 0.0,
              waterType: data['water_type'] ?? 'desconocido',
              createdByUserId: data['created_by'] ?? '',
            );
            _newSpotController.add(spotEvent);
          } catch (e) {
            // Error al parsear evento de spot nuevo
          }
        },
        onError: (error) {
          // Error en la suscripción de spots
        },
      );
    } catch (e) {
      // No se pudo suscribir a spots nuevos
    }
  }

  // ===========================================================================
  // LIMPIEZA
  // ===========================================================================

  /// Cancelar todas las suscripciones y cerrar streams
  void dispose() {
    _rankingSub?.close();
    _sightingsSub?.close();
    _spotsSub?.close();
    _rankingController.close();
    _fishSpottedController.close();
    _newSpotController.close();
    _isConnected = false;
  }
}

// =============================================================================
// PROVIDERS DE RIVERPOD
// =============================================================================

/// Provider del cliente Appwrite (debe ser inicializado en la app)
final appwriteClientProvider = Provider<Client>((ref) {
  final client = Client()
      .setEndpoint(AppConstants.appwriteEndpoint)
      .setProject(AppConstants.appwriteProjectId);
  return client;
});

/// Provider de Realtime de Appwrite
final appwriteRealtimeProvider = Provider<Realtime>((ref) {
  final client = ref.watch(appwriteClientProvider);
  return Realtime(client);
});

/// Provider del ID del usuario actual (se actualiza al hacer login)
final currentUserIdProvider = StateProvider<String>((ref) => '');

/// Provider del servicio Realtime
final realtimeServiceProvider = Provider<RealtimeService>((ref) {
  final realtime = ref.watch(appwriteRealtimeProvider);
  final userId = ref.watch(currentUserIdProvider);

  final service = RealtimeService(
    realtime: realtime,
    currentUserId: userId,
  );

  // Iniciar suscripciones automáticamente si hay usuario
  if (userId.isNotEmpty) {
    service.subscribeAll();
  }

  // Limpiar al disponer
  ref.onDispose(() => service.dispose());

  return service;
});

/// Provider del stream de actualizaciones de ranking
final rankingUpdatesProvider = StreamProvider<RankingUpdateEvent>((ref) {
  final service = ref.watch(realtimeServiceProvider);
  return service.rankingUpdates;
});

/// Provider del stream de peces avistados por otros
final fishSpottedByOthersProvider = StreamProvider<FishSpottedEvent>((ref) {
  final service = ref.watch(realtimeServiceProvider);
  return service.fishSpottedByOthers;
});

/// Provider del stream de nuevos spots de pesca
final newFishingSpotsProvider = StreamProvider<NewFishingSpotEvent>((ref) {
  final service = ref.watch(realtimeServiceProvider);
  return service.newFishingSpots;
});
