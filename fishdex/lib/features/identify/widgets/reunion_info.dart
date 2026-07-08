import 'package:flutter/material.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/identify_result.dart';

/// Widget que muestra la información de un reencuentro con un pez conocido
/// Incluye historial, crecimiento y avistamientos previos
class ReunionInfo extends StatelessWidget {
  final FishPreviousData previousData;

  const ReunionInfo({super.key, required this.previousData});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.energyOrange.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Título
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.energyOrange.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.history,
                  color: AppTheme.energyOrange,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  context.l10n.reunionHistory,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: AppTheme.energyOrange.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  context.l10n.reunionTimesSeen(previousData.totalSightings),
                  style: const TextStyle(
                    color: AppTheme.energyOrange,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          
          // Datos del historial
          _buildHistoryRow(
            icon: Icons.calendar_today,
            label: context.l10n.reunionFirstSighting,
            value: _formatDate(previousData.firstSeenDate),
          ),
          const SizedBox(height: 10),
          _buildHistoryRow(
            icon: Icons.location_on,
            label: context.l10n.reunionFirstLocation,
            value: previousData.firstSeenLocation ?? context.l10n.reunionUnknown,
          ),
          const SizedBox(height: 10),
          _buildHistoryRow(
            icon: Icons.access_time,
            label: context.l10n.reunionLastSighting,
            value: _formatDate(previousData.lastSeenDate),
          ),
          
          // Indicador de crecimiento
          if (previousData.growthCm > 0) ...[
            const SizedBox(height: 16),
            const Divider(color: Colors.white12),
            const SizedBox(height: 12),
            _buildGrowthIndicator(context),
          ],
        ],
      ),
    );
  }

  Widget _buildHistoryRow({
    required IconData icon,
    required String label,
    required String value,
  }) {
    return Row(
      children: [
        Icon(icon, color: Colors.white38, size: 16),
        const SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 13,
          ),
        ),
        const Spacer(),
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildGrowthIndicator(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.successGreen.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppTheme.successGreen.withOpacity(0.3),
        ),
      ),
      child: Row(
        children: [
          const Icon(
            Icons.trending_up,
            color: AppTheme.successGreen,
            size: 24,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.reunionGrown,
                  style: const TextStyle(
                    color: AppTheme.successGreen,
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  'Antes: ${previousData.lastEstimatedSizeCm} cm → Ahora: ${(previousData.lastEstimatedSizeCm + previousData.growthCm).toStringAsFixed(1)} cm',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Text(
            '+${previousData.growthCm.toStringAsFixed(1)} ${context.l10n.reunionGrowthLabel}',
            style: const TextStyle(
              color: AppTheme.successGreen,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  String _formatDate(String isoDate) {
    try {
      final date = DateTime.parse(isoDate);
      return '${date.day}/${date.month}/${date.year}';
    } catch (_) {
      return isoDate;
    }
  }
}
