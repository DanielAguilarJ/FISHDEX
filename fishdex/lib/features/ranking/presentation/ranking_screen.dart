import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';

/// Datos de un usuario en el ranking
class RankerData {
  final String userId;
  final String name;
  final int level;
  final String? avatarUrl;
  final double value;
  final int position;

  const RankerData({
    required this.userId,
    required this.name,
    required this.level,
    this.avatarUrl,
    required this.value,
    required this.position,
  });
}

/// Provider mock de rankings
final rankingProvider = Provider.family<List<RankerData>, String>((ref, type) {
  // TODO: Conectar con Appwrite Realtime
  return [
    RankerData(userId: '1', name: 'PescadorPro99', level: 12, value: 2450, position: 1),
    RankerData(userId: '2', name: 'RíoMaster', level: 10, value: 1890, position: 2),
    RankerData(userId: '3', name: 'TruchaKing', level: 8, value: 1520, position: 3),
    RankerData(userId: '4', name: 'LucioHunter', level: 7, value: 1200, position: 4),
    RankerData(userId: '5', name: 'CarpaDiver', level: 6, value: 980, position: 5),
    RankerData(userId: '6', name: 'SiluroMax', level: 5, value: 750, position: 6),
    RankerData(userId: '7', name: 'BassMaster', level: 4, value: 620, position: 7),
    RankerData(userId: '8', name: 'AngulaFan', level: 3, value: 450, position: 8),
    RankerData(userId: '9', name: 'BarboTeam', level: 3, value: 380, position: 9),
    RankerData(userId: '10', name: 'PercaLover', level: 2, value: 200, position: 10),
  ];
});

/// Pantalla de Rankings con tabs para diferentes categorías y períodos
class RankingScreen extends ConsumerStatefulWidget {
  const RankingScreen({super.key});

  @override
  ConsumerState<RankingScreen> createState() => _RankingScreenState();
}

class _RankingScreenState extends ConsumerState<RankingScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  String _selectedPeriod = 'all_time';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          // Header
          _buildHeader(context),
          
          // Period selector
          _buildPeriodSelector(),
          
          // Tab bar
          Container(
            color: AppTheme.darkSurface,
            child: TabBar(
              controller: _tabController,
              indicatorColor: AppTheme.accentBlue,
              labelColor: AppTheme.accentBlue,
              unselectedLabelColor: Colors.white38,
              tabs: const [
                Tab(text: 'XP TOTAL'),
                Tab(text: 'ESPECIES'),
                Tab(text: 'PEZ MAYOR'),
              ],
            ),
          ),
          
          // Content
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                _buildRankingList('xp'),
                _buildRankingList('species'),
                _buildRankingList('biggest'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        top: MediaQuery.of(context).padding.top + 16,
        left: 24,
        right: 24,
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
          Row(
            children: [
              Text(
                'RANKING',
                style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                      letterSpacing: 3,
                    ),
              ),
              const Spacer(),
              const Icon(Icons.emoji_events, color: AppTheme.gold, size: 28),
            ],
          ),
          const SizedBox(height: 8),
          // Tu posición actual
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: AppTheme.accentBlue.withOpacity(0.3),
              ),
            ),
            child: Row(
              children: [
                const Text(
                  'Tu posición:',
                  style: TextStyle(color: Colors.white60, fontSize: 14),
                ),
                const SizedBox(width: 8),
                const Text(
                  '#42',
                  style: TextStyle(
                    color: AppTheme.accentBlue,
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    gradient: AppTheme.goldGradient,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Text(
                    '0 XP',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
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

  Widget _buildPeriodSelector() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          _buildPeriodChip('all_time', 'Global'),
          _buildPeriodChip('weekly', 'Semanal'),
          _buildPeriodChip('monthly', 'Mensual'),
        ],
      ),
    );
  }

  Widget _buildPeriodChip(String value, String label) {
    final isSelected = _selectedPeriod == value;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _selectedPeriod = value),
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 4),
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: isSelected
                ? AppTheme.accentBlue.withOpacity(0.2)
                : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: isSelected
                  ? AppTheme.accentBlue.withOpacity(0.5)
                  : Colors.white12,
            ),
          ),
          child: Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: isSelected ? AppTheme.accentBlue : Colors.white54,
              fontSize: 13,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRankingList(String type) {
    final rankers = ref.watch(rankingProvider(type));

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: rankers.length,
      itemBuilder: (context, index) {
        final ranker = rankers[index];
        return _buildRankerTile(ranker, type);
      },
    );
  }

  Widget _buildRankerTile(RankerData ranker, String type) {
    final isTopThree = ranker.position <= 3;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isTopThree
            ? AppTheme.darkSurface
            : AppTheme.darkSurface.withOpacity(0.5),
        borderRadius: BorderRadius.circular(12),
        border: isTopThree
            ? Border.all(
                color: _getPositionColor(ranker.position).withOpacity(0.3),
              )
            : null,
      ),
      child: Row(
        children: [
          // Posición
          SizedBox(
            width: 36,
            child: isTopThree
                ? Icon(
                    Icons.emoji_events,
                    color: _getPositionColor(ranker.position),
                    size: 24,
                  )
                : Text(
                    '#${ranker.position}',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.5),
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                    ),
                    textAlign: TextAlign.center,
                  ),
          ),
          const SizedBox(width: 12),
          
          // Avatar
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: AppTheme.primaryGradient,
            ),
            child: Center(
              child: Text(
                ranker.name[0].toUpperCase(),
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          
          // Nombre y nivel
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  ranker.name,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  'Nivel ${ranker.level}',
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
              color: isTopThree ? AppTheme.gold : Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Color _getPositionColor(int position) {
    switch (position) {
      case 1:
        return AppTheme.gold;
      case 2:
        return Colors.grey.shade300;
      case 3:
        return const Color(0xFFCD7F32); // Bronce
      default:
        return Colors.white54;
    }
  }

  String _formatValue(double value, String type) {
    switch (type) {
      case 'xp':
        return '${value.toInt()} XP';
      case 'species':
        return '${value.toInt()} spp';
      case 'biggest':
        return '${value.toInt()} cm';
      default:
        return value.toString();
    }
  }
}
