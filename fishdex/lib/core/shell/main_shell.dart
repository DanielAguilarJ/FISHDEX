import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../theme/app_theme.dart';

/// Shell principal con Bottom Navigation Bar gamificada
/// Contiene las 5 pestañas: Mapa, Cámara, Colección, Ranking, Perfil
class MainShell extends StatelessWidget {
  final Widget child;

  const MainShell({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: _buildBottomNav(context),
      extendBody: true,
    );
  }

  Widget _buildBottomNav(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    final currentIndex = _getIndexFromLocation(location);

    return Container(
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        boxShadow: [
          BoxShadow(
            color: AppTheme.accentBlue.withOpacity(0.1),
            blurRadius: 20,
            offset: const Offset(0, -5),
          ),
        ],
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildNavItem(
                context,
                icon: Icons.map_outlined,
                activeIcon: Icons.map,
                label: 'Mapa',
                index: 0,
                currentIndex: currentIndex,
              ),
              _buildNavItem(
                context,
                icon: Icons.collections_bookmark_outlined,
                activeIcon: Icons.collections_bookmark,
                label: 'Colección',
                index: 1,
                currentIndex: currentIndex,
              ),
              _buildCameraButton(context, currentIndex),
              _buildNavItem(
                context,
                icon: Icons.leaderboard_outlined,
                activeIcon: Icons.leaderboard,
                label: 'Ranking',
                index: 3,
                currentIndex: currentIndex,
              ),
              _buildNavItem(
                context,
                icon: Icons.person_outline,
                activeIcon: Icons.person,
                label: 'Perfil',
                index: 4,
                currentIndex: currentIndex,
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Botón central de cámara (más grande, estilo Pokémon Go)
  Widget _buildCameraButton(BuildContext context, int currentIndex) {
    final isActive = currentIndex == 2;
    
    return GestureDetector(
      onTap: () => _onItemTapped(context, 2),
      child: Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: isActive
              ? AppTheme.primaryGradient
              : const LinearGradient(
                  colors: [AppTheme.accentBlue, AppTheme.teal],
                ),
          boxShadow: [
            BoxShadow(
              color: AppTheme.accentBlue.withOpacity(0.4),
              blurRadius: 12,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: const Icon(
          Icons.camera_alt,
          color: Colors.white,
          size: 28,
        ),
      ),
    );
  }

  Widget _buildNavItem(
    BuildContext context, {
    required IconData icon,
    required IconData activeIcon,
    required String label,
    required int index,
    required int currentIndex,
  }) {
    final isActive = index == currentIndex;
    
    return GestureDetector(
      onTap: () => _onItemTapped(context, index),
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: 60,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isActive ? activeIcon : icon,
              color: isActive ? AppTheme.accentBlue : Colors.white38,
              size: 24,
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                color: isActive ? AppTheme.accentBlue : Colors.white38,
              ),
            ),
            if (isActive)
              Container(
                margin: const EdgeInsets.only(top: 4),
                width: 4,
                height: 4,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppTheme.accentBlue,
                ),
              ),
          ],
        ),
      ),
    );
  }

  int _getIndexFromLocation(String location) {
    if (location.startsWith('/map')) return 0;
    if (location.startsWith('/collection')) return 1;
    if (location.startsWith('/camera')) return 2;
    if (location.startsWith('/ranking')) return 3;
    if (location.startsWith('/profile')) return 4;
    return 0;
  }

  void _onItemTapped(BuildContext context, int index) {
    switch (index) {
      case 0:
        context.go('/map');
        break;
      case 1:
        context.go('/collection');
        break;
      case 2:
        context.go('/camera');
        break;
      case 3:
        context.go('/ranking');
        break;
      case 4:
        context.go('/profile');
        break;
    }
  }
}
