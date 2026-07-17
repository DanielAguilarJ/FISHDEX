import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../data/models/fishing_area.dart';
import '../../../data/repositories/fishing_spots_repository.dart';
import '../../../data/services/areas_service.dart';
import '../../auth/providers/auth_provider.dart';
import '../../map/providers/map_providers.dart';
import '../../camera/providers/capture_metadata_provider.dart';

/// Pantalla de marcado rápido de spot de pesca al estilo acción rápida
/// Se accede desde el Speed Dial central del menú
class QuickSpotScreen extends ConsumerStatefulWidget {
  const QuickSpotScreen({super.key});

  @override
  ConsumerState<QuickSpotScreen> createState() => _QuickSpotScreenState();
}

class _QuickSpotScreenState extends ConsumerState<QuickSpotScreen>
    with SingleTickerProviderStateMixin {
  void _goBack() {
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    } else {
      context.go('/map');
    }
  }

  final _nameController = TextEditingController();
  final _descController = TextEditingController();
  final _areaSearchController = TextEditingController();
  String _selectedWaterType = 'rio';
  bool _isSaving = false;

  // Area selection state
  List<FishingArea> _nearbyAreas = [];
  List<FishingArea> _filteredAreas = [];
  FishingArea? _selectedArea;
  bool _isLoadingAreas = true;
  bool _showAllAreas = false;

  late AnimationController _entranceController;
  late Animation<Offset> _slideAnim;
  late Animation<double> _fadeAnim;

  // Opciones de tipo de agua: (id, ícono, color)
  static const _waterTypes = [
    ('rio', Icons.water, Color(0xFF1565C0)),
    ('embalse', Icons.water_drop_rounded, Color(0xFF0097A7)),
    ('lago', Icons.landscape_rounded, Color(0xFF2E7D32)),
    ('mar', Icons.waves_rounded, Color(0xFF0D47A1)),
  ];

  @override
  void initState() {
    super.initState();
    _entranceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );
    _slideAnim = Tween<Offset>(
      begin: const Offset(0, 0.15),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _entranceController, curve: Curves.easeOutCubic),
    );
    _fadeAnim = CurvedAnimation(
      parent: _entranceController,
      curve: Curves.easeOut,
    );
    _entranceController.forward();

    // Load nearby areas after location is available
    _loadNearbyAreas();
  }

  /// Load nearby fishing areas based on current GPS location
  Future<void> _loadNearbyAreas() async {
    setState(() => _isLoadingAreas = true);
    try {
      final location = ref.read(userLocationProvider).valueOrNull;
      if (location != null) {
        final areasService = AreasService();
        final areas = await areasService.getNearbyAreas(
          location.latitude,
          location.longitude,
          radiusKm: 15.0,
        );
        if (mounted) {
          setState(() {
            _nearbyAreas = areas;
            _filteredAreas = areas;
            _isLoadingAreas = false;
          });
        }
      } else {
        // GPS not available - show empty list with option to search all
        if (mounted) {
          setState(() {
            _isLoadingAreas = false;
            _showAllAreas = true;
          });
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoadingAreas = false);
      }
    }
  }

  /// Filter areas based on search text
  void _filterAreas(String query) {
    if (query.isEmpty) {
      setState(() => _filteredAreas = _nearbyAreas);
    } else {
      final lowerQuery = query.toLowerCase();
      setState(() {
        _filteredAreas = _nearbyAreas
            .where((area) =>
                area.name.toLowerCase().contains(lowerQuery) ||
                area.code.contains(query))
            .toList();
      });
    }
  }

  @override
  void dispose() {
    _entranceController.dispose();
    _nameController.dispose();
    _descController.dispose();
    _areaSearchController.dispose();
    super.dispose();
  }

  String _waterTypeLabel(String type) {
    switch (type) {
      case 'rio':
        return context.l10n.quickSpotWaterRiver;
      case 'embalse':
        return context.l10n.quickSpotWaterReservoir;
      case 'lago':
        return context.l10n.quickSpotWaterLake;
      case 'mar':
        return context.l10n.quickSpotWaterSea;
      default:
        return type;
    }
  }

  // ── Guardar el spot ────────────────────────────────────────────────────────────
  Future<void> _saveSpot() async {
    final l10n = context.l10n;
    final location = ref.read(userLocationProvider).valueOrNull;
    if (location == null) {
      _showError(l10n.quickSpotErrorGps);
      return;
    }

    final name = _nameController.text.trim();
    if (name.isEmpty) {
      _showError(l10n.quickSpotErrorName);
      return;
    }

    // Store selected area in capture metadata provider
    if (_selectedArea != null) {
      ref.read(captureMetadataProvider.notifier).setArea(
            _selectedArea!.code,
            _selectedArea!.name,
          );
    }

    setState(() => _isSaving = true);

    try {
      final prefs = await SharedPreferences.getInstance();
      final isDemoMode = prefs.getBool('is_demo_mode') ?? false;

      if (isDemoMode) {
        // MODO DEMO: simular guardado y mostrar éxito sin llamar a Appwrite
        await Future.delayed(const Duration(milliseconds: 800));
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle_rounded, color: Colors.white),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    l10n.quickSpotSavedDemo(name),
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
            backgroundColor: AppTheme.successGreen,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            duration: const Duration(seconds: 4),
          ),
        );
        context.go('/map');
        return;
      }

      // MODO REAL: obtener userId del usuario autenticado
      final authUser = await ref.read(authStateProvider.future);
      final userId = authUser?.$id ?? 'anonymous';

      final databases = ref.read(appwriteDatabasesProvider);
      final repo = FishingSpotsRepository(databases: databases);

      await repo.createSpot(
        name: name,
        latitude: location.latitude,
        longitude: location.longitude,
        waterType: _selectedWaterType,
        createdBy: userId,
        description: _descController.text.trim().isEmpty
            ? null
            : _descController.text.trim(),
      );

      if (!mounted) return;

      // Éxito → feedback visual y navegar al mapa
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              const Icon(Icons.check_circle_rounded, color: Colors.white),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  l10n.quickSpotSaved(name),
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          backgroundColor: AppTheme.successGreen,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 3),
        ),
      );

      context.go('/map');
    } catch (e) {
      if (!mounted) return;
      setState(() => _isSaving = false);
      _showError(context.l10n.quickSpotErrorSave(e.toString()));
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: Colors.red.shade700,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  // ── Build ──────────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: FadeTransition(
        opacity: _fadeAnim,
        child: SlideTransition(
          position: _slideAnim,
          child: Column(
            children: [
              _buildHeader(context),
              Expanded(
                child: SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(20, 20, 20,
                      MediaQuery.of(context).padding.bottom + 120),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildLocationCard(),
                      const SizedBox(height: 24),
                      _buildSectionLabel(context.l10n.quickSpotFishingAreaLabel),
                      const SizedBox(height: 8),
                      _buildAreaSelector(),
                      const SizedBox(height: 24),
                      _buildSectionLabel(context.l10n.quickSpotNameLabel),
                      const SizedBox(height: 8),
                      _buildNameField(),
                      const SizedBox(height: 20),
                      _buildSectionLabel(context.l10n.quickSpotWaterType),
                      const SizedBox(height: 12),
                      _buildWaterTypeGrid(),
                      const SizedBox(height: 20),
                      _buildSectionLabel(context.l10n.quickSpotDescription),
                      const SizedBox(height: 8),
                      _buildDescField(),
                      const SizedBox(height: 32),
                      _buildSaveButton(),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ── Area Selector (dynamic dropdown) ───────────────────────────────────────────
  Widget _buildAreaSelector() {
    if (_isLoadingAreas) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppTheme.darkSurface,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          children: [
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.accentBlue),
            ),
            const SizedBox(width: 12),
            Text(
              context.l10n.quickSpotLoadingAreas,
              style: const TextStyle(color: Colors.white54, fontSize: 13),
            ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Search field
        TextField(
          controller: _areaSearchController,
          style: const TextStyle(color: Colors.white, fontSize: 13),
          onChanged: _filterAreas,
          decoration: InputDecoration(
            hintText: context.l10n.quickSpotSearchAreaHint,
            hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
            filled: true,
            fillColor: AppTheme.darkSurface,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide.none,
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: const BorderSide(color: AppTheme.accentBlue, width: 2),
            ),
            prefixIcon: const Icon(Icons.search, color: AppTheme.accentBlue, size: 20),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          ),
        ),
        const SizedBox(height: 8),
        // Selected area display
        if (_selectedArea != null)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.accentBlue.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppTheme.accentBlue.withOpacity(0.4)),
            ),
            child: Row(
              children: [
                const Icon(Icons.location_on, color: AppTheme.accentBlue, size: 16),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _selectedArea!.displayName,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                if (_selectedArea!.distanceKm != null)
                  Text(
                    _selectedArea!.distanceDisplay,
                    style: const TextStyle(color: Colors.white54, fontSize: 11),
                  ),
                const SizedBox(width: 8),
                GestureDetector(
                  onTap: () => setState(() => _selectedArea = null),
                  child: const Icon(Icons.close, color: Colors.white54, size: 16),
                ),
              ],
            ),
          ),
        // Area list
        if (_selectedArea == null && _filteredAreas.isNotEmpty)
          Container(
            constraints: const BoxConstraints(maxHeight: 180),
            margin: const EdgeInsets.only(top: 8),
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(12),
            ),
            child: ListView.separated(
              shrinkWrap: true,
              padding: const EdgeInsets.symmetric(vertical: 4),
              itemCount: _filteredAreas.length,
              separatorBuilder: (_, __) => Divider(
                color: Colors.white.withOpacity(0.05),
                height: 1,
              ),
              itemBuilder: (context, index) {
                final area = _filteredAreas[index];
                return ListTile(
                  dense: true,
                  visualDensity: VisualDensity.compact,
                  leading: const Icon(
                    Icons.water,
                    color: AppTheme.accentBlue,
                    size: 18,
                  ),
                  title: Text(
                    area.displayName,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  trailing: area.distanceKm != null
                      ? Text(
                          area.distanceDisplay,
                          style: const TextStyle(
                            color: Colors.white38,
                            fontSize: 11,
                          ),
                        )
                      : null,
                  onTap: () {
                    setState(() {
                      _selectedArea = area;
                      _areaSearchController.clear();
                    });
                  },
                );
              },
            ),
          ),
        // Empty state or "search all" option
        if (_filteredAreas.isEmpty && !_isLoadingAreas)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _nearbyAreas.isEmpty
                  ? context.l10n.quickSpotNoAreasNearby
                  : context.l10n.quickSpotNoAreasMatching,
              style: const TextStyle(color: Colors.white38, fontSize: 12),
            ),
          ),
      ],
    );
  }

  // ── Header con gradiente verde ─────────────────────────────────────────────────
  Widget _buildHeader(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        top: MediaQuery.of(context).padding.top + 12,
        left: 20,
        right: 20,
        bottom: 18,
      ),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [Color(0xFF2E7D32), Color(0xFF1B5E20)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Row(
        children: [
          GestureDetector(
            onTap: _goBack,
            child: Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.black.withOpacity(0.2),
              ),
              child: const Icon(
                Icons.arrow_back_ios_new_rounded,
                color: Colors.white,
                size: 18,
              ),
            ),
          ),
          const SizedBox(width: 14),
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white.withOpacity(0.15),
            ),
            child: const Icon(
              Icons.add_location_alt_rounded,
              color: Colors.white,
              size: 24,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.quickSpotTitle,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.2,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  context.l10n.quickSpotSubtitle,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Tarjeta de ubicación actual ────────────────────────────────────────────────
  Widget _buildLocationCard() {
    final locationAsync = ref.watch(userLocationProvider);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.successGreen.withOpacity(0.35),
          width: 1.5,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppTheme.successGreen.withOpacity(0.12),
            ),
            child: const Icon(
              Icons.my_location_rounded,
              color: AppTheme.successGreen,
              size: 24,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: locationAsync.when(
              data: (location) => location != null
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          context.l10n.quickSpotLocationCurrent,
                          style: const TextStyle(
                            color: Colors.white54,
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          '${location.latitude.toStringAsFixed(5)}, ${location.longitude.toStringAsFixed(5)}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            fontFamily: 'monospace',
                          ),
                        ),
                      ],
                    )
                  : Text(
                      context.l10n.quickSpotLocationNone,
                      style: const TextStyle(color: Colors.orange, fontSize: 14),
                    ),
              loading: () => Text(
                context.l10n.quickSpotLocationGetting,
                style: const TextStyle(color: Colors.white54, fontSize: 14),
              ),
              error: (_, __) => Text(
                context.l10n.quickSpotLocationError,
                style: const TextStyle(color: Colors.redAccent, fontSize: 14),
              ),
            ),
          ),
          const SizedBox(width: 8),
          locationAsync.when(
            data: (l) => Icon(
              l != null
                  ? Icons.check_circle_rounded
                  : Icons.error_outline_rounded,
              color: l != null ? AppTheme.successGreen : Colors.orange,
              size: 22,
            ),
            loading: () => const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: AppTheme.accentBlue,
              ),
            ),
            error: (_, __) =>
                const Icon(Icons.error_outline_rounded, color: Colors.red),
          ),
        ],
      ),
    );
  }

  // ── Helpers de UI ───────────────────────────────────────────────────────────────
  Widget _buildSectionLabel(String text) {
    return Text(
      text,
      style: const TextStyle(
        color: Colors.white70,
        fontSize: 13,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.4,
      ),
    );
  }

  Widget _buildNameField() {
    return TextField(
      controller: _nameController,
      style: const TextStyle(color: Colors.white),
      textCapitalization: TextCapitalization.sentences,
      decoration: InputDecoration(
        hintText: context.l10n.quickSpotNameHint,
        hintStyle: const TextStyle(color: Colors.white24),
        filled: true,
        fillColor: AppTheme.darkSurface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide:
              const BorderSide(color: AppTheme.successGreen, width: 2),
        ),
        prefixIcon: const Icon(
          Icons.location_on_rounded,
          color: AppTheme.successGreen,
          size: 20,
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
    );
  }

  Widget _buildWaterTypeGrid() {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 10,
      mainAxisSpacing: 10,
      childAspectRatio: 2.8,
      children: _waterTypes.map((type) {
        final isSelected = _selectedWaterType == type.$1;
        final label = _waterTypeLabel(type.$1);
        return GestureDetector(
          onTap: () => setState(() => _selectedWaterType = type.$1),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: isSelected
                  ? type.$3.withOpacity(0.18)
                  : AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isSelected ? type.$3 : Colors.white12,
                width: isSelected ? 2 : 1,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  type.$2,
                  color: isSelected ? type.$3 : Colors.white38,
                  size: 18,
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    label,
                    style: TextStyle(
                      color: isSelected ? type.$3 : Colors.white38,
                      fontWeight: isSelected
                          ? FontWeight.w700
                          : FontWeight.normal,
                      fontSize: 13,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _buildDescField() {
    return TextField(
      controller: _descController,
      style: const TextStyle(color: Colors.white),
      maxLines: 2,
      textCapitalization: TextCapitalization.sentences,
      decoration: InputDecoration(
        hintText: context.l10n.quickSpotDescriptionHint,
        hintStyle: const TextStyle(color: Colors.white24),
        filled: true,
        fillColor: AppTheme.darkSurface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide:
              const BorderSide(color: AppTheme.successGreen, width: 2),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      ),
    );
  }

  Widget _buildSaveButton() {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton.icon(
        onPressed: _isSaving ? null : _saveSpot,
        icon: _isSaving
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2.5,
                  color: Colors.white,
                ),
              )
            : const Icon(Icons.save_alt_rounded, size: 22),
        label: Text(
          _isSaving
              ? context.l10n.quickSpotSaving
              : context.l10n.quickSpotSaveButton,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.8,
          ),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: AppTheme.successGreen,
          foregroundColor: Colors.white,
          disabledBackgroundColor: AppTheme.successGreen.withOpacity(0.35),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          elevation: 4,
        ),
      ),
    );
  }
}
