import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/fish_capture.dart';
import '../providers/fish_history_provider.dart';

// =============================================================================
// TIMELINE RAMIFICADO DEL HISTORIAL DE UN PEZ
// =============================================================================

/// Widget que muestra el historial de capturas de un fish_id como
/// un timeline ramificado. Las capturas se agrupan por ubicación
/// (±500m) para visualizar el "movimiento" del pez.
class FishHistoryTimeline extends ConsumerWidget {
  final String fishId;
  final String species;

  const FishHistoryTimeline({
    super.key,
    required this.fishId,
    required this.species,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final groupedHistory = ref.watch(fishHistoryGroupedProvider(fishId));

    return groupedHistory.when(
      data: (groups) {
        if (groups.isEmpty) {
          return _buildEmptyState();
        }
        return _buildTimeline(context, groups);
      },
      loading: () => _buildLoading(),
      error: (e, _) => _buildError(e),
    );
  }

  Widget _buildTimeline(BuildContext context, List<LocationGroup> groups) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header del timeline
        Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppTheme.teal.withOpacity(0.2),
                border: Border.all(color: AppTheme.teal, width: 2),
              ),
              child: const Icon(Icons.phishing, color: AppTheme.teal, size: 16),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    species,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    '${_totalCaptures(groups)} capturas en ${groups.length} ubicación${groups.length > 1 ? "es" : ""}',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),

        // Ramas del timeline
        ...List.generate(groups.length, (index) {
          final group = groups[index];
          final isLast = index == groups.length - 1;
          return _buildLocationBranch(context, group, isLast, index);
        }),
      ],
    );
  }

  Widget _buildLocationBranch(
    BuildContext context,
    LocationGroup group,
    bool isLast,
    int branchIndex,
  ) {
    final branchColors = [
      AppTheme.teal,
      AppTheme.accentBlue,
      AppTheme.energyOrange,
      AppTheme.gold,
      Colors.purple,
    ];
    final branchColor = branchColors[branchIndex % branchColors.length];

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Línea vertical + nodo de la rama
          SizedBox(
            width: 32,
            child: Column(
              children: [
                Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: branchColor.withOpacity(0.2),
                    border: Border.all(color: branchColor, width: 2),
                  ),
                  child: Icon(Icons.place, color: branchColor, size: 12),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      color: Colors.white.withOpacity(0.15),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 12),

          // Contenido de la rama
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Zona ${group.locationLabel}',
                          style: TextStyle(
                            color: branchColor,
                            fontSize: 13,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: branchColor.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '${group.count}x',
                          style: TextStyle(
                            color: branchColor,
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ...group.captures.map(
                    (capture) => _buildCaptureEntry(capture, branchColor),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCaptureEntry(FishCapture capture, Color branchColor) {
    final date = capture.capturedAt;
    final dateStr = '${date.day}/${_monthName(date.month)}/${date.year}';

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: AppTheme.darkSurfaceElevated,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: Colors.white.withOpacity(0.06),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.calendar_today,
                    color: Colors.white.withOpacity(0.4), size: 12),
                const SizedBox(width: 6),
                Text(
                  dateStr,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 12,
                  ),
                ),
                const Spacer(),
                Icon(Icons.person_outline,
                    color: Colors.white.withOpacity(0.3), size: 12),
                const SizedBox(width: 4),
                Text(
                  capture.userId.length > 8
                      ? capture.userId.substring(0, 8)
                      : capture.userId,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.4),
                    fontSize: 11,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                if (capture.lengthCm != null) ...[
                  _dataChip(Icons.straighten, '${capture.lengthCm}cm'),
                  const SizedBox(width: 8),
                ],
                _dataChip(
                  Icons.psychology,
                  '${(capture.confidence * 100).toStringAsFixed(0)}%',
                ),
                const SizedBox(width: 8),
                _dataChip(
                  capture.isNewFish ? Icons.fiber_new : Icons.replay,
                  capture.isNewFish ? 'Nuevo' : 'Reencuentro',
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _dataChip(IconData icon, String text) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, color: Colors.white38, size: 12),
        const SizedBox(width: 3),
        Text(
          text,
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 11,
          ),
        ),
      ],
    );
  }

  Widget _buildEmptyState() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurfaceElevated,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(Icons.info_outline, color: Colors.white.withOpacity(0.3), size: 18),
          const SizedBox(width: 12),
          Text(
            'No hay historial disponible para este pez',
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoading() {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 16),
      child: Center(
        child: SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: AppTheme.teal,
          ),
        ),
      ),
    );
  }

  Widget _buildError(Object error) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: Colors.red, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Error al cargar historial: $error',
              style: const TextStyle(color: Colors.red, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  int _totalCaptures(List<LocationGroup> groups) {
    return groups.fold(0, (sum, group) => sum + group.count);
  }

  String _monthName(int month) {
    const months = [
      'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
      'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
    ];
    return months[month - 1];
  }
}
