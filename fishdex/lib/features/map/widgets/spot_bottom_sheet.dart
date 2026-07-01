import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../providers/map_providers.dart';

/// Bottom sheet que muestra la información de un spot de pesca
/// Se abre al tocar un marcador en el mapa
class SpotBottomSheet extends StatelessWidget {
  final FishingSpotData spot;

  const SpotBottomSheet({super.key, required this.spot});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle
          Container(
            margin: const EdgeInsets.only(top: 12),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.white24,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          
          Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Nombre del spot y tipo de agua
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            spot.name,
                            style: Theme.of(context)
                                .textTheme
                                .headlineMedium
                                ?.copyWith(fontSize: 20),
                          ),
                          const SizedBox(height: 4),
                          Row(
                            children: [
                              _buildWaterTypeBadge(),
                              const SizedBox(width: 8),
                              if (spot.hasRareFish) _buildRareBadge(),
                            ],
                          ),
                        ],
                      ),
                    ),
                    // Icono del tipo de agua
                    Container(
                      width: 50,
                      height: 50,
                      decoration: BoxDecoration(
                        color: AppTheme.teal.withOpacity(0.2),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        _getWaterTypeIcon(),
                        color: AppTheme.teal,
                        size: 28,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                
                // Descripción
                if (spot.description != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: Text(
                      spot.description!,
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.7),
                        fontSize: 14,
                      ),
                    ),
                  ),
                
                // Stats del spot
                Row(
                  children: [
                    _buildStatItem(
                      Icons.phishing,
                      '${spot.totalCatches}',
                      'Capturas',
                    ),
                    const SizedBox(width: 24),
                    _buildStatItem(
                      Icons.category,
                      '${spot.commonSpecies.length}',
                      'Especies',
                    ),
                    if (spot.lastCatchDate != null) ...[
                      const SizedBox(width: 24),
                      _buildStatItem(
                        Icons.access_time,
                        _formatDate(spot.lastCatchDate!),
                        'Última captura',
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 20),
                
                // Especies comunes
                Text(
                  'ESPECIES COMUNES',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: spot.commonSpecies
                      .map((species) => _buildSpeciesChip(species))
                      .toList(),
                ),
                const SizedBox(height: 24),
                
                // Botón de "Ir a pescar aquí"
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton.icon(
                    onPressed: () {
                      Navigator.pop(context);
                      // TODO: Navegar a la cámara con este spot seleccionado
                    },
                    icon: const Icon(Icons.camera_alt),
                    label: const Text('PESCAR AQUÍ'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.accentBlue,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildWaterTypeBadge() {
    final label = switch (spot.waterType) {
      'rio' => 'Río',
      'lago' => 'Lago',
      'mar' => 'Mar',
      'embalse' => 'Embalse',
      _ => spot.waterType,
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.teal.withOpacity(0.2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.teal.withOpacity(0.3)),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: AppTheme.teal,
          fontSize: 12,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  Widget _buildRareBadge() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.legendaryPurple.withOpacity(0.2),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.legendaryPurple.withOpacity(0.3)),
      ),
      child: const Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.star, color: AppTheme.legendaryPurple, size: 12),
          SizedBox(width: 4),
          Text(
            'Peces raros',
            style: TextStyle(
              color: AppTheme.legendaryPurple,
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatItem(IconData icon, String value, String label) {
    return Column(
      children: [
        Row(
          children: [
            Icon(icon, color: AppTheme.gold, size: 16),
            const SizedBox(width: 4),
            Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 11,
          ),
        ),
      ],
    );
  }

  Widget _buildSpeciesChip(String species) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: AppTheme.darkSurfaceElevated,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Text(
        species,
        style: const TextStyle(
          color: Colors.white70,
          fontSize: 13,
        ),
      ),
    );
  }

  IconData _getWaterTypeIcon() {
    return switch (spot.waterType) {
      'rio' => Icons.water,
      'lago' => Icons.pool,
      'mar' => Icons.sailing,
      'embalse' => Icons.landscape,
      _ => Icons.water_drop,
    };
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final diff = now.difference(date);
    if (diff.inDays == 0) return 'Hoy';
    if (diff.inDays == 1) return 'Ayer';
    if (diff.inDays < 7) return 'Hace ${diff.inDays}d';
    return '${date.day}/${date.month}';
  }
}
