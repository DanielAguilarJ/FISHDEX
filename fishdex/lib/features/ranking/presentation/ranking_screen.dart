import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';
import '../data/ranking_repository.dart';
import '../providers/ranking_providers.dart';

/// Pantalla de Ranking — muestra leaderboards reales de Appwrite
/// con tabs XP/Especies/Pez Mayor y filtro por período.
class RankingScreen extends ConsumerStatefulWidget {
  const RankingScreen({super.key});

  @override
  ConsumerState<RankingScreen> createState() => _RankingScreenState();
}

class _RankingScreenState extends ConsumerState<RankingScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  String _period = 'all_time';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _tabController.addListener(() {
      if (!_tabController.indexIsChanging) {
        setState(() {}); // Reconstruir para actualizar tarjeta "Tu posición"
      }
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  /// Tipo de ranking según tab activo
  String get _currentType {
    switch (_tabController.index) {
      case 0:
        return 'xp';
      case 1:
        return 'species';
      case 2:
        return 'biggest';
      default:
        return 'xp';
    }
  }

  /// Fuerza recarga de todos los providers de ranking
  Future<void> _refresh() async {
    ref.invalidate(currentUserRankProvider);
    ref.invalidate(
      rankingListProvider(RankingParams(type: 'xp', period: _period)),
    );
    ref.invalidate(
      rankingListProvider(RankingParams(type: 'species', period: _period)),
    );
    ref.invalidate(
      rankingListProvider(RankingParams(type: 'biggest', period: _period)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: RefreshIndicator(
        onRefresh: _refresh,
        color: AppTheme.accentBlue,
        child: CustomScrollView(
          slivers: [
            // Header
            SliverToBoxAdapter(child: _buildHeader()),
            // Period selector
            SliverToBoxAdapter(child: _buildPeriodSelector()),
            // Tab bar
            SliverToBoxAdapter(child: _buildTabBar()),
            // Contenido del tab
            SliverFillRemaining(child: _buildTabContent()),
          ],
        ),
      ),
    );
  }

  // ===========================================================================
  // HEADER CON POSICIÓN DEL USUARIO
  // ===========================================================================

  Widget _buildHeader() {
    return Container(
      padding: EdgeInsets.only(
        top: MediaQuery.of(context).padding.top + 16,
        left: 16,
        right: 16,
        bottom: 16,
      ),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFF1A1A3E), AppTheme.darkBackground],
        ),
      ),
      child: Column(
        children: [
          // Título
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.emoji_events, color: AppTheme.gold, size: 28),
              const SizedBox(width: 10),
              Text(
                context.l10n.rankingTitle,
                style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                      letterSpacing: 3,
                    ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          // Tarjeta de posición del usuario
          _buildUserPositionCard(),
        ],
      ),
    );
  }

  Widget _buildUserPositionCard() {
    final rankAsync = ref.watch(currentUserRankProvider);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.accentBlue.withOpacity(0.3)),
      ),
      child: rankAsync.when(
        loading: () => _buildPositionShimmer(),
        error: (_, __) => Text(
          context.l10n.rankingLoginToSee,
          style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 14),
          textAlign: TextAlign.center,
        ),
        data: (position) {
          if (position == null) {
            return Text(
              context.l10n.rankingLoginToSee,
              style: TextStyle(
                  color: Colors.white.withOpacity(0.4), fontSize: 14),
              textAlign: TextAlign.center,
            );
          }
          return _buildPositionData(position);
        },
      ),
    );
  }

  Widget _buildPositionData(UserRankPosition position) {
    // Seleccionar datos según tab activo
    int pos;
    String valueText;
    switch (_currentType) {
      case 'xp':
        pos = position.xpPosition;
        valueText = context.l10n.rankingValueXp(position.totalXp);
        break;
      case 'species':
        pos = position.speciesPosition;
        valueText = context.l10n.rankingValueSpecies(position.uniqueSpecies);
        break;
      case 'biggest':
        pos = position.biggestPosition;
        valueText = context.l10n.rankingValueBiggest(
            position.biggestFishCm.toStringAsFixed(1));
        break;
      default:
        pos = -1;
        valueText = '--';
    }

    final posText = pos > 0 ? '#$pos' : '--';

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(Icons.person, color: AppTheme.accentBlue, size: 20),
        const SizedBox(width: 8),
        Text(
          context.l10n.rankingYourPosition,
          style: const TextStyle(color: Colors.white70, fontSize: 14),
        ),
        const SizedBox(width: 12),
        Text(
          posText,
          style: const TextStyle(
            color: AppTheme.accentBlue,
            fontSize: 22,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(width: 16),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: AppTheme.gold.withOpacity(0.15),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            valueText,
            style: const TextStyle(
              color: AppTheme.gold,
              fontSize: 13,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPositionShimmer() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          width: 80,
          height: 14,
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.1),
            borderRadius: BorderRadius.circular(4),
          ),
        ),
        const SizedBox(width: 16),
        Container(
          width: 50,
          height: 20,
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.1),
            borderRadius: BorderRadius.circular(4),
          ),
        ),
      ],
    );
  }

  // ===========================================================================
  // SELECTOR DE PERÍODO
  // ===========================================================================

  Widget _buildPeriodSelector() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _buildPeriodChip(context.l10n.rankingPeriodGlobal, 'all_time'),
          const SizedBox(width: 8),
          _buildPeriodChip(context.l10n.rankingPeriodWeekly, 'weekly'),
          const SizedBox(width: 8),
          _buildPeriodChip(context.l10n.rankingPeriodMonthly, 'monthly'),
        ],
      ),
    );
  }

  Widget _buildPeriodChip(String label, String value) {
    final isActive = _period == value;
    return GestureDetector(
      onTap: () => setState(() => _period = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isActive ? AppTheme.accentBlue : AppTheme.darkSurface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isActive
                ? AppTheme.accentBlue
                : Colors.white.withOpacity(0.15),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isActive ? Colors.white : Colors.white60,
            fontSize: 13,
            fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }

  // ===========================================================================
  // TAB BAR
  // ===========================================================================

  Widget _buildTabBar() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      child: TabBar(
        controller: _tabController,
        indicatorColor: AppTheme.accentBlue,
        indicatorWeight: 3,
        labelColor: Colors.white,
        unselectedLabelColor: Colors.white54,
        labelStyle: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.bold,
          letterSpacing: 0.5,
        ),
        tabs: [
          Tab(text: context.l10n.rankingTabXp),
          Tab(text: context.l10n.rankingTabSpecies),
          Tab(text: context.l10n.rankingTabBiggest),
        ],
      ),
    );
  }

  // ===========================================================================
  // CONTENIDO DE TABS
  // ===========================================================================

  Widget _buildTabContent() {
    return TabBarView(
      controller: _tabController,
      children: [
        _buildTab('xp'),
        _buildTab('species'),
        _buildTab('biggest'),
      ],
    );
  }

  Widget _buildTab(String type) {
    final params = RankingParams(type: type, period: _period);
    final rankingAsync = ref.watch(rankingListProvider(params));

    return rankingAsync.when(
      loading: () => _buildLoadingList(),
      error: (_, __) => _buildErrorState(),
      data: (rankers) {
        if (rankers.isEmpty) return _buildEmptyState();
        return ListView.builder(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          itemCount: rankers.length,
          itemBuilder: (context, index) =>
              _buildRankerTile(rankers[index], type),
        );
      },
    );
  }

  // ===========================================================================
  // ESTADOS VACÍO / ERROR / CARGANDO
  // ===========================================================================

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.emoji_events_outlined,
            color: Colors.white.withOpacity(0.2),
            size: 64,
          ),
          const SizedBox(height: 16),
          Text(
            context.l10n.rankingEmpty,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            context.l10n.rankingEmptySubtitle,
            style: TextStyle(
              color: Colors.white.withOpacity(0.3),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.wifi_off,
            color: Colors.white.withOpacity(0.3),
            size: 48,
          ),
          const SizedBox(height: 12),
          Text(
            context.l10n.rankingNoConnection,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _refresh,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.accentBlue,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            child: Text(context.l10n.retry),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingList() {
    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      itemCount: 10,
      itemBuilder: (_, __) => const _ShimmerTile(),
    );
  }

  // ===========================================================================
  // TILE DE RANKER
  // ===========================================================================

  Widget _buildRankerTile(RankerData ranker, String type) {
    // Colores según posición
    Color? borderColor;
    Color? bgTint;
    if (ranker.position == 1) {
      borderColor = const Color(0xFFFFD700).withOpacity(0.6);
      bgTint = const Color(0xFFFFD700).withOpacity(0.05);
    } else if (ranker.position == 2) {
      borderColor = Colors.grey.shade400.withOpacity(0.5);
      bgTint = Colors.grey.shade400.withOpacity(0.03);
    } else if (ranker.position == 3) {
      borderColor = const Color(0xFFCD7F32).withOpacity(0.5);
      bgTint = const Color(0xFFCD7F32).withOpacity(0.04);
    }

    // Si es el usuario actual, sobreescribir border
    final isMe = ranker.isCurrentUser;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: bgTint ?? AppTheme.darkSurface.withOpacity(0.6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isMe
              ? AppTheme.accentBlue.withOpacity(0.8)
              : (borderColor ?? Colors.transparent),
          width: isMe ? 1.5 : 1.0,
        ),
      ),
      child: Row(
        children: [
          // Posición / trofeo
          SizedBox(
            width: 36,
            child: _buildPositionBadge(ranker.position),
          ),
          const SizedBox(width: 10),

          // Avatar
          _buildAvatar(ranker),
          const SizedBox(width: 12),

          // Nombre + nivel
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        ranker.name,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (isMe) ...[
                      const SizedBox(width: 6),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: AppTheme.accentBlue,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          context.l10n.rankingYouBadge,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 9,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  context.l10n.rankingLevel(ranker.level),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.4),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),

          // Valor
          Text(
            _formatValue(ranker.value, type),
            style: TextStyle(
              color: ranker.position <= 3 ? AppTheme.gold : Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPositionBadge(int position) {
    if (position <= 3) {
      final colors = [
        const Color(0xFFFFD700), // Oro
        Colors.grey.shade400, // Plata
        const Color(0xFFCD7F32), // Bronce
      ];
      return Icon(
        Icons.emoji_events,
        color: colors[position - 1],
        size: 26,
      );
    }
    return Text(
      '#$position',
      style: TextStyle(
        color: Colors.white.withOpacity(0.5),
        fontSize: 13,
        fontWeight: FontWeight.bold,
      ),
      textAlign: TextAlign.center,
    );
  }

  Widget _buildAvatar(RankerData ranker) {
    const double size = 44;

    if (ranker.avatarUrl != null && ranker.avatarUrl!.isNotEmpty) {
      return ClipOval(
        child: CachedNetworkImage(
          imageUrl: ranker.avatarUrl!,
          width: size,
          height: size,
          fit: BoxFit.cover,
          placeholder: (_, __) => _buildAvatarPlaceholder(ranker.name, size),
          errorWidget: (_, __, ___) =>
              _buildAvatarPlaceholder(ranker.name, size),
        ),
      );
    }
    return _buildAvatarPlaceholder(ranker.name, size);
  }

  Widget _buildAvatarPlaceholder(String name, double size) {
    return Container(
      width: size,
      height: size,
      decoration: const BoxDecoration(
        shape: BoxShape.circle,
        gradient: AppTheme.primaryGradient,
      ),
      child: Center(
        child: Text(
          name.isNotEmpty ? name[0].toUpperCase() : 'P',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }

  String _formatValue(double value, String type) {
    switch (type) {
      case 'xp':
        return context.l10n.rankingValueXp(value.toInt());
      case 'species':
        return context.l10n.rankingValueSpecies(value.toInt());
      case 'biggest':
        return context.l10n.rankingValueBiggest(value.toStringAsFixed(1));
      default:
        return value.toString();
    }
  }
}

// =============================================================================
// SHIMMER TILE — Animación de carga con AnimationController (battery-efficient)
// =============================================================================

class _ShimmerTile extends StatefulWidget {
  const _ShimmerTile();

  @override
  State<_ShimmerTile> createState() => _ShimmerTileState();
}

class _ShimmerTileState extends State<_ShimmerTile>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Opacity(
          opacity: 0.3 + (0.3 * _controller.value),
          child: Container(
            height: 64,
            margin: const EdgeInsets.only(bottom: 8),
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        );
      },
    );
  }
}
