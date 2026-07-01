import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/constants/app_constants.dart';
import '../providers/map_providers.dart';
import '../widgets/spot_bottom_sheet.dart';
import '../widgets/spot_marker.dart';

/// Pantalla principal del Mapa Interactivo
/// Muestra la ubicación del usuario y los fishing spots cercanos
class MapScreen extends ConsumerStatefulWidget {
  const MapScreen({super.key});

  @override
  ConsumerState<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends ConsumerState<MapScreen> {
  final MapController _mapController = MapController();

  @override
  Widget build(BuildContext context) {
    final userLocation = ref.watch(userLocationProvider);
    final fishingSpots = ref.watch(fishingSpotsProvider);

    return Scaffold(
      body: Stack(
        children: [
          // Mapa
          _buildMap(userLocation, fishingSpots),
          
          // Header overlay con gradiente
          _buildHeaderOverlay(context),
          
          // Info de ubicación
          Positioned(
            top: MediaQuery.of(context).padding.top + 60,
            left: 16,
            right: 16,
            child: _buildLocationInfo(userLocation),
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
  ) {
    // Ubicación por defecto (Madrid, España) si no hay GPS
    final center = userLocation.valueOrNull ?? const LatLng(40.4168, -3.7038);

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(
        initialCenter: center,
        initialZoom: AppConstants.mapDefaultZoom,
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
                0.3, 0, 0, 0, 0,    // Red
                0, 0.3, 0, 0, 0,    // Green
                0, 0, 0.4, 0, 20,   // Blue (más azulado)
                0, 0, 0, 1, 0,      // Alpha
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

  Widget _buildHeaderOverlay(BuildContext context) {
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
                  'MAPA DE PESCA',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        letterSpacing: 2,
                      ),
                ),
                const Spacer(),
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
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.place, color: AppTheme.teal, size: 16),
                      SizedBox(width: 4),
                      Text(
                        'Spots',
                        style: TextStyle(color: Colors.white70, fontSize: 12),
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
            child: const Row(
              children: [
                Icon(Icons.location_off, color: Colors.orange, size: 18),
                SizedBox(width: 8),
                Text(
                  'Activar ubicación para ver spots cercanos',
                  style: TextStyle(color: Colors.white70, fontSize: 13),
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
        child: const Row(
          children: [
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            SizedBox(width: 8),
            Text(
              'Obteniendo ubicación...',
              style: TextStyle(color: Colors.white70, fontSize: 13),
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
                'Error GPS: $e',
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

  void _showSpotBottomSheet(FishingSpotData spot) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
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
