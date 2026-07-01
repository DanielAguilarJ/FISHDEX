import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/identify_result.dart';

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

  const CollectionFish({
    required this.fishId,
    required this.species,
    required this.rarity,
    required this.sizeCm,
    required this.timesSpotted,
    required this.firstSeen,
    this.isDiscovered = true,
    this.imageBase64,
  });
}

/// Provider de la colección del usuario (mock por ahora)
final collectionProvider = Provider<List<CollectionFish>>((ref) {
  // TODO: Conectar con Appwrite cuando esté configurado
  // Datos de ejemplo para mostrar la UI
  return [
    CollectionFish(
      fishId: 'FISH-1234',
      species: 'Trucha Arcoíris',
      rarity: 'common',
      sizeCm: 35.2,
      timesSpotted: 3,
      firstSeen: DateTime.now().subtract(const Duration(days: 15)),
    ),
    CollectionFish(
      fishId: 'FISH-5678',
      species: 'Lucio',
      rarity: 'uncommon',
      sizeCm: 72.0,
      timesSpotted: 1,
      firstSeen: DateTime.now().subtract(const Duration(days: 7)),
    ),
    CollectionFish(
      fishId: 'FISH-9012',
      species: 'Siluro',
      rarity: 'rare',
      sizeCm: 145.5,
      timesSpotted: 1,
      firstSeen: DateTime.now().subtract(const Duration(days: 3)),
    ),
    // Peces no descubiertos (siluetas)
    CollectionFish(
      fishId: 'FISH-????',
      species: '???',
      rarity: 'common',
      sizeCm: 0,
      timesSpotted: 0,
      firstSeen: DateTime.now(),
      isDiscovered: false,
    ),
    CollectionFish(
      fishId: 'FISH-????',
      species: '???',
      rarity: 'uncommon',
      sizeCm: 0,
      timesSpotted: 0,
      firstSeen: DateTime.now(),
      isDiscovered: false,
    ),
    CollectionFish(
      fishId: 'FISH-????',
      species: '???',
      rarity: 'rare',
      sizeCm: 0,
      timesSpotted: 0,
      firstSeen: DateTime.now(),
      isDiscovered: false,
    ),
    CollectionFish(
      fishId: 'FISH-????',
      species: '???',
      rarity: 'legendary',
      sizeCm: 0,
      timesSpotted: 0,
      firstSeen: DateTime.now(),
      isDiscovered: false,
    ),
  ];
});

/// Pantalla de Colección - Pokédex de Peces
/// Grid de cartas coleccionables, peces descubiertos a color y no descubiertos como silueta
class CollectionScreen extends ConsumerWidget {
  const CollectionScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final collection = ref.watch(collectionProvider);
    final discovered = collection.where((f) => f.isDiscovered).length;
    final total = collection.length;

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
            title: const Text('MI COLECCIÓN'),
          ),

          // Filtros
          SliverToBoxAdapter(
            child: _buildFilters(),
          ),

          // Grid de peces
          SliverPadding(
            padding: const EdgeInsets.all(16),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                childAspectRatio: 0.75,
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
                    '$discovered especies descubiertas',
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

  Widget _buildFilters() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          _buildFilterChip('Todos', true),
          _buildFilterChip('Comunes', false),
          _buildFilterChip('Poco comunes', false),
          _buildFilterChip('Raros', false),
          _buildFilterChip('Legendarios', false),
        ],
      ),
    );
  }

  Widget _buildFilterChip(String label, bool isSelected) {
    return Container(
      margin: const EdgeInsets.only(right: 8),
      child: FilterChip(
        label: Text(label),
        selected: isSelected,
        onSelected: (_) {},
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
      return _buildUndiscoveredCard(fish);
    }
    return _buildDiscoveredCard(context, fish);
  }

  Widget _buildDiscoveredCard(BuildContext context, CollectionFish fish) {
    return GestureDetector(
      onTap: () => _showFishDetail(context, fish),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
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
                          '${fish.timesSpotted}x',
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

  Widget _buildUndiscoveredCard(CollectionFish fish) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: AppTheme.darkSurface.withOpacity(0.5),
        border: Border.all(color: Colors.white.withOpacity(0.05)),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Silueta del pez
          Icon(
            Icons.help_outline,
            size: 48,
            color: Colors.white.withOpacity(0.1),
          ),
          const SizedBox(height: 8),
          Text(
            '???',
            style: TextStyle(
              color: Colors.white.withOpacity(0.2),
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            'No descubierto',
            style: TextStyle(
              color: Colors.white.withOpacity(0.1),
              fontSize: 11,
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
                      _buildStat('Tamaño', '${fish.sizeCm} cm'),
                      _buildStat('Avistamientos', '${fish.timesSpotted}'),
                      _buildStat('Rareza', fish.rarity.toUpperCase()),
                    ],
                  ),
                  const SizedBox(height: 24),
                  
                  // Timeline de avistamientos
                  const Text(
                    'HISTORIAL DE AVISTAMIENTOS',
                    style: TextStyle(
                      color: Colors.white54,
                      fontSize: 12,
                      letterSpacing: 1,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  
                  // Avistamiento de ejemplo
                  _buildSightingEntry(
                    'Primer avistamiento',
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
