import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../providers/map_providers.dart';
import 'fish_history_timeline.dart';

// =============================================================================
// BOTTOM SHEET DETALLADO DE CAPTURA (RESEARCHER/ADMIN)
// =============================================================================

/// Bottom sheet rico que muestra información detallada de una captura
/// y el historial ramificado del pez. Solo visible para Researchers y Admins.
class CaptureDetailSheet extends ConsumerStatefulWidget {
  final MapCaptureData capture;

  const CaptureDetailSheet({super.key, required this.capture});

  @override
  ConsumerState<CaptureDetailSheet> createState() => _CaptureDetailSheetState();
}

class _CaptureDetailSheetState extends ConsumerState<CaptureDetailSheet> {
  bool _showHistory = false;

  @override
  Widget build(BuildContext context) {
    final capture = widget.capture;
    final rarityColor = AppTheme.getRarityColor(capture.rarity);

    return DraggableScrollableSheet(
      initialChildSize: 0.55,
      minChildSize: 0.3,
      maxChildSize: 0.9,
      builder: (context, scrollController) {
        return Container(
          decoration: BoxDecoration(
            color: AppTheme.darkBackground,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
            border: Border.all(color: Colors.white.withOpacity(0.08)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.5),
                blurRadius: 20,
                offset: const Offset(0, -4),
              ),
            ],
          ),
          child: ListView(
            controller: scrollController,
            padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
            children: [
              // Handle
              Center(
                child: Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 20),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.3),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),

              _buildHeader(capture, rarityColor),
              const SizedBox(height: 20),

              _buildDataSection(capture),
              const SizedBox(height: 20),

              _buildCoordinatesSection(capture),
              const SizedBox(height: 20),

              _buildHistoryToggle(),
              const SizedBox(height: 12),

              if (_showHistory)
                _buildHistorySection(capture),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHeader(MapCaptureData capture, Color rarityColor) {
    return Row(
      children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(
              colors: [
                rarityColor.withOpacity(0.3),
                rarityColor.withOpacity(0.1),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            border: Border.all(color: rarityColor, width: 2),
          ),
          child: Icon(Icons.phishing, color: rarityColor, size: 22),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                capture.species,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: rarityColor.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: rarityColor.withOpacity(0.4),
                      ),
                    ),
                    child: Text(
                      capture.rarity.toUpperCase(),
                      style: TextStyle(
                        color: rarityColor,
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  if (capture.isOwn)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: AppTheme.accentBlue.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        context.l10n.sheetOwnCapture,
                        style: const TextStyle(
                          color: AppTheme.accentBlue,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildDataSection(MapCaptureData capture) {
    final date = capture.capturedAt;
    final dateStr = '${date.day}/${date.month}/${date.year}';
    final timeStr =
        '${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.06)),
      ),
      child: Column(
        children: [
          _dataRow(Icons.calendar_today, context.l10n.sheetFieldDate, dateStr),
          _divider(),
          _dataRow(Icons.access_time, context.l10n.sheetFieldTime, timeStr),
          _divider(),
          _dataRow(Icons.fingerprint, context.l10n.sheetFieldFishId, capture.fishId),
          _divider(),
          _dataRow(Icons.badge, context.l10n.sheetFieldCaptureId,
              capture.captureId.length > 12
                  ? '${capture.captureId.substring(0, 12)}...'
                  : capture.captureId),
          if (capture.userId != null) ...[
            _divider(),
            _dataRow(Icons.person, context.l10n.sheetFieldUser,
                capture.userId!.length > 10
                    ? '${capture.userId!.substring(0, 10)}...'
                    : capture.userId!),
          ],
        ],
      ),
    );
  }

  Widget _dataRow(IconData icon, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, color: Colors.white38, size: 16),
          const SizedBox(width: 10),
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 13,
            ),
          ),
          const Spacer(),
          Flexible(
            child: Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
              textAlign: TextAlign.right,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  Widget _divider() {
    return Divider(
      color: Colors.white.withOpacity(0.06),
      height: 1,
    );
  }

  Widget _buildCoordinatesSection(MapCaptureData capture) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.teal.withOpacity(0.2)),
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppTheme.teal.withOpacity(0.15),
            ),
            child: const Icon(Icons.location_on, color: AppTheme.teal, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.sheetFieldCoordinates,
                  style: const TextStyle(
                    color: AppTheme.teal,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  '${capture.latitude.toStringAsFixed(6)}, ${capture.longitude.toStringAsFixed(6)}',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 13,
                    fontFamily: 'monospace',
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHistoryToggle() {
    return GestureDetector(
      onTap: () => setState(() => _showHistory = !_showHistory),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: _showHistory
              ? AppTheme.teal.withOpacity(0.1)
              : AppTheme.darkSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: _showHistory
                ? AppTheme.teal.withOpacity(0.3)
                : Colors.white.withOpacity(0.06),
          ),
        ),
        child: Row(
          children: [
            Icon(
              Icons.account_tree,
              color: _showHistory ? AppTheme.teal : Colors.white54,
              size: 20,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.l10n.sheetHistoryTitle,
                    style: TextStyle(
                      color: _showHistory ? AppTheme.teal : Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    context.l10n.sheetHistorySubtitle,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.4),
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
            AnimatedRotation(
              turns: _showHistory ? 0.5 : 0,
              duration: const Duration(milliseconds: 200),
              child: Icon(
                Icons.keyboard_arrow_down,
                color: _showHistory ? AppTheme.teal : Colors.white38,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHistorySection(MapCaptureData capture) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.teal.withOpacity(0.15)),
      ),
      child: FishHistoryTimeline(
        fishId: capture.fishId,
        species: capture.species,
      ),
    );
  }
}
