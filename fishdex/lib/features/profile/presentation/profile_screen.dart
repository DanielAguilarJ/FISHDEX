import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../auth/providers/auth_provider.dart';
import '../providers/profile_setup_provider.dart';

/// Pantalla de Perfil — Diseño estilo Pokémon GO / Gaming
/// Hero header con lago, avatar, tabs ME/FRIENDS/PARTY,
/// barra de nivel, accesos rápidos circulares y Total Activity.
class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _tabController.addListener(() {
      if (_tabController.indexIsChanging) {
        if (_tabController.index != 0) {
          // FRIENDS y PARTY → mostrar "Próximamente"
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Próximamente'),
              duration: Duration(seconds: 1),
            ),
          );
          // Regresar al tab ME
          _tabController.animateTo(0);
        }
      }
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _handleLogout() async {
    try {
      final authRepo = ref.read(authRepositoryProvider);
      await authRepo.logout();
    } catch (_) {}
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('has_active_session', false);
    ref.invalidate(authStateProvider);
    if (mounted) context.go('/login');
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authStateProvider);
    final profileAsync = ref.watch(userProfileProvider);
    final profile = profileAsync.valueOrNull;

    // Datos de display
    final String displayName = profile?.username.isNotEmpty == true
        ? profile!.username
        : (authState.valueOrNull?.name ?? 'Pescador');
    final String displayEmail =
        authState.valueOrNull?.email ?? 'Modo Demo';
    final String? avatarPath = profile?.avatarPath;

    return Scaffold(
      backgroundColor: const Color(0xFF0A1020),
      body: CustomScrollView(
        slivers: [
          // ═══════════════════════════════════════════════════════════════════
          // SECCIÓN 1: HERO HEADER (SliverAppBar)
          // ═══════════════════════════════════════════════════════════════════
          SliverAppBar(
            expandedHeight: 420,
            pinned: true,
            backgroundColor: const Color(0xFF0A1020),
            automaticallyImplyLeading: false,
            flexibleSpace: FlexibleSpaceBar(
              background: _buildHeroBackground(
                displayName,
                displayEmail,
                avatarPath,
              ),
            ),
            // Tabs en la parte inferior del AppBar colapsado
            bottom: PreferredSize(
              preferredSize: const Size.fromHeight(0),
              child: Container(),
            ),
          ),

          // ═══════════════════════════════════════════════════════════════════
          // SECCIÓN 2: BARRA NIVEL/XP
          // ═══════════════════════════════════════════════════════════════════
          SliverToBoxAdapter(child: _buildLevelBar()),

          // ═══════════════════════════════════════════════════════════════════
          // SECCIÓN 3: ACCESOS RÁPIDOS (4 botones circulares)
          // ═══════════════════════════════════════════════════════════════════
          SliverToBoxAdapter(child: _buildQuickAccess()),

          // ═══════════════════════════════════════════════════════════════════
          // SECCIÓN 4: TOTAL ACTIVITY
          // ═══════════════════════════════════════════════════════════════════
          SliverToBoxAdapter(child: _buildTotalActivity()),

          // Espacio final para bottom nav
          const SliverToBoxAdapter(child: SizedBox(height: 100)),
        ],
      ),
    );
  }

  // ===========================================================================
  // HERO BACKGROUND — Gradiente de lago + avatar + tabs + nombre
  // ===========================================================================

  Widget _buildHeroBackground(
    String name,
    String email,
    String? avatarPath,
  ) {
    return Stack(
      fit: StackFit.expand,
      children: [
        // Fondo: gradiente tipo lago con cielo
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              stops: [0.0, 0.3, 0.6, 0.85, 1.0],
              colors: [
                Color(0xFFE8A838), // Cielo dorado/atardecer arriba
                Color(0xFF5BB3D0), // Cielo azul claro
                Color(0xFF2E8B9A), // Agua superficie
                Color(0xFF1A5F7A), // Agua profunda
                Color(0xFF0A1020), // Fade a fondo oscuro
              ],
            ),
          ),
        ),

        // Overlay de vegetación lateral (efecto decorativo)
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          height: 120,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  const Color(0xFF2D7A3A).withOpacity(0.3),
                  Colors.transparent,
                ],
              ),
            ),
          ),
        ),

        // Fade inferior para transición suave al contenido
        Positioned(
          bottom: 0,
          left: 0,
          right: 0,
          height: 150,
          child: Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.transparent,
                  Color(0xFF0A1020),
                ],
              ),
            ),
          ),
        ),

        // Contenido del hero
        SafeArea(
          child: Column(
            children: [
              // TabBar + botón logout
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Row(
                  children: [
                    Expanded(
                      child: TabBar(
                        controller: _tabController,
                        indicatorColor: Colors.white,
                        indicatorWeight: 3,
                        labelColor: Colors.white,
                        unselectedLabelColor: Colors.white60,
                        labelStyle: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 1,
                        ),
                        tabs: [
                          const Tab(text: 'ME'),
                          Tab(
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Text('FRIENDS'),
                                const SizedBox(width: 4),
                                // Punto verde de notificación
                                Container(
                                  width: 8,
                                  height: 8,
                                  decoration: const BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: AppTheme.successGreen,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const Tab(text: 'PARTY'),
                        ],
                      ),
                    ),
                    // Botón logout
                    IconButton(
                      icon: const Icon(Icons.logout, color: Colors.white),
                      onPressed: _handleLogout,
                    ),
                  ],
                ),
              ),

              // Spacer flexible para centrar el avatar
              const Spacer(flex: 2),

              // Avatar del usuario
              _buildHeroAvatar(name, avatarPath),
              const SizedBox(height: 16),

              // Nombre de usuario
              Text(
                name,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  shadows: [
                    Shadow(color: Colors.black54, blurRadius: 8),
                  ],
                ),
              ),
              const SizedBox(height: 4),

              // Email
              Text(
                email,
                style: const TextStyle(
                  color: Colors.white54,
                  fontSize: 13,
                ),
              ),

              const Spacer(flex: 1),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildHeroAvatar(String name, String? avatarPath) {
    final hasRealAvatar =
        avatarPath != null && File(avatarPath).existsSync();

    return Container(
      width: 110,
      height: 110,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 15,
            spreadRadius: 2,
          ),
        ],
        gradient: hasRealAvatar ? null : AppTheme.primaryGradient,
        image: hasRealAvatar
            ? DecorationImage(
                image: FileImage(File(avatarPath)),
                fit: BoxFit.cover,
              )
            : null,
      ),
      child: hasRealAvatar
          ? null
          : Center(
              child: Text(
                name.isNotEmpty ? name[0].toUpperCase() : 'P',
                style: const TextStyle(
                  fontSize: 44,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ),
    );
  }

  // ===========================================================================
  // BARRA DE NIVEL / XP
  // ===========================================================================

  Widget _buildLevelBar() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0D2137),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.gold.withOpacity(0.3),
        ),
      ),
      child: Column(
        children: [
          Row(
            children: [
              // Chip dorado NV. 1
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                decoration: BoxDecoration(
                  gradient: AppTheme.goldGradient,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'NV. 1',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              const Text(
                'Principiante',
                style: TextStyle(color: Colors.white, fontSize: 15),
              ),
              const Spacer(),
              const Text(
                '0 / 100 XP',
                style: TextStyle(
                  color: AppTheme.gold,
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: const LinearProgressIndicator(
              value: 0.0,
              minHeight: 8,
              backgroundColor: Color(0xFF1A2A3A),
              valueColor: AlwaysStoppedAnimation<Color>(Color(0xFFFFA500)),
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // ACCESOS RÁPIDOS — 4 BOTONES CIRCULARES
  // ===========================================================================

  Widget _buildQuickAccess() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: [
          _buildQuickButton(
            icon: Icons.people,
            label: 'BUDDY\nHISTORY',
            subtitle: 'Avistamientos',
            gradientColors: const [Color(0xFF11998E), Color(0xFF38EF7D)],
          ),
          _buildQuickButton(
            icon: Icons.straighten,
            label: 'SCRAPBOOK',
            subtitle: 'Pez más grande',
            gradientColors: const [Color(0xFF2193B0), Color(0xFF6DD5ED)],
          ),
          _buildQuickButton(
            icon: Icons.calendar_month,
            label: 'JOURNAL',
            subtitle: 'Días activos',
            gradientColors: const [Color(0xFF11998E), Color(0xFF38EF7D)],
          ),
          _buildQuickButton(
            icon: Icons.local_fire_department,
            label: 'STYLE',
            subtitle: 'Racha actual',
            gradientColors: const [Color(0xFFF7971E), Color(0xFFFFD200)],
          ),
        ],
      ),
    );
  }

  Widget _buildQuickButton({
    required IconData icon,
    required String label,
    required String subtitle,
    required List<Color> gradientColors,
  }) {
    return Column(
      children: [
        Container(
          width: 70,
          height: 70,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: gradientColors,
            ),
            boxShadow: [
              BoxShadow(
                color: gradientColors.first.withOpacity(0.4),
                blurRadius: 12,
                spreadRadius: 2,
              ),
            ],
          ),
          child: Icon(icon, color: Colors.white, size: 32),
        ),
        const SizedBox(height: 8),
        Text(
          label,
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 11,
            fontWeight: FontWeight.bold,
            height: 1.2,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          subtitle,
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 10,
          ),
        ),
      ],
    );
  }

  // ===========================================================================
  // TOTAL ACTIVITY — Lista de estadísticas
  // ===========================================================================

  Widget _buildTotalActivity() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      child: Column(
        children: [
          // Separador con título
          Row(
            children: [
              Expanded(
                child: Divider(color: Colors.white.withOpacity(0.2)),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  'TOTAL ACTIVITY',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                    fontSize: 13,
                    letterSpacing: 2,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Expanded(
                child: Divider(color: Colors.white.withOpacity(0.2)),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // Lista de actividad
          _buildActivityItem(
            icon: Icons.directions_walk,
            iconBgColor: Colors.blueGrey,
            title: 'Distance Walked',
            value: '-- km',
          ),
          _buildActivityItem(
            icon: Icons.phishing,
            iconBgColor: const Color(0xFF1565C0),
            title: 'Fish Caught',
            value: '0',
          ),
          _buildActivityItem(
            icon: Icons.explore,
            iconBgColor: const Color(0xFF006064),
            title: 'Locations Visited',
            value: '0',
          ),
          _buildActivityItem(
            icon: Icons.star,
            iconBgColor: const Color(0xFF4527A0),
            title: 'Total XP',
            value: '0',
          ),
        ],
      ),
    );
  }

  Widget _buildActivityItem({
    required IconData icon,
    required Color iconBgColor,
    required String title,
    required String value,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          // Ícono circular
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: iconBgColor.withOpacity(0.8),
            ),
            child: Icon(icon, color: Colors.white, size: 20),
          ),
          const SizedBox(width: 16),
          // Título
          Expanded(
            child: Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          // Valor
          Text(
            value,
            style: const TextStyle(
              color: Color(0xFF00BCD4),
              fontSize: 15,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}
