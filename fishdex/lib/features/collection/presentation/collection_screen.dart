import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/czech_fish_catalog.dart';
import '../../../data/models/fish_capture.dart';
import '../../../data/repositories/captures_repository.dart';
import '../../../widgets/pressable_scale.dart';
import '../../auth/providers/auth_provider.dart';

/// Datos de un pez en la colección del usuario
class CollectionFish {
  final String fishId;
  final String species;
  final String rarity;
  final double sizeCm;
  final int timesSpotted;
  final DateTime firstSeen;
  final bool isDiscovered;
  final String? imageBase64; // URL or base64 string
  final String? czechName;
  final String? latinName;

  const CollectionFish({
    required this.fishId,
    required this.species,
    required this.rarity,
    required this.sizeCm,
    required this.timesSpotted,
    required this.firstSeen,
    this.isDiscovered = true,
    this.imageBase64,
    this.czechName,
    this.latinName,
  });
}

/// Provider de la colección del usuario — carga desde el servidor local (SQLite)
/// a través del CapturesRepository, y cruza con el catálogo de 45 especies checas.
final collectionProvider = FutureProvider<List<CollectionFish>>((ref) async {
  List<CollectionFish> discovered = [];

  try {
    final authUser = ref.read(authStateProvider).valueOrNull;
    if (authUser != null) {
      final capturesRepo = ref.read(capturesRepositoryProvider);
      final captures = await capturesRepo.getCapturesForUser(
        userId: authUser.$id,
        userRole: 'fisherman',
        limit: 200,
      );

      // Deduplicate by fishId — keep the entry with the latest capturedAt and
      // count total sightings per individual fish.
      final Map<String, FishCapture> fishMap = {};
      final Map<String, int> sightingCount = {};

      for (final capture in captures) {
        final id = capture.fishId;
        sightingCount[id] = (sightingCount[id] ?? 0) + 1;
        if (!fishMap.containsKey(id) ||
            capture.capturedAt.isAfter(fishMap[id]!.capturedAt)) {
          fishMap[id] = capture;
        }
      }

      // Convert FishCapture → CollectionFish
      discovered = fishMap.entries.map((entry) {
        final capture = entry.value;
        final catalogMatch = findCzechSpeciesByAnyName(capture.species);

        return CollectionFish(
          fishId: capture.fishId,
          species: catalogMatch?.englishName ?? capture.species,
          rarity: capture.rarity,
          sizeCm: capture.lengthCm ?? 0.0,
          timesSpotted: sightingCount[capture.fishId] ?? 1,
          firstSeen: capture.capturedAt,
          isDiscovered: true,
          imageBase64: capture.imageUrl,
          czechName: catalogMatch?.czechName,
          latinName: capture.scientificName ?? catalogMatch?.latinName,
        );
      }).toList();

      // Newest first
      discovered.sort((a, b) => b.firstSeen.compareTo(a.firstSeen));
    }
  } catch (e) {
    debugPrint('❌ Collection load error: $e');
  }

  // 2. Cross with catalog: undiscovered species shown as silhouettes
  final discoveredSpecies = discovered
      .map((f) => f.species.toLowerCase())
      .toSet();

  final undiscovered = czechFishCatalog
      .where((sp) => !discoveredSpecies.contains(sp.englishName.toLowerCase()))
      .map((sp) => CollectionFish(
            fishId: 'FISH-????',
            species: sp.englishName,
            rarity: sp.rarity,
            sizeCm: 0,
            timesSpotted: 0,
            firstSeen: DateTime.now(),
            isDiscovered: false,
            czechName: sp.czechName,
            latinName: sp.latinName,
          ))
      .toList();

  return [...discovered, ...undiscovered];
});

/// Pantalla de Colección - Pokédex de Peces
/// Grid de cartas coleccionables, peces descubiertos a color y no descubiertos como silueta
class CollectionScreen extends ConsumerStatefulWidget {
  const CollectionScreen({super.key});

  @override
  ConsumerState<CollectionScreen> createState() => _CollectionScreenState();
}

class _CollectionScreenState extends ConsumerState<CollectionScreen> {
  /// Filtro activo: null = todos, o 'common'/'uncommon'/'rare'/'legendary'
  String? _selectedFilter;

  @override
  Widget build(BuildContext context) {
    final allCollection =
        ref.watch(collectionProvider).valueOrNull ?? <CollectionFish>[];

    // Aplicar filtro de rareza
    final collection = _selectedFilter == null
        ? allCollection
        : allCollection
            .where((f) => f.rarity == _selectedFilter)
            .toList();

    final discovered = allCollection.where((f) => f.isDiscovered).length;
    final total = allCollection.length;

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          // Header con barra de progreso
          SliverAppBar(
            expandedHeight: 160,
            pinned: true,
            backgroundColor: AppTheme.darkBackground,
            flexibleSpace: FlexibleSpaceBar(
              background: _buildHeader(context, discovered, total),
            ),
            title: Text(context.l10n.collectionTitle),
          ),

          // Filtros
          SliverToBoxAdapter(
            child: _buildFilters(context),
          ),

          // Grid de peces
          SliverPadding(
            padding: EdgeInsets.fromLTRB(16, 16, 16,
                MediaQuery.of(context).padding.bottom + 100),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                childAspectRatio: 0.80,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
              ),
              delegate: SliverChildBuilderDelegate(
                (context, index) => _buildCollectionCard(
                  context,
                  collection[index],
                ),
                childCount: collection.length,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context, int discovered, int total) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFF0D2137),
            AppTheme.darkBackground,
          ],
        ),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 50, 24, 16),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              // Progreso de colección
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    context.l10n.collectionDiscovered(discovered),
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.8),
                      fontSize: 14,
                    ),
                  ),
                  Text(
                    '$discovered / $total',
                    style: const TextStyle(
                      color: AppTheme.gold,
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              // Barra de progreso
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: total > 0 ? discovered / total : 0,
                  minHeight: 10,
                  backgroundColor: AppTheme.darkSurfaceElevated,
                  valueColor: const AlwaysStoppedAnimation<Color>(AppTheme.gold),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFilters(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          _buildFilterChip(context.l10n.collectionFilterAll, null),
          _buildFilterChip(context.l10n.collectionFilterCommon, 'common'),
          _buildFilterChip(context.l10n.collectionFilterUncommon, 'uncommon'),
          _buildFilterChip(context.l10n.collectionFilterRare, 'rare'),
          _buildFilterChip(context.l10n.collectionFilterLegendary, 'legendary'),
        ],
      ),
    );
  }

  Widget _buildFilterChip(String label, String? filterValue) {
    final isSelected = _selectedFilter == filterValue;
    return Container(
      margin: const EdgeInsets.only(right: 8),
      child: FilterChip(
        label: Text(label),
        selected: isSelected,
        onSelected: (_) {
          setState(() {
            _selectedFilter = isSelected ? null : filterValue;
          });
        },
        selectedColor: AppTheme.accentBlue.withOpacity(0.3),
        backgroundColor: AppTheme.darkSurface,
        labelStyle: TextStyle(
          color: isSelected ? AppTheme.accentBlue : Colors.white60,
          fontSize: 13,
        ),
        side: BorderSide(
          color: isSelected
              ? AppTheme.accentBlue.withOpacity(0.5)
              : Colors.transparent,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
        ),
      ),
    );
  }

  Widget _buildCollectionCard(BuildContext context, CollectionFish fish) {
    if (!fish.isDiscovered) {
      return _buildUndiscoveredCard(context, fish);
    }
    return _buildDiscoveredCard(context, fish);
  }

  Widget _buildDiscoveredCard(BuildContext context, CollectionFish fish) {
    return PressableScale(
      onTap: () => _showFishDetail(context, fish),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(AppTheme.radiusLg),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              AppTheme.darkSurface,
              AppTheme.getRarityColor(fish.rarity).withOpacity(0.1),
            ],
          ),
          border: Border.all(
            color: AppTheme.getRarityColor(fish.rarity).withOpacity(0.4),
            width: 1.5,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Imagen del pez (annotated preview from server or placeholder)
            Expanded(
              flex: 3,
              child: Container(
                width: double.infinity,
                decoration: BoxDecoration(
                  borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(15),
                  ),
                  color: Colors.black.withOpacity(0.3),
                ),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    // Fish image (URL from server) or placeholder icon
                    ClipRRect(
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(15),
                      ),
                      child: fish.imageBase64 != null &&
                              fish.imageBase64!.isNotEmpty
                          ? Image.network(
                              fish.imageBase64!,
                              fit: BoxFit.cover,
                              alignment: Alignment.center,
                              errorBuilder: (_, __, ___) => Center(
                                child: Icon(
                                  Icons.phishing,
                                  size: 48,
                                  color: AppTheme.getRarityColor(fish.rarity)
                                      .withOpacity(0.6),
                                ),
                              ),
                            )
                          : Center(
                              child: Icon(
                                Icons.phishing,
                                size: 48,
                                color: AppTheme.getRarityColor(fish.rarity)
                                    .withOpacity(0.6),
                              ),
                            ),
                    ),
                    // Overlay: times spotted badge (top-right)
                    Positioned(
                      top: 8,
                      right: 8,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          context.l10n.collectionTimesSpotted(fish.timesSpotted),
                          style: const TextStyle(
                            color: Colors.white70,
                            fontSize: 10,
                          ),
                        ),
                      ),
                    ),
                    // Rarity dot (top-left)
                    Positioned(
                      top: 8,
                      left: 8,
                      child: Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: AppTheme.getRarityColor(fish.rarity),
                          boxShadow: [
                            BoxShadow(
                              color: AppTheme.getRarityColor(fish.rarity)
                                  .withOpacity(0.5),
                              blurRadius: 4,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // Info
            Expanded(
              flex: 2,
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      fish.species,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 13,
                        fontWeight: FontWeight.bold,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (fish.latinName != null)
                      Text(
                        fish.latinName!,
                        style: TextStyle(
                          color: Colors.white
                              .withOpacity(AppTheme.opacityMuted),
                          fontSize: 11,
                          fontStyle: FontStyle.italic,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    Row(
                      children: [
                        Icon(
                          Icons.straighten,
                          color: Colors.white.withOpacity(0.5),
                          size: 12,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '${fish.sizeCm > 0 ? fish.sizeCm.toStringAsFixed(0) : '?'} cm',
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.6),
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                    Text(
                      fish.fishId,
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.3),
                        fontSize: 10,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUndiscoveredCard(BuildContext context, CollectionFish fish) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppTheme.radiusLg),
        color: AppTheme.darkSurface.withOpacity(0.6),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white.withOpacity(0.04),
            ),
            child: Icon(
              Icons.help_outline,
              size: 36,
              color: Colors.white.withOpacity(0.18),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            '???',
            style: TextStyle(
              color: Colors.white.withOpacity(0.3),
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            context.l10n.collectionUndiscovered,
            style: TextStyle(
              color: Colors.white.withOpacity(0.2),
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  void _showFishDetail(BuildContext context, CollectionFish fish) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => _FishDetailSheet(fish: fish),
    );
  }
}

/// Bottom sheet con detalle completo del pez
class _FishDetailSheet extends StatelessWidget {
  final CollectionFish fish;

  const _FishDetailSheet({required this.fish});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.7,
      decoration: const BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
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

          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Fish image (large, annotated preview)
                  if (fish.imageBase64 != null && fish.imageBase64!.isNotEmpty)
                    Container(
                      width: double.infinity,
                      height: 200,
                      margin: const EdgeInsets.only(bottom: 20),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: AppTheme.getRarityColor(fish.rarity)
                              .withOpacity(0.4),
                        ),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(15),
                        child: Image.network(
                          fish.imageBase64!,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Center(
                            child: Icon(
                              Icons.phishing,
                              size: 64,
                              color: AppTheme.getRarityColor(fish.rarity)
                                  .withOpacity(0.5),
                            ),
                          ),
                        ),
                      ),
                    ),

                  // Header
                  Row(
                    children: [
                      Container(
                        width: 56,
                        height: 56,
                        decoration: BoxDecoration(
                          color: AppTheme.getRarityColor(fish.rarity)
                              .withOpacity(0.2),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Icon(
                          Icons.phishing,
                          size: 28,
                          color: AppTheme.getRarityColor(fish.rarity),
                        ),
                      ),
                      const SizedBox(width: 16),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              fish.species,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 20,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            if (fish.latinName != null)
                              Text(
                                fish.latinName!,
                                style: TextStyle(
                                  color: Colors.white.withOpacity(0.5),
                                  fontSize: 13,
                                  fontStyle: FontStyle.italic,
                                ),
                              ),
                            const SizedBox(height: 2),
                            Text(
                              fish.fishId,
                              style: TextStyle(
                                color: Colors.white.withOpacity(0.4),
                                fontSize: 12,
                                fontFamily: 'monospace',
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // Stats
                  Row(
                    children: [
                      _buildStat(
                        context.l10n.collectionSizeLabel,
                        fish.sizeCm > 0
                            ? '${fish.sizeCm.toStringAsFixed(0)} cm'
                            : '-',
                      ),
                      _buildStat(
                        context.l10n.collectionSightingsLabel,
                        '${fish.timesSpotted}',
                      ),
                      _buildStat(
                        context.l10n.collectionRarityLabel,
                        fish.rarity.toUpperCase(),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // Timeline entry
                  Text(
                    context.l10n.collectionHistoryTitle,
                    style: const TextStyle(
                      color: Colors.white54,
                      fontSize: 12,
                      letterSpacing: 1,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  _buildSightingEntry(
                    context.l10n.collectionFirstSighting,
                    fish.firstSeen,
                    fish.sizeCm,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStat(String label, String value) {
    return Expanded(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 4),
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: AppTheme.darkSurfaceElevated,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Text(
              value,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                color: Colors.white.withOpacity(0.5),
                fontSize: 11,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSightingEntry(String title, DateTime date, double size) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.darkSurfaceElevated,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: AppTheme.accentBlue,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  '${date.day}/${date.month}/${date.year}'
                  '${size > 0 ? ' — ${size.toStringAsFixed(0)} cm' : ''}',
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
    );
  }
}
