import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/identify_result.dart';
import '../../../data/repositories/sightings_repository.dart';
import '../../auth/providers/auth_provider.dart';
import '../widgets/fish_card.dart';
import '../widgets/confetti_overlay.dart';
import '../widgets/xp_animation.dart';
import '../widgets/reunion_info.dart';

/// Pantalla de resultado de identificación
/// Muestra diferentes animaciones según si el pez es nuevo o un reencuentro
class ResultScreen extends ConsumerStatefulWidget {
  final IdentifyResult result;

  /// Primary constructor with IdentifyResult
  const ResultScreen({super.key, required this.result});

  static bool _parseSqliteBool(dynamic value, {bool defaultValue = false}) {
    if (value == null) return defaultValue;
    if (value is bool) return value;
    if (value is int) return value == 1;
    if (value is num) return value.toInt() == 1;
    if (value is String) {
      final lower = value.toLowerCase().trim();
      return lower == '1' || lower == 'true' || lower == 'yes';
    }
    return defaultValue;
  }

  /// Factory constructor from job completion data (v2 job-based flow)
  factory ResultScreen.fromJobData({Key? key, required Map<String, dynamic> jobData}) {
    final isNew = _parseSqliteBool(
      jobData['is_new_fish'],
      defaultValue: true,
    );

    final fishId = jobData['fish_id'] as String? ??
        jobData['result_fish_id'] as String? ??
        '';

    final speciesEnglish = jobData['species_english'] as String? ??
        jobData['species_common'] as String? ??
        jobData['species_slug'] as String? ??
        'Unknown';

    final result = IdentifyResult(
      success: true,
      fishId: fishId,
      species: speciesEnglish,
      scientificName: jobData['species_latin'] as String?,
      confidence: (jobData['confidence'] as num?)?.toDouble() ?? 0.0,
      isNew: isNew,
      estimatedSizeCm: (jobData['size_cm'] as num?)?.toDouble() ?? 0.0,
      rarity: jobData['rarity'] as String? ?? 'common',
      xpEarned: (jobData['xp_earned'] as num?)?.toInt() ?? 10,
      message: isNew
          ? 'New fish discovered!'
          : 'Recapture! This fish has been seen before.',
      timestamp: jobData['completed_at'] as String? ??
          jobData['created_at'] as String? ??
          DateTime.now().toIso8601String(),
      areaCode: jobData['area_code'] as String?,
      areaName: jobData['area_name'] as String?,
      speciesCzech: jobData['species_czech'] as String?,
    );
    return ResultScreen(key: key, result: result);
  }

  @override
  ConsumerState<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends ConsumerState<ResultScreen>
    with TickerProviderStateMixin {
  late AnimationController _entranceController;
  late AnimationController _cardController;
  late Animation<double> _fadeIn;
  late Animation<double> _slideUp;
  late Animation<double> _cardScale;
  late Animation<double> _cardRotation;

  bool _showConfetti = false;
  bool _showXP = false;
  bool _showDetails = false;
  bool _historyExpanded = false;

  @override
  void initState() {
    super.initState();

    // Animación de entrada del título
    _entranceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );

    _fadeIn = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _entranceController, curve: Curves.easeOut),
    );

    _slideUp = Tween<double>(begin: 50, end: 0).animate(
      CurvedAnimation(parent: _entranceController, curve: Curves.easeOutBack),
    );

    // Animación de la carta del pez
    _cardController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );

    _cardScale = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _cardController, curve: Curves.elasticOut),
    );

    _cardRotation = Tween<double>(begin: 0.03, end: 0.0).animate(
      CurvedAnimation(parent: _cardController, curve: Curves.easeOut),
    );

    // Secuencia de animaciones
    _startAnimationSequence();
  }

  Future<void> _startAnimationSequence() async {
    // Guardar el avistamiento en Appwrite en background (sin bloquear animaciones)
    _saveSighting();

    // Secuencia compacta: 1200ms total (en vez de 2300ms)
    // 1. Mostrar confeti si es nuevo
    if (widget.result.isNew) {
      await Future.delayed(const Duration(milliseconds: 100));
      setState(() => _showConfetti = true);
    }

    // 2. Animar título
    await Future.delayed(const Duration(milliseconds: 150));
    _entranceController.forward();

    // 3. Animar carta del pez
    await Future.delayed(const Duration(milliseconds: 300));
    _cardController.forward();

    // 4. Mostrar XP (stagger 100ms después de la carta)
    await Future.delayed(const Duration(milliseconds: 400));
    setState(() => _showXP = true);

    // 5. Mostrar detalles
    await Future.delayed(const Duration(milliseconds: 200));
    setState(() => _showDetails = true);
  }

  /// Guarda el avistamiento en Appwrite sin bloquear la UI.
  /// En modo demo o sin sesión, no hace nada.
  /// Obtiene la ubicación GPS actual para guardarla con el avistamiento.
  Future<void> _saveSighting() async {
    // Sighting registration is already completed server-side during the identification job pipeline.
    debugPrint('📋 Sighting registration completed locally by server pipeline.');
  }

  /// Open area URL in browser
  Future<void> _openAreaUrl() async {
    final url = widget.result.areaUrl;
    if (url != null && url.isNotEmpty) {
      try {
        await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
      } catch (_) {}
    }
  }

  @override
  void dispose() {
    _entranceController.dispose();
    _cardController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: Stack(
        children: [
          // Fondo con gradiente según resultado
          _buildBackground(),

          // Contenido principal
          SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: [
                  const SizedBox(height: 20),

                  // Título animado
                  _buildTitle(),
                  const SizedBox(height: 24),

                  // Area name chip
                  if (_showDetails && widget.result.areaName != null)
                    _buildAreaChip(),
                  if (_showDetails && widget.result.areaName != null)
                    const SizedBox(height: 12),

                  // Species bilingual display
                  if (_showDetails &&
                      (widget.result.speciesCzech != null ||
                          widget.result.speciesEnglish != null))
                    _buildSpeciesBilingual(),
                  if (_showDetails &&
                      (widget.result.speciesCzech != null ||
                          widget.result.speciesEnglish != null))
                    const SizedBox(height: 12),

                  // Catch number badge
                  if (_showDetails &&
                      widget.result.catchNumber != null &&
                      widget.result.catchNumber! > 1)
                    _buildCatchNumberBadge(),
                  if (_showDetails &&
                      widget.result.catchNumber != null &&
                      widget.result.catchNumber! > 1)
                    const SizedBox(height: 12),

                  // Carta del pez
                  _buildFishCard(),
                  const SizedBox(height: 20),

                  // XP ganada
                  if (_showXP) _buildXPSection(),
                  const SizedBox(height: 16),

                  // Detalles (reencuentro o nuevo)
                  if (_showDetails) _buildDetailsSection(),
                  const SizedBox(height: 16),

                  // Full history for researchers
                  if (_showDetails && widget.result.userRole == 'researcher')
                    _buildFullHistorySection(),
                  const SizedBox(height: 24),

                  // Botones de acción
                  if (_showDetails) _buildActions(),
                  const SizedBox(height: 40),
                ],
              ),
            ),
          ),

          // Confeti overlay
          if (_showConfetti) const ConfettiOverlay(),

          // Botón cerrar (44px min hit area)
          Positioned(
            top: MediaQuery.of(context).padding.top + 12,
            right: 16,
            child: GestureDetector(
              onTap: () => Navigator.of(context).popUntil(
                (route) => route.isFirst,
              ),
              behavior: HitTestBehavior.opaque,
              child: Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withOpacity(0.12),
                ),
                child: const Icon(Icons.close, color: Colors.white70, size: 22),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Area name chip with link to rybsvaz.cz
  Widget _buildAreaChip() {
    return GestureDetector(
      onTap: widget.result.areaUrl != null ? _openAreaUrl : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: AppTheme.accentBlue.withOpacity(0.15),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppTheme.accentBlue.withOpacity(0.3)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.location_on, color: AppTheme.accentBlue, size: 16),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                widget.result.areaName!,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (widget.result.areaUrl != null) ...[
              const SizedBox(width: 6),
              const Icon(Icons.open_in_new, color: AppTheme.accentBlue, size: 14),
            ],
          ],
        ),
      ),
    );
  }

  /// Species display in both Czech and English
  Widget _buildSpeciesBilingual() {
    final czech = widget.result.speciesCzech ?? '';
    final english = widget.result.speciesEnglish ?? '';
    final display = czech.isNotEmpty && english.isNotEmpty
        ? '$czech / $english'
        : czech.isNotEmpty
            ? czech
            : english;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.successGreen.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.pets, color: AppTheme.successGreen, size: 16),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              display,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w500,
                fontStyle: FontStyle.italic,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  /// Catch number badge
  Widget _buildCatchNumberBadge() {
    final n = widget.result.catchNumber!;
    final suffix = n == 2
        ? '2nd'
        : n == 3
            ? '3rd'
            : '${n}th';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.energyOrange.withOpacity(0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.energyOrange.withOpacity(0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.repeat, color: AppTheme.energyOrange, size: 16),
          const SizedBox(width: 6),
          Text(
            '$suffix catch of this individual fish!',
            style: const TextStyle(
              color: AppTheme.energyOrange,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  /// Full history expandable section (researchers only)
  Widget _buildFullHistorySection() {
    final result = widget.result;
    // full_history is in the JSON response but not directly in IdentifyResult model
    // For researchers, show the previous_data at minimum
    if (result.previousData == null && result.catchNumber == null) {
      return const SizedBox.shrink();
    }

    return Container(
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.purple.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          ListTile(
            leading: const Icon(Icons.history, color: Colors.purple, size: 20),
            title: const Text(
              'Full History (Researcher View)',
              style: TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.bold,
              ),
            ),
            trailing: Icon(
              _historyExpanded
                  ? Icons.expand_less
                  : Icons.expand_more,
              color: Colors.white54,
            ),
            onTap: () => setState(() => _historyExpanded = !_historyExpanded),
          ),
          if (_historyExpanded && result.previousData != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _buildHistoryRow(
                    'First seen',
                    result.previousData!.firstSeenDate,
                  ),
                  _buildHistoryRow(
                    'Total sightings',
                    '${result.previousData!.totalSightings}',
                  ),
                  _buildHistoryRow(
                    'Last seen',
                    result.previousData!.lastSeenDate,
                  ),
                  _buildHistoryRow(
                    'Growth',
                    '${result.previousData!.growthCm.toStringAsFixed(1)} cm',
                  ),
                  if (result.previousData!.firstSeenLocation != null)
                    _buildHistoryRow(
                      'Location',
                      result.previousData!.firstSeenLocation!,
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildHistoryRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12),
          ),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBackground() {
    final colors = widget.result.isNew
        ? [AppTheme.darkBackground, const Color(0xFF0A2E1A)] // Verde oscuro
        : [AppTheme.darkBackground, const Color(0xFF1A1A3E)]; // Azul oscuro

    return Container(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: Alignment.topCenter,
          radius: 1.5,
          colors: colors,
        ),
      ),
    );
  }

  Widget _buildTitle() {
    return AnimatedBuilder(
      animation: _entranceController,
      builder: (context, child) {
        return Transform.translate(
          offset: Offset(0, _slideUp.value),
          child: Opacity(
            opacity: _fadeIn.value,
            child: Column(
              children: [
                // Badge de rareza
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: AppTheme.getRarityColor(widget.result.rarity)
                        .withOpacity(0.2),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: AppTheme.getRarityColor(widget.result.rarity)
                          .withOpacity(0.5),
                    ),
                  ),
                  child: Text(
                    widget.result.rarity.toUpperCase(),
                    style: TextStyle(
                      color: AppTheme.getRarityColor(widget.result.rarity),
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 2,
                    ),
                  ),
                ),
                const SizedBox(height: 12),

                // Título principal
                Text(
                  widget.result.isNew
                      ? context.l10n.resultNewDiscovery
                      : context.l10n.resultReunion,
                  style: Theme.of(context).textTheme.displayMedium?.copyWith(
                        color: widget.result.isNew
                            ? AppTheme.successGreen
                            : AppTheme.energyOrange,
                        shadows: [
                          Shadow(
                            color: (widget.result.isNew
                                    ? AppTheme.successGreen
                                    : AppTheme.energyOrange)
                                .withOpacity(0.5),
                            blurRadius: 20,
                          ),
                        ],
                      ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFishCard() {
    return AnimatedBuilder(
      animation: _cardController,
      builder: (context, child) {
        return Transform.scale(
          scale: _cardScale.value,
          child: Transform.rotate(
            angle: _cardRotation.value,
            child: FishCard(
              fishId: widget.result.fishId,
              species: widget.result.species,
              sizeCm: widget.result.estimatedSizeCm,
              rarity: widget.result.rarity,
              confidence: widget.result.confidence,
              imageBase64: widget.result.frameUsed,
              isNew: widget.result.isNew,
            ),
          ),
        );
      },
    );
  }

  Widget _buildXPSection() {
    return XPAnimation(
      xpEarned: widget.result.xpEarned,
      isNewFish: widget.result.isNew,
    );
  }

  Widget _buildDetailsSection() {
    if (!widget.result.isNew && widget.result.previousData != null) {
      return ReunionInfo(previousData: widget.result.previousData!);
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.info_outline, color: AppTheme.accentBlue, size: 18),
              const SizedBox(width: 8),
              Text(
                context.l10n.resultDetails,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.8),
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _buildDetailRow(context.l10n.resultFishId, widget.result.fishId),
          _buildDetailRow(context.l10n.resultSpecies, widget.result.species),
          if (widget.result.scientificName != null)
            _buildDetailRow('Scientific', widget.result.scientificName!),
          _buildDetailRow(
            context.l10n.resultEstimatedSize,
            '${widget.result.estimatedSizeCm} cm',
          ),
          _buildDetailRow(
            context.l10n.resultAiConfidence,
            '${(widget.result.confidence * 100).toStringAsFixed(1)}%',
          ),
          if (widget.result.areaCode != null)
            _buildDetailRow('Area Code', widget.result.areaCode!),
        ],
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 13,
            ),
          ),
          Flexible(
            child: Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActions() {
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          height: 52,
          child: ElevatedButton.icon(
            onPressed: () {
              Navigator.of(context).popUntil((route) => route.isFirst);
            },
            icon: const Icon(Icons.collections_bookmark),
            label: Text(context.l10n.resultViewCollection),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.accentBlue,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: OutlinedButton.icon(
            onPressed: () {
              Navigator.of(context).popUntil((route) => route.isFirst);
            },
            icon: const Icon(Icons.map),
            label: Text(context.l10n.resultBackToMap),
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.white70,
              side: const BorderSide(color: Colors.white24),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
