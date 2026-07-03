import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../theme/app_theme.dart';

// ─── Modelo de cada acción del Speed Dial ─────────────────────────────────────
class _DialItem {
  final IconData icon;
  final String label;
  final List<Color> gradientColors;
  final double angle; // grados matemáticos: 0=derecha, 90=arriba, 135=arriba-izq
  final String route;

  const _DialItem({
    required this.icon,
    required this.label,
    required this.gradientColors,
    required this.angle,
    required this.route,
  });
}

/// Shell principal con Bottom Navigation Bar gamificada y Speed Dial al estilo Pokémon GO
class MainShell extends ConsumerStatefulWidget {
  final Widget child;
  const MainShell({super.key, required this.child});

  @override
  ConsumerState<MainShell> createState() => _MainShellState();
}

class _MainShellState extends ConsumerState<MainShell>
    with SingleTickerProviderStateMixin {
  bool _isOpen = false;
  late AnimationController _controller;
  late Animation<double> _dialAnim;

  // ── Las 3 sub-acciones del Speed Dial ────────────────────────────────────────
  static const _dialItems = [
    _DialItem(
      icon: Icons.photo_library_rounded,
      label: 'Galería',
      gradientColors: [Color(0xFF00BCD4), Color(0xFF006064)],
      angle: 135.0, // arriba-izquierda
      route: '/gallery',
    ),
    _DialItem(
      icon: Icons.videocam_rounded,
      label: 'Identificar',
      gradientColors: [Color(0xFF0D47A1), Color(0xFF00BCD4)],
      angle: 90.0, // recto hacia arriba
      route: '/camera',
    ),
    _DialItem(
      icon: Icons.add_location_alt_rounded,
      label: 'Spot',
      gradientColors: [Color(0xFF66BB6A), Color(0xFF1B5E20)],
      angle: 45.0, // arriba-derecha
      route: '/quick-spot',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 320),
    );
    _dialAnim = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutBack,
      reverseCurve: Curves.easeIn,
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  // ── Control del menú ──────────────────────────────────────────────────────────
  void _toggleDial() {
    setState(() {
      _isOpen = !_isOpen;
      _isOpen ? _controller.forward() : _controller.reverse();
    });
  }

  void _closeDial() {
    if (!_isOpen) return;
    setState(() => _isOpen = false);
    _controller.reverse();
  }

  void _onDialAction(BuildContext context, String route) {
    _closeDial();
    // Capturar el router antes del gap async para evitar usar context en async
    final router = GoRouter.of(context);
    Future.delayed(const Duration(milliseconds: 120), () {
      if (mounted) router.go(route);
    });
  }

  void _onNavTap(BuildContext context, int index) {
    _closeDial();
    switch (index) {
      case 0:
        context.go('/map');
      case 1:
        context.go('/collection');
      case 3:
        context.go('/ranking');
      case 4:
        context.go('/profile');
    }
  }

  int _getIndexFromLocation(String location) {
    if (location.startsWith('/map')) return 0;
    if (location.startsWith('/collection')) return 1;
    if (location.startsWith('/camera') ||
        location.startsWith('/gallery') ||
        location.startsWith('/quick-spot')) return 2;
    if (location.startsWith('/ranking')) return 3;
    if (location.startsWith('/profile')) return 4;
    return 0;
  }

  // ── Build principal ───────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Scaffold(
          body: widget.child,
          bottomNavigationBar: _buildBottomNav(context),
          extendBody: true,
        ),
        _buildDimOverlay(),
        _buildDialButtons(context),
      ],
    );
  }

  // ── Overlay oscuro semitransparente ───────────────────────────────────────────
  Widget _buildDimOverlay() {
    return AnimatedBuilder(
      animation: _controller,
      builder: (_, __) {
        final v = _controller.value;
        if (v == 0) return const SizedBox.shrink();
        return Positioned.fill(
          child: GestureDetector(
            onTap: _closeDial,
            behavior: HitTestBehavior.opaque,
            child: Container(
              color: Colors.black.withOpacity(0.6 * v),
            ),
          ),
        );
      },
    );
  }

  // ── Botones del Speed Dial en arco ────────────────────────────────────────────
  Widget _buildDialButtons(BuildContext context) {
    final mq = MediaQuery.of(context);
    final screenWidth = mq.size.width;
    final bottomPad = mq.padding.bottom;

    // Altura de la nav bar: contenido 80px + safe area
    const navContentH = 80.0;
    final navBarH = navContentH + bottomPad;

    // Centro del FAB desde el borde inferior de la pantalla
    final fabFromBottom = navBarH / 2;
    // Centro del FAB desde el borde izquierdo
    final fabFromLeft = screenWidth / 2;

    // Radio del arco en px
    const radius = 105.0;
    // Tamaño del círculo de cada sub-botón
    const btnSize = 54.0;
    // Altura del label bajo el botón (~18px texto + 4px margen)
    const labelH = 22.0;
    const gapH = 4.0;

    return AnimatedBuilder(
      animation: _dialAnim,
      builder: (_, __) {
        final t = _dialAnim.value;
        return Stack(
          children: _dialItems.map((item) {
            final rad = item.angle * math.pi / 180.0;
            final dx = math.cos(rad) * radius * t;
            final dy = math.sin(rad) * radius * t;

            // Centro del círculo en coordenadas "desde abajo"
            final circleX = fabFromLeft + dx;
            final circleFromBottom = fabFromBottom + dy;

            // El widget es: [círculo btnSize] + [gap gapH] + [label labelH]
            // "bottom" de Positioned = borde inferior del widget completo
            // borde inferior = circleCenter - btnSize/2 - gapH - labelH
            final left = circleX - btnSize / 2;
            final bottom = circleFromBottom - btnSize / 2 - gapH - labelH;

            return Positioned(
              left: left,
              bottom: bottom,
              child: Opacity(
                opacity: t.clamp(0.0, 1.0),
                child: Transform.scale(
                  scale: 0.25 + 0.75 * t,
                  alignment: Alignment.bottomCenter,
                  child: _buildDialButton(context, item),
                ),
              ),
            );
          }).toList(),
        );
      },
    );
  }

  Widget _buildDialButton(BuildContext context, _DialItem item) {
    return GestureDetector(
      onTap: () => _onDialAction(context, item.route),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Círculo con gradiente y sombra
          Container(
            width: 54,
            height: 54,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                colors: item.gradientColors,
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              boxShadow: [
                BoxShadow(
                  color: item.gradientColors.first.withOpacity(0.45),
                  blurRadius: 12,
                  offset: const Offset(0, 4),
                ),
                BoxShadow(
                  color: Colors.black.withOpacity(0.3),
                  blurRadius: 6,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Icon(item.icon, color: Colors.white, size: 24),
          ),
          const SizedBox(height: 4),
          // Label con fondo oscuro (estilo Pokémon GO)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.72),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              item.label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.4,
              ),
              maxLines: 1,
            ),
          ),
        ],
      ),
    );
  }

  // ── Barra de navegación inferior ─────────────────────────────────────────────
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
              // Botón central del Speed Dial
              _buildCenterFab(context, currentIndex),
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

  // ── FAB central (abre/cierra el Speed Dial) ───────────────────────────────────
  Widget _buildCenterFab(BuildContext context, int currentIndex) {
    final isActive = currentIndex == 2;

    return AnimatedBuilder(
      animation: _controller,
      builder: (_, __) {
        final t = _controller.value;
        return GestureDetector(
          onTap: _toggleDial,
          child: Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                colors: _isOpen
                    ? const [Color(0xFF37474F), Color(0xFF263238)]
                    : isActive
                        ? [AppTheme.primaryBlue, AppTheme.teal]
                        : [AppTheme.accentBlue, AppTheme.teal],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              boxShadow: [
                BoxShadow(
                  color: (_isOpen
                          ? const Color(0xFF37474F)
                          : AppTheme.accentBlue)
                      .withOpacity(0.5),
                  blurRadius: 16,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            // El ícono rota 135° al abrir → efecto + → ✕
            child: Transform.rotate(
              angle: t * math.pi * 0.75,
              child: Icon(
                _isOpen ? Icons.close_rounded : Icons.add_rounded,
                color: Colors.white,
                size: 30,
              ),
            ),
          ),
        );
      },
    );
  }

  // ── Ítems normales de la nav bar ──────────────────────────────────────────────
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
      onTap: () => _onNavTap(context, index),
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
}
