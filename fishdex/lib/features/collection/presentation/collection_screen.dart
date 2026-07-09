import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/czech_fish_catalog.dart';
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
  final String? imageBase64;
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

/// Provider de la colección del usuario — carga desde fish_individuals de Appwrite
/// y cruza con el catálogo de 45 especies checas para mostrar la colección completa.
final collectionProvider = FutureProvider<List<CollectionFish>>((ref) async {
  // 1. Obtener capturas reales del usuario desde Appwrite
  List<CollectionFish> discovered = [];

  try {
    final prefs = await SharedPreferences.getInstance();
    final isDemoMode = prefs.getBool('is_demo_mode') ?? false;

    if (!isDemoMode) {
      final authUser = ref.read(authStateProvider).valueOrNull;
      if (authUser != null) {
        final databases = ref.read(appwriteDatabasesProvider);
        final response = await databases.listDocuments(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishIndividualsCollection,
          queries: [
            'equal("first_seen_by", ["${authUser.$id}"])',
            'orderDesc("\$createdAt")',
            'limit(100)',
          ],
        );

        discovered = response.documents.map((doc) {
          final data = doc.data;
          final speciesName = data['species'] as String? ?? 'Desconocido';
          final catalogMatch = findCzechSpeciesByAnyName(speciesName);
          return CollectionFish(
            fishId: doc.$id,
            species: catalogMatch?.englishName ?? speciesName,
            rarity: data['rarity'] as String? ?? catalogMatch?.rarity ?? 'common',
            sizeCm: (data['estimated_size_cm'] as num?)?.toDouble() ?? 0.0,
            timesSpotted: (data['total_sightings'] as num?)?.toInt() ?? 1,
            firstSeen: data['first_seen_date'] != null
                ? DateTime.tryParse(data['first_seen_date'] as String) ??
                    DateTime.now()
                : DateTime.now(),
            isDiscovered: true,
            czechName: catalogMatch?.czechName,
            latinName: catalogMatch?.latinName,
          );
        }).toList();
      }
    }
  } catch (e) {
    // Si falla Appwrite, seguimos con discovered vacío
  }

  // 2. Cruzar con el catálogo: las especies no descubiertas se añaden como siluetas
  final discoveredNames = discovered
      .map((f) => f.species.toLowerCase())
      .toSet();

  final undiscovered = czechFishCatalog
      .where((sp) => !discoveredNames.contains(sp.englishName.toLowerCase()))
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

  // 3. Descubiertos primero, luego no descubiertos
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
            // Imagen del pez
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
                  children: [
                    Center(
                      child: Icon(
                        Icons.phishing,
                        size: 48,
                        color: AppTheme.getRarityColor(fish.rarity)
                            .withOpacity(0.6),
                      ),
                    ),
                    // Badge de veces visto
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
                    // Indicador de rareza
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
                          color: Colors.white.withOpacity(AppTheme.opacityMuted),
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
                          '${fish.sizeCm} cm',
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
          // Silueta del pez con más presencia
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
                  // Header del pez
                  Row(
                    children: [
                      // Icono grande
                      Container(
                        width: 64,
                        height: 64,
                        decoration: BoxDecoration(
                          color: AppTheme.getRarityColor(fish.rarity)
                              .withOpacity(0.2),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Icon(
                          Icons.phishing,
                          size: 32,
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
                                fontSize: 22,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              fish.fishId,
                              style: TextStyle(
                                color: Colors.white.withOpacity(0.5),
                                fontSize: 13,
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
                      _buildStat(context.l10n.collectionSizeLabel, '${fish.sizeCm} cm'),
                      _buildStat(context.l10n.collectionSightingsLabel, '${fish.timesSpotted}'),
                      _buildStat(context.l10n.collectionRarityLabel, fish.rarity.toUpperCase()),
                    ],
                  ),
                  const SizedBox(height: 24),
                  
                  // Timeline de avistamientos
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
                  
                  // Avistamiento de ejemplo
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
                  '${date.day}/${date.month}/${date.year} - $size cm',
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
