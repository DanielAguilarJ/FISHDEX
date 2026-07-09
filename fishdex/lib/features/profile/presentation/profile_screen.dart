import 'dart:io';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../app.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/enums/user_role.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/services/gamification_service.dart';
import '../../../data/services/role_guard_service.dart';
import '../../../widgets/pressable_scale.dart';
import '../../auth/providers/auth_provider.dart';
import '../providers/profile_setup_provider.dart';

// =============================================================================
// PROVIDER DE STATS REALES DEL USUARIO
// =============================================================================

/// Carga las estadísticas reales del usuario desde Appwrite
final userStatsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final isDemoMode = prefs.getBool('is_demo_mode') ?? false;
    if (isDemoMode) return _demoStats();

    final account = ref.read(appwriteAccountProvider);
    final user = await account.get();
    final databases = ref.read(appwriteDatabasesProvider);

    final doc = await databases.getDocument(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.usersCollection,
      documentId: user.$id,
    );

    return doc.data;
  } catch (e) {
    return _demoStats();
  }
});

Map<String, dynamic> _demoStats() => {
      'total_xp': 0,
      'level': 1,
      'total_sightings': 0,
      'unique_species': 0,
      'rare_fish_count': 0,
      'legendary_fish_count': 0,
      'role': 'fisherman',
      'approval_status': 'approved',
    };

// =============================================================================
// PANTALLA DE PERFIL
// =============================================================================

/// Pantalla de Perfil completa con datos reales, rol, stats y accesos rápidos
class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final GamificationService _gamification = GamificationService();

  void _showLanguageDialog(BuildContext context) {
    final currentLocale = ref.read(localeProvider);

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.darkSurfaceVariant,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppTheme.radiusLg)),
        title: const Row(
          children: [
            Icon(Icons.language, color: Colors.white70),
            SizedBox(width: 10),
            Text('Idioma / Language', style: TextStyle(color: Colors.white)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildLanguageTile(ctx, 'Español', '🇪🇸', const Locale('es'), currentLocale),
            _buildLanguageTile(ctx, 'English', '🇬🇧', const Locale('en'), currentLocale),
            _buildLanguageTile(ctx, 'Čeština', '🇨🇿', const Locale('cs'), currentLocale),
          ],
        ),
      ),
    );
  }

  Widget _buildLanguageTile(
    BuildContext ctx,
    String name,
    String flag,
    Locale locale,
    Locale current,
  ) {
    final isSelected = locale.languageCode == current.languageCode;
    return ListTile(
      leading: Text(flag, style: const TextStyle(fontSize: 24)),
      title: Text(
        name,
        style: TextStyle(
          color: isSelected ? AppTheme.accentBlue : Colors.white,
          fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
        ),
      ),
      trailing: isSelected
          ? const Icon(Icons.check_circle, color: AppTheme.accentBlue)
          : null,
      onTap: () {
        ref.read(localeProvider.notifier).state = locale;
        Navigator.pop(ctx);
      },
    );
  }

  Future<void> _handleLogout() async {
    final l10n = context.l10n;
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.darkSurfaceVariant,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppTheme.radiusLg)),
        title: Text(l10n.profileLogoutTitle,
            style: const TextStyle(color: Colors.white)),
        content: Text(
          l10n.profileLogoutConfirm,
          style: const TextStyle(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(l10n.cancel,
                style: const TextStyle(color: Colors.white54)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(l10n.profileLogout,
                style: TextStyle(color: Colors.red.shade400)),
          ),
        ],
      ),
    );

    if (confirm != true) return;

    try {
      final authRepo = ref.read(authRepositoryProvider);
      await authRepo.logout();
    } catch (_) {}

    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('has_active_session', false);
    await prefs.setBool('is_demo_mode', false);
    await prefs.setBool('profile_setup_completed', false);
    await prefs.remove('cached_user_role');
    await prefs.remove('cached_approval_status');

    ref.invalidate(authStateProvider);
    ref.invalidate(userProfileProvider);
    ref.invalidate(userStatsProvider);

    if (mounted) context.go('/login');
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authStateProvider);
    final profileAsync = ref.watch(userProfileProvider);
    final statsAsync = ref.watch(userStatsProvider);
    final roleAsync = ref.watch(currentUserRoleProvider);
    final profile = profileAsync.valueOrNull;
    final stats = statsAsync.valueOrNull ?? _demoStats();
    final roleModel = roleAsync.valueOrNull;

    // Datos de display
    final String displayName = profile?.username.isNotEmpty == true
        ? profile!.username
        : (authState.valueOrNull?.name ?? 'Pescador');
    final String displayEmail = authState.valueOrNull?.email ?? '';
    final String? avatarPath = profile?.avatarPath;
    final String city = profile?.city ?? '';

    // Stats
    final int totalXp = (stats['total_xp'] as num?)?.toInt() ?? 0;
    final int level = (stats['level'] as num?)?.toInt() ?? 1;
    final int totalSightings =
        (stats['total_sightings'] as num?)?.toInt() ?? 0;
    final int uniqueSpecies =
        (stats['unique_species'] as num?)?.toInt() ?? 0;
    final int rareFish = (stats['rare_fish_count'] as num?)?.toInt() ?? 0;
    final int legendaryFish =
        (stats['legendary_fish_count'] as num?)?.toInt() ?? 0;

    // XP progress
    final int xpForNext = _gamification.xpForNextLevel(level);
    final int xpInLevel = totalXp - _xpAccumulatedToLevel(level);
    final double xpProgress =
        xpForNext > 0 ? (xpInLevel / xpForNext).clamp(0.0, 1.0) : 0.0;

    // Rol
    final UserRole role = roleModel?.role ?? UserRole.fisherman;

    // Nivel título
    final String levelTitle = _getLevelTitle(level);

    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: CustomScrollView(
        slivers: [
          // HERO HEADER
          SliverAppBar(
            expandedHeight: 280,
            pinned: true,
            backgroundColor: AppTheme.darkBackground,
            automaticallyImplyLeading: false,
            actions: [
              // Botón selector de idioma
              IconButton(
                icon: const Icon(Icons.language, color: Colors.white70, size: 22),
                onPressed: () => _showLanguageDialog(context),
                tooltip: 'Idioma / Language',
              ),
              // Botón editar perfil
              IconButton(
                icon: const Icon(Icons.edit, color: Colors.white70, size: 22),
                onPressed: () => context.go('/profile-setup'),
                tooltip: context.l10n.profileEditButton,
              ),
              // Botón admin (solo visible para admins)
              if (role == UserRole.admin)
                IconButton(
                  icon: const Icon(Icons.admin_panel_settings,
                      color: Colors.orange, size: 22),
                  onPressed: () => context.go('/admin'),
                  tooltip: context.l10n.profileAdminPanel,
                ),
              // Botón logout
              IconButton(
                icon: const Icon(Icons.logout, color: Colors.white54, size: 22),
                onPressed: _handleLogout,
                tooltip: context.l10n.profileLogout,
              ),
            ],
            flexibleSpace: FlexibleSpaceBar(
              background: _buildHeroSection(
                name: displayName,
                email: displayEmail,
                city: city,
                avatarPath: avatarPath,
                level: level,
                role: role,
              ),
            ),
          ),

          // BARRA DE NIVEL/XP
          SliverToBoxAdapter(
            child: _buildXpBar(level, levelTitle, totalXp, xpForNext, xpProgress),
          ),

          // STATS GRID
          SliverToBoxAdapter(
            child: _buildStatsGrid(
              totalSightings: totalSightings,
              uniqueSpecies: uniqueSpecies,
              rareFish: rareFish,
              legendaryFish: legendaryFish,
              totalXp: totalXp,
            ),
          ),

          // ACCESOS RÁPIDOS
          SliverToBoxAdapter(child: _buildQuickActions(role)),

          // ACTIVIDAD RECIENTE
          SliverToBoxAdapter(child: _buildRecentActivity(stats)),

          // Espacio final
          const SliverToBoxAdapter(child: SizedBox(height: 100)),
        ],
      ),
    );
  }

  // ===========================================================================
  // HERO SECTION
  // ===========================================================================

  Widget _buildHeroSection({
    required String name,
    required String email,
    required String city,
    required String? avatarPath,
    required int level,
    required UserRole role,
  }) {
    return Stack(
      fit: StackFit.expand,
      children: [
        // Fondo gradiente
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: [0.0, 0.4, 0.7, 1.0],
              colors: [
                Color(0xFF1A3A5C),
                AppTheme.darkSurfaceVariant,
                AppTheme.darkSurfaceDeep,
                AppTheme.darkBackground,
              ],
            ),
          ),
        ),

        // Contenido centrado
        SafeArea(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const SizedBox(height: 40),

              // Avatar
              _buildAvatar(name, avatarPath, level),
              const SizedBox(height: 16),

              // Nombre
              Text(
                name,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),

              // Email y ciudad
              if (email.isNotEmpty || city.isNotEmpty)
                Text(
                  [email, city].where((s) => s.isNotEmpty).join(' · '),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                    fontSize: 13,
                  ),
                ),
              const SizedBox(height: 10),

              // Badge de rol
              _buildRoleBadge(role),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAvatar(String name, String? avatarPath, int level) {
    final hasAvatar = avatarPath != null && File(avatarPath).existsSync();

    return Stack(
      alignment: Alignment.bottomRight,
      children: [
        Container(
          width: 100,
          height: 100,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: AppTheme.accentBlue, width: 3),
            boxShadow: [
              BoxShadow(
                color: AppTheme.accentBlue.withOpacity(0.3),
                blurRadius: 20,
                spreadRadius: 2,
              ),
            ],
            gradient: hasAvatar ? null : AppTheme.primaryGradient,
            image: hasAvatar
                ? DecorationImage(
                    image: FileImage(File(avatarPath)),
                    fit: BoxFit.cover,
                  )
                : null,
          ),
          child: hasAvatar
              ? null
              : Center(
                  child: Text(
                    name.isNotEmpty ? name[0].toUpperCase() : 'P',
                    style: const TextStyle(
                      fontSize: 40,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                ),
        ),
        // Badge de nivel
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            gradient: AppTheme.goldGradient,
            borderRadius: BorderRadius.circular(10),
            boxShadow: [
              BoxShadow(
                color: AppTheme.gold.withOpacity(0.4),
                blurRadius: 6,
              ),
            ],
          ),
          child: Text(
            context.l10n.levelTitle(level),
            style: const TextStyle(
              color: Colors.white,
              fontSize: 11,
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildRoleBadge(UserRole role) {
    Color badgeColor;
    IconData badgeIcon;
    String roleName;

    switch (role) {
      case UserRole.admin:
        badgeColor = Colors.orange;
        badgeIcon = Icons.admin_panel_settings;
        roleName = context.l10n.roleAdmin;
        break;
      case UserRole.researcher:
        badgeColor = Colors.purple;
        badgeIcon = Icons.biotech;
        roleName = context.l10n.roleResearcher;
        break;
      case UserRole.fisherman:
      default:
        badgeColor = AppTheme.teal;
        badgeIcon = Icons.phishing;
        roleName = context.l10n.roleFisherman;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(
        color: badgeColor.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: badgeColor.withOpacity(0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(badgeIcon, color: badgeColor, size: 14),
          const SizedBox(width: 6),
          Text(
            roleName,
            style: TextStyle(
              color: badgeColor,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // BARRA XP
  // ===========================================================================

  Widget _buildXpBar(
      int level, String title, int totalXp, int xpForNext, double progress) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurfaceVariant,
        borderRadius: BorderRadius.circular(AppTheme.radiusLg),
        border: Border.all(color: AppTheme.gold.withOpacity(AppTheme.opacityBorder)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  gradient: AppTheme.goldGradient,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  context.l10n.levelTitle(level),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
              const Spacer(),
              Text(
                '$totalXp / ${_xpAccumulatedToLevel(level) + xpForNext} XP',
                style: const TextStyle(
                  color: AppTheme.gold,
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 8,
              backgroundColor: AppTheme.darkSurfaceElevated,
              valueColor: const AlwaysStoppedAnimation<Color>(AppTheme.gold),
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // STATS GRID
  // ===========================================================================

  Widget _buildStatsGrid({
    required int totalSightings,
    required int uniqueSpecies,
    required int rareFish,
    required int legendaryFish,
    required int totalXp,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.profileStatsTitle,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 12,
              letterSpacing: 2,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _buildStatCard(
                  context.l10n.statsCaptures,
                  totalSightings.toString(),
                  Icons.phishing,
                  color: AppTheme.accentBlue),
              const SizedBox(width: 10),
              _buildStatCard(
                  context.l10n.statsSpecies,
                  uniqueSpecies.toString(),
                  Icons.pets,
                  color: Colors.green),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _buildStatCard(
                  context.l10n.statsRare,
                  rareFish.toString(),
                  Icons.star,
                  color: Colors.purple),
              const SizedBox(width: 10),
              _buildStatCard(
                  context.l10n.statsLegendary,
                  legendaryFish.toString(),
                  Icons.auto_awesome,
                  color: AppTheme.gold),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStatCard(String label, String value, IconData icon,
      {Color color = Colors.white}) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.15)),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: color.withOpacity(0.15),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, color: color, size: 18),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  value,
                  style: TextStyle(
                    color: color,
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Text(
                  label,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ===========================================================================
  // ACCESOS RÁPIDOS
  // ===========================================================================

  Widget _buildQuickActions(UserRole role) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.profileQuickAccess,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 12,
              letterSpacing: 2,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _buildActionButton(
                icon: Icons.collections_bookmark,
                label: context.l10n.navCollection,
                color: const Color(0xFF11998E),
                onTap: () => context.go('/collection'),
              ),
              const SizedBox(width: 10),
              _buildActionButton(
                icon: Icons.emoji_events,
                label: context.l10n.navRanking,
                color: const Color(0xFFF7971E),
                onTap: () => context.go('/ranking'),
              ),
              const SizedBox(width: 10),
              _buildActionButton(
                icon: Icons.map,
                label: context.l10n.navMap,
                color: const Color(0xFF2193B0),
                onTap: () => context.go('/map'),
              ),
              const SizedBox(width: 10),
              _buildActionButton(
                icon: Icons.camera_alt,
                label: context.l10n.navIdentify,
                color: Colors.green,
                onTap: () => context.go('/camera'),
              ),
            ],
          ),
          // Admin button row
          if (role == UserRole.admin) ...[
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () => context.go('/admin'),
                icon: const Icon(Icons.admin_panel_settings, size: 18),
                label: Text(context.l10n.profileAdminPanel),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.orange,
                  side: BorderSide(color: Colors.orange.withOpacity(0.4)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required String label,
    required Color color,
    required VoidCallback onTap,
  }) {
    return Expanded(
      child: PressableScale(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(
            color: color.withOpacity(0.1),
            borderRadius: BorderRadius.circular(AppTheme.radiusMd),
            border: Border.all(color: color.withOpacity(AppTheme.opacityBorder)),
          ),
          child: Column(
            children: [
              Icon(icon, color: color, size: 24),
              const SizedBox(height: 6),
              Text(
                label,
                style: TextStyle(
                  color: color,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ===========================================================================
  // ACTIVIDAD RECIENTE
  // ===========================================================================

  Widget _buildRecentActivity(Map<String, dynamic> stats) {
    final totalXp = (stats['total_xp'] as num?)?.toInt() ?? 0;
    final totalSightings = (stats['total_sightings'] as num?)?.toInt() ?? 0;
    final uniqueSpecies = (stats['unique_species'] as num?)?.toInt() ?? 0;
    final lastActivity = stats['last_activity'] as String?;
    String lastActiveText = context.l10n.profileNoActivity;
    if (lastActivity != null) {
      try {
        final date = DateTime.parse(lastActivity);
        final diff = DateTime.now().difference(date);
        if (diff.inMinutes < 60) {
          lastActiveText = context.l10n.profileMinutesAgo(diff.inMinutes);
        } else if (diff.inHours < 24) {
          lastActiveText = context.l10n.profileHoursAgo(diff.inHours);
        } else {
          lastActiveText = context.l10n.profileDaysAgo(diff.inDays);
        }
      } catch (_) {}
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.profileSummary,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 12,
              letterSpacing: 2,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          _buildActivityRow(Icons.local_fire_department,
              context.l10n.profileLastActivity, lastActiveText, Colors.orange),
          _buildActivityRow(Icons.phishing, context.l10n.profileTotalCaptures,
              '$totalSightings', AppTheme.accentBlue),
          _buildActivityRow(Icons.pets, context.l10n.profileUniqueSpecies,
              '$uniqueSpecies', Colors.green),
          _buildActivityRow(
              Icons.star, context.l10n.profileTotalXp, '$totalXp', AppTheme.gold),
        ],
      ),
    );
  }

  Widget _buildActivityRow(
      IconData icon, String label, String value, Color color) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: AppTheme.darkSurfaceDeep,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 12),
          Text(
            label,
            style: const TextStyle(color: Colors.white70, fontSize: 14),
          ),
          const Spacer(),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 14,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // HELPERS
  // ===========================================================================

  int _xpAccumulatedToLevel(int level) {
    int total = 0;
    for (int i = 2; i <= level; i++) {
      total += (AppConstants.xpBaseForLevel * math.pow(i, AppConstants.xpLevelFactor))
          .toInt();
    }
    return total;
  }

  String _getLevelTitle(int level) {
    if (level >= 50) return context.l10n.levelLegendaryMaster;
    if (level >= 40) return context.l10n.levelGrandMaster;
    if (level >= 30) return context.l10n.levelMaster;
    if (level >= 20) return context.l10n.levelExpert;
    if (level >= 15) return context.l10n.levelVeteran;
    if (level >= 10) return context.l10n.levelAdvanced;
    if (level >= 5) return context.l10n.levelIntermediate;
    if (level >= 2) return context.l10n.levelApprentice;
    return context.l10n.levelBeginner;
  }
}
