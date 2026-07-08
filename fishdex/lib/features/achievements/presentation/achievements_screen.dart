import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';

/// Datos de un logro
class AchievementData {
  final String id;
  final String name;
  final String description;
  final IconData icon;
  final int xpReward;
  final String category;
  final String badgeRarity; // bronze, silver, gold, platinum
  final int progress;
  final int target;
  final bool isUnlocked;

  const AchievementData({
    required this.id,
    required this.name,
    required this.description,
    required this.icon,
    required this.xpReward,
    required this.category,
    required this.badgeRarity,
    required this.progress,
    required this.target,
    required this.isUnlocked,
  });
}

/// Provider mock de logros
final achievementsProvider = Provider<List<AchievementData>>((ref) {
  return [
    const AchievementData(
      id: '1', name: 'Primer Avistamiento', description: 'Identifica tu primer pez',
      icon: Icons.phishing, xpReward: 50, category: 'discovery',
      badgeRarity: 'bronze', progress: 1, target: 1, isUnlocked: true,
    ),
    const AchievementData(
      id: '2', name: 'Coleccionista Novato', description: 'Identifica 10 peces diferentes',
      icon: Icons.collections_bookmark, xpReward: 100, category: 'collection',
      badgeRarity: 'silver', progress: 3, target: 10, isUnlocked: false,
    ),
    const AchievementData(
      id: '3', name: 'Maestro del Río', description: 'Identifica 50 peces diferentes',
      icon: Icons.military_tech, xpReward: 500, category: 'collection',
      badgeRarity: 'gold', progress: 3, target: 50, isUnlocked: false,
    ),
    const AchievementData(
      id: '4', name: 'Pez Trofeo', description: 'Encuentra un pez de más de 100cm',
      icon: Icons.emoji_events, xpReward: 200, category: 'discovery',
      badgeRarity: 'gold', progress: 0, target: 1, isUnlocked: false,
    ),
    const AchievementData(
      id: '5', name: 'Reencuentro', description: 'Identifica el mismo pez en diferentes días',
      icon: Icons.refresh, xpReward: 75, category: 'discovery',
      badgeRarity: 'silver', progress: 0, target: 1, isUnlocked: false,
    ),
    const AchievementData(
      id: '6', name: 'Explorador', description: 'Registra avistamientos en 5 ubicaciones',
      icon: Icons.explore, xpReward: 150, category: 'exploration',
      badgeRarity: 'silver', progress: 1, target: 5, isUnlocked: false,
    ),
    const AchievementData(
      id: '7', name: 'Científico Ciudadano', description: 'Contribuye con 100 avistamientos',
      icon: Icons.science, xpReward: 1000, category: 'social',
      badgeRarity: 'platinum', progress: 3, target: 100, isUnlocked: false,
    ),
    const AchievementData(
      id: '8', name: 'Madrugador', description: 'Identifica un pez antes de las 6:00 AM',
      icon: Icons.wb_twilight, xpReward: 50, category: 'exploration',
      badgeRarity: 'bronze', progress: 0, target: 1, isUnlocked: false,
    ),
    const AchievementData(
      id: '9', name: 'Cazador Legendario', description: 'Encuentra un pez legendario',
      icon: Icons.auto_awesome, xpReward: 300, category: 'discovery',
      badgeRarity: 'platinum', progress: 0, target: 1, isUnlocked: false,
    ),
    const AchievementData(
      id: '10', name: 'Racha de 7 Días', description: 'Usa la app 7 días consecutivos',
      icon: Icons.local_fire_department, xpReward: 100, category: 'social',
      badgeRarity: 'silver', progress: 1, target: 7, isUnlocked: false,
    ),
  ];
});

/// Pantalla de Logros - Grid de insignias con progreso
class AchievementsScreen extends ConsumerWidget {
  const AchievementsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final achievements = ref.watch(achievementsProvider);
    final unlocked = achievements.where((a) => a.isUnlocked).length;

    return Scaffold(
      appBar: AppBar(
        title: Text(context.l10n.achievementsCategory),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color: AppTheme.gold.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  '$unlocked/${achievements.length}',
                  style: const TextStyle(
                    color: AppTheme.gold,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
      body: GridView.builder(
        padding: const EdgeInsets.all(16),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          childAspectRatio: 0.85,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
        ),
        itemCount: achievements.length,
        itemBuilder: (context, index) {
          return _buildAchievementCard(context, achievements[index]);
        },
      ),
    );
  }

  Widget _buildAchievementCard(BuildContext context, AchievementData achievement) {
    final badgeColor = _getBadgeColor(achievement.badgeRarity);
    final progressPercent = achievement.target > 0
        ? achievement.progress / achievement.target
        : 0.0;

    return Container(
      decoration: BoxDecoration(
        color: achievement.isUnlocked
            ? AppTheme.darkSurface
            : AppTheme.darkSurface.withOpacity(0.4),
        borderRadius: BorderRadius.circular(16),
        border: achievement.isUnlocked
            ? Border.all(color: badgeColor.withOpacity(0.5), width: 1.5)
            : null,
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Icono de la insignia
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: achievement.isUnlocked
                    ? badgeColor.withOpacity(0.2)
                    : Colors.white.withOpacity(0.05),
                border: Border.all(
                  color: achievement.isUnlocked
                      ? badgeColor
                      : Colors.white.withOpacity(0.1),
                  width: 2,
                ),
              ),
              child: Icon(
                achievement.icon,
                color: achievement.isUnlocked
                    ? badgeColor
                    : Colors.white.withOpacity(0.2),
                size: 28,
              ),
            ),
            const SizedBox(height: 10),
            
            // Nombre
            Text(
              achievement.name,
              style: TextStyle(
                color: achievement.isUnlocked
                    ? Colors.white
                    : Colors.white.withOpacity(0.4),
                fontSize: 13,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 4),
            
            // Descripción
            Text(
              achievement.description,
              style: TextStyle(
                color: Colors.white.withOpacity(0.4),
                fontSize: 10,
              ),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 8),
            
            // Barra de progreso
            if (!achievement.isUnlocked) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: progressPercent,
                  minHeight: 4,
                  backgroundColor: Colors.white.withOpacity(0.1),
                  valueColor: AlwaysStoppedAnimation<Color>(badgeColor),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                context.l10n.achievementsProgressLabel(
                  achievement.progress,
                  achievement.target,
                ),
                style: TextStyle(
                  color: Colors.white.withOpacity(0.3),
                  fontSize: 10,
                ),
              ),
            ] else
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.star, color: AppTheme.gold, size: 12),
                  const SizedBox(width: 4),
                  Text(
                    '+${achievement.xpReward} XP',
                    style: const TextStyle(
                      color: AppTheme.gold,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }

  Color _getBadgeColor(String rarity) {
    switch (rarity) {
      case 'bronze':
        return const Color(0xFFCD7F32);
      case 'silver':
        return Colors.grey.shade300;
      case 'gold':
        return AppTheme.gold;
      case 'platinum':
        return AppTheme.legendaryPurple;
      default:
        return Colors.grey;
    }
  }
}
