import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/enums/user_role.dart';
import '../../../data/services/role_guard_service.dart';
import '../providers/map_providers.dart';
import '../widgets/anonymous_marker.dart';
import '../widgets/capture_detail_sheet.dart';
import '../widgets/spot_bottom_sheet.dart';
import '../widgets/spot_marker.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

/// Pantalla principal del Mapa Interactivo
/// Muestra la ubicación del usuario y los fishing spots cercanos
class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final MapController _mapController = MapController();
  bool _hasCenteredOnUser = false;

  @override
  Widget build(BuildContext context) {
    // Auto-centrar en la ubicación del usuario la primera vez que llega GPS
    ref.listen<AsyncValue<LatLng?>>(userLocationProvider, (previous, next) {
      final location = next.valueOrNull;
      if (location != null && !_hasCenteredOnUser) {
        _hasCenteredOnUser = true;
        // Mover el mapa a la ubicación real del usuario
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _mapController.move(location, AppConstants.mapDefaultZoom);
          }
        });
      }
    });
    final userLocation = ref.watch(userLocationProvider);
    final fishingSpots = ref.watch(fishingSpotsProvider);
    final mapCaptures = ref.watch(mapCapturesProvider);
    final currentRole = ref.watch(currentUserRoleProvider);

    return Scaffold(
      body: Stack(
        children: [
          // Mapa
          _buildMap(userLocation, fishingSpots, mapCaptures),

          // Header overlay con gradiente
          _buildHeaderOverlay(context, currentRole),

          // Info de ubicación
          Positioned(
            top: MediaQuery.of(context).padding.top + 60,
            left: 16,
            right: 16,
            child: _buildLocationInfo(userLocation),
          ),

          if (mapCaptures.hasError)
            Positioned(
              left: 16,
              right: 88,
              bottom: MediaQuery.of(context).padding.bottom + 112,
              child: _buildCaptureLoadError(),
            ),
        ],
      ),

      // FAB para centrar en ubicación
      floatingActionButton: Padding(
        padding: const EdgeInsets.only(bottom: 80),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Botón de centrar ubicación
            FloatingActionButton(
              heroTag: 'center_location',
              onPressed: () => _centerOnUser(userLocation),
              backgroundColor: AppTheme.darkSurface,
              child: const Icon(Icons.my_location, color: AppTheme.accentBlue),
            ),
            const SizedBox(height: 12),
            // Botón de zoom in
            FloatingActionButton.small(
              heroTag: 'zoom_in',
              onPressed: () {
                final zoom = _mapController.camera.zoom + 1;
                _mapController.move(
                  _mapController.camera.center,
                  zoom.clamp(AppConstants.mapMinZoom, AppConstants.mapMaxZoom),
                );
              },
              backgroundColor: AppTheme.darkSurface,
              child: const Icon(Icons.add, color: Colors.white70),
            ),
            const SizedBox(height: 8),
            // Botón de zoom out
            FloatingActionButton.small(
              heroTag: 'zoom_out',
              onPressed: () {
                final zoom = _mapController.camera.zoom - 1;
                _mapController.move(
                  _mapController.camera.center,
                  zoom.clamp(AppConstants.mapMinZoom, AppConstants.mapMaxZoom),
                );
              },
              backgroundColor: AppTheme.darkSurface,
              child: const Icon(Icons.remove, color: Colors.white70),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMap(
    AsyncValue<LatLng?> userLocation,
    AsyncValue<List<FishingSpotData>> fishingSpots,
    AsyncValue<List<MapCaptureData>> mapCaptures,
  ) {
    // Centro temporal mientras se obtiene GPS (se re-centra automáticamente)
    final center = userLocation.valueOrNull ?? const LatLng(0, 0);
    final initialZoom = userLocation.valueOrNull != null
        ? AppConstants.mapDefaultZoom
        : 2.0; // Zoom global mientras no hay GPS

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: center,
        initialZoom: initialZoom,
        minZoom: AppConstants.mapMinZoom,
        maxZoom: AppConstants.mapMaxZoom,
        // Estilo oscuro del mapa
        backgroundColor: AppTheme.darkBackground,
      ),
      children: [
        // Tile layer (OpenStreetMap con estilo oscuro)
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.fishdex.app',
          // Filtro oscuro para que combine con el tema gaming
          tileBuilder: (context, tileWidget, tile) {
            return ColorFiltered(
              colorFilter: const ColorFilter.matrix(<double>[
                0.3, 0, 0, 0, 0, // Red
                0, 0.3, 0, 0, 0, // Green
                0, 0, 0.4, 0, 20, // Blue (más azulado)
                0, 0, 0, 1, 0, // Alpha
              ]),
              child: tileWidget,
            );
          },
        ),

        // Marcadores de fishing spots
        fishingSpots.when(
          data: (spots) => MarkerLayer(
            markers: spots.map((spot) => _buildSpotMarker(spot)).toList(),
          ),
          loading: () => const MarkerLayer(markers: []),
          error: (_, __) => const MarkerLayer(markers: []),
        ),

        // Marcadores de capturas (filtrados por rol)
        mapCaptures.when(
          data: (captures) => MarkerLayer(
            markers: captures.map((c) => _buildCaptureMarker(c)).toList(),
          ),
          loading: () => const MarkerLayer(markers: []),
          error: (_, __) => const MarkerLayer(markers: []),
        ),

        // Marcador del usuario
        if (userLocation.valueOrNull != null)
          MarkerLayer(
            markers: [
              Marker(
                point: userLocation.value!,
                width: 40,
                height: 40,
                child: const UserLocationMarker(),
              ),
            ],
          ),
      ],
    );
  }

  /// Construye un marker de captura según su tipo (propio, anónimo, o completo)
  Marker _buildCaptureMarker(MapCaptureData capture) {
    return Marker(
      point: LatLng(capture.latitude, capture.longitude),
      width: 40,
      height: 40,
      child: capture.isAnonymous
          ? AnonymousMarker(
              onTap: () => _showAnonymousBottomSheet(capture),
            )
          : GestureDetector(
              onTap: () => _showCaptureInfo(capture),
              child: _buildCaptureMarkerWidget(capture),
            ),
    );
  }

  /// Widget del marker de captura propia
  Widget _buildCaptureMarkerWidget(MapCaptureData capture) {
    Color markerColor;
    switch (capture.rarity) {
      case 'legendary':
        markerColor = Colors.amber;
        break;
      case 'rare':
        markerColor = Colors.purple;
        break;
      case 'uncommon':
        markerColor = AppTheme.teal;
        break;
      default:
        markerColor = Colors.green;
    }

    return Container(
      width: 32,
      height: 32,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: markerColor.withOpacity(0.8),
        border: Border.all(
          color: capture.isOwn ? Colors.white : markerColor,
          width: capture.isOwn ? 2.5 : 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: markerColor.withOpacity(0.4),
            blurRadius: 6,
          ),
        ],
      ),
      child: Icon(
        Icons.phishing,
        color: Colors.white,
        size: capture.isOwn ? 16 : 14,
      ),
    );
  }

  void _showAnonymousBottomSheet(MapCaptureData capture) {
    _showFloatingMapSheet(
      isScrollControlled: false,
      builder: (context) =>
          AnonymousMarkerBottomSheet(species: capture.species),
    );
  }

  void _showCaptureInfo(MapCaptureData capture) {
    final role = ref.read(currentUserRoleProvider).valueOrNull?.role;

    if (role == UserRole.researcher || role == UserRole.admin) {
      // Researcher/Admin: popup detallado con historial ramificado
      _showFloatingMapSheet(
        isScrollControlled: true,
        builder: (context) => CaptureDetailSheet(capture: capture),
      );
    } else {
      // Fisherman: popup básico
      _showFloatingMapSheet(
        isScrollControlled: false,
        builder: (context) => _CaptureInfoSheet(capture: capture),
      );
    }
  }

  Marker _buildSpotMarker(FishingSpotData spot) {
    return Marker(
      point: LatLng(spot.latitude, spot.longitude),
      width: 50,
      height: 50,
      child: GestureDetector(
        onTap: () => _showSpotBottomSheet(spot),
        child: SpotMarkerWidget(
          hasRareFish: spot.hasRareFish,
          totalCatches: spot.totalCatches,
        ),
      ),
    );
  }

  Widget _buildHeaderOverlay(BuildContext context, AsyncValue currentRole) {
    final roleName = currentRole.valueOrNull?.role.displayName ?? '';

    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        height: MediaQuery.of(context).padding.top + 56,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              AppTheme.darkBackground,
              AppTheme.darkBackground.withOpacity(0.8),
              Colors.transparent,
            ],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                Text(
                  context.l10n.mapTitle,
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        letterSpacing: 2,
                      ),
                ),
                const Spacer(),
                // Badge de rol
                if (roleName.isNotEmpty)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: AppTheme.darkSurface.withOpacity(0.8),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      roleName,
                      style: const TextStyle(
                        color: Colors.white54,
                        fontSize: 11,
                      ),
                    ),
                  ),
                const SizedBox(width: 8),
                // Indicador de spots cercanos
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: AppTheme.darkSurface.withOpacity(0.8),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.place, color: AppTheme.teal, size: 16),
                      const SizedBox(width: 4),
                      Text(
                        context.l10n.mapSpots,
                        style: const TextStyle(
                            color: Colors.white70, fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCaptureLoadError() {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface.withOpacity(0.95),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.red.withOpacity(0.35)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, color: Colors.redAccent, size: 18),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'No se pudieron cargar las capturas del mapa.',
              style: TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ),
          IconButton(
            tooltip: 'Reintentar',
            visualDensity: VisualDensity.compact,
            onPressed: () => ref.invalidate(mapCapturesProvider),
            icon: const Icon(Icons.refresh, color: AppTheme.accentBlue),
          ),
        ],
      ),
    );
  }

  Widget _buildLocationInfo(AsyncValue<LatLng?> userLocation) {
    return userLocation.when(
      data: (location) {
        if (location == null) {
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: AppTheme.darkSurface.withOpacity(0.9),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                const Icon(Icons.location_off, color: Colors.orange, size: 18),
                const SizedBox(width: 8),
                Text(
                  context.l10n.mapActivateLocation,
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          );
        }
        return const SizedBox.shrink();
      },
      loading: () => Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: AppTheme.darkSurface.withOpacity(0.9),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 8),
            Text(
              context.l10n.mapGettingLocation,
              style: const TextStyle(color: Colors.white70, fontSize: 13),
            ),
          ],
        ),
      ),
      error: (e, _) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.red.withOpacity(0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.red.withOpacity(0.3)),
        ),
        child: Row(
          children: [
            const Icon(Icons.error_outline, color: Colors.red, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                context.l10n.mapGpsError(e.toString()),
                style: const TextStyle(color: Colors.red, fontSize: 12),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _centerOnUser(AsyncValue<LatLng?> userLocation) {
    final location = userLocation.valueOrNull;
    if (location != null) {
      _mapController.move(location, AppConstants.mapDefaultZoom);
    }
  }

  Future<T?> _showFloatingMapSheet<T>({
    required WidgetBuilder builder,
    bool isScrollControlled = true,
  }) {
    return showModalBottomSheet<T>(
      context: context,
      useRootNavigator: true,
      useSafeArea: true,
      isScrollControlled: isScrollControlled,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withOpacity(0.55),
      builder: (sheetContext) {
        final bottomSafe = MediaQuery.of(sheetContext).padding.bottom;

        return Padding(
          padding: EdgeInsets.fromLTRB(
            12,
            0,
            12,
            bottomSafe + 92,
          ),
          child: builder(sheetContext),
        );
      },
    );
  }

  void _showSpotBottomSheet(FishingSpotData spot) {
    _showFloatingMapSheet(
      isScrollControlled: false,
      builder: (context) => SpotBottomSheet(spot: spot),
    );
  }
}

/// Marcador de ubicación del usuario (punto azul pulsante)
class UserLocationMarker extends StatefulWidget {
  const UserLocationMarker({super.key});

  @override
  State<UserLocationMarker> createState() => _UserLocationMarkerState();
}

class _UserLocationMarkerState extends State<UserLocationMarker>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _pulseController,
      builder: (context, child) {
        final scale = 1.0 + (_pulseController.value * 0.3);
        return Stack(
          alignment: Alignment.center,
          children: [
            // Halo pulsante
            Transform.scale(
              scale: scale,
              child: Container(
                width: 30,
                height: 30,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppTheme.accentBlue.withOpacity(0.2),
                ),
              ),
            ),
            // Punto central
            Container(
              width: 16,
              height: 16,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppTheme.accentBlue,
                border: Border.all(color: Colors.white, width: 3),
                boxShadow: [
                  BoxShadow(
                    color: AppTheme.accentBlue.withOpacity(0.5),
                    blurRadius: 8,
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

// =============================================================================
// BOTTOM SHEET DE INFO DE CAPTURA
// =============================================================================

/// Bottom sheet con información de una captura en el mapa
class _CaptureInfoSheet extends StatelessWidget {
  final MapCaptureData capture;

  const _CaptureInfoSheet({required this.capture});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppTheme.darkBackground,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withOpacity(0.1)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Handle
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Especie y rareza
          Row(
            children: [
              Icon(
                Icons.phishing,
                color: _rarityColor(capture.rarity),
                size: 24,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  capture.species,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: _rarityColor(capture.rarity).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  capture.rarity.toUpperCase(),
                  style: TextStyle(
                    color: _rarityColor(capture.rarity),
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Info
          _infoRow(Icons.calendar_today, context.l10n.mapFishDate,
              '${capture.capturedAt.day}/${capture.capturedAt.month}/${capture.capturedAt.year}'),
          const SizedBox(height: 8),
          _infoRow(
            Icons.fingerprint,
            context.l10n.mapFishId,
            capture.fishId.length > 8
                ? capture.fishId.substring(0, 8)
                : capture.fishId,
          ),
          const SizedBox(height: 8),
          _infoRow(
            Icons.location_on,
            context.l10n.mapCoordinates,
            '${capture.latitude.toStringAsFixed(6)}, ${capture.longitude.toStringAsFixed(6)}',
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  Widget _infoRow(IconData icon, String label, String value) {
    return Row(
      children: [
        Icon(icon, color: Colors.white38, size: 16),
        const SizedBox(width: 8),
        Text(
          '$label: ',
          style: const TextStyle(color: Colors.white54, fontSize: 13),
        ),
        Text(
          value,
          style: const TextStyle(color: Colors.white, fontSize: 13),
        ),
      ],
    );
  }

  Color _rarityColor(String rarity) {
    switch (rarity) {
      case 'legendary':
        return Colors.amber;
      case 'rare':
        return Colors.purple;
      case 'uncommon':
        return AppTheme.teal;
      default:
        return Colors.green;
    }
  }
}
