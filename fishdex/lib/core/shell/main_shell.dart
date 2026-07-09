import 'dart:math' as math;
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../l10n/l10n_extension.dart';
import '../theme/app_theme.dart';

// ─── Modelo de cada acción del Speed Dial ─────────────────────────────────────
class _DialItem {
  final IconData icon;
  final String label;
  final double angle; // grados: 0=derecha, 90=arriba, 135=arriba-izq, 45=arriba-der
  final String route;

  const _DialItem({
    required this.icon,
    required this.label,
    required this.angle,
    required this.route,
  });
}

/// Shell principal con Bottom Navigation Bar y Speed Dial estilo Pokémon GO
class MainShell extends ConsumerStatefulWidget {
  final Widget child;
  const MainShell({super.key, required this.child});

  @override
  ConsumerState<MainShell> createState() => _MainShellState();
}

class _MainShellState extends ConsumerState<MainShell>
    with TickerProviderStateMixin {
  bool _isOpen = false;

  // ── Controladores de animación ─────────────────────────────────────────────
  late AnimationController _dialController;    // apertura/cierre del menú
  late AnimationController _pulseController;   // pulso del FAB cuando cerrado
  late Animation<double> _pulseAnim;
  late List<Animation<double>> _itemAnims;     // stagger por ítem

  // ── Las 3 sub-acciones ─────────────────────────────────────────────────────
  // NOTE: labels are set dynamically in _buildDialButton using l10n
  static const _dialItems = [
    _DialItem(
      icon: Icons.photo_library_outlined,
      label: 'gallery',   // key for l10n lookup
      angle: 135.0,
      route: '/gallery',
    ),
    _DialItem(
      icon: Icons.camera_alt_outlined,
      label: 'identify',
      angle: 90.0,
      route: '/camera',
    ),
    _DialItem(
      icon: Icons.location_on_outlined,
      label: 'spot',
      angle: 45.0,
      route: '/quick-spot',
    ),
  ];

  @override
  void initState() {
    super.initState();

    // Controlador del dial (350ms, easeOutBack por ítem)
    _dialController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 350),
    );

    // Animaciones escalonadas (stagger 40ms entre ítems)
    _itemAnims = List.generate(_dialItems.length, (i) {
      return CurvedAnimation(
        parent: _dialController,
        curve: Interval(
          i * 0.15,
          (i * 0.15 + 0.70).clamp(0.0, 1.0),
          curve: Curves.easeOutBack,
        ),
        reverseCurve: Interval(
          i * 0.10,
          (i * 0.10 + 0.60).clamp(0.0, 1.0),
          curve: Curves.easeIn,
        ),
      );
    });

    // Pulso del FAB cuando el menú está cerrado
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);

    _pulseAnim = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _dialController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  // ── Control del menú ──────────────────────────────────────────────────────────
  void _toggleDial() {
    setState(() {
      _isOpen = !_isOpen;
      if (_isOpen) {
        _dialController.forward();
        _pulseController.stop();
      } else {
        _dialController.reverse();
        _pulseController.repeat(reverse: true);
      }
    });
  }

  void _closeDial() {
    if (!_isOpen) return;
    setState(() => _isOpen = false);
    _dialController.reverse();
    _pulseController.repeat(reverse: true);
  }

  void _onDialAction(BuildContext context, String route) {
    _closeDial();
    final router = GoRouter.of(context);
    // Navigate immediately - no artificial delay
    if (mounted) router.go(route);
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
        _buildGlassmorphismOverlay(),
        _buildDialButtons(context),
      ],
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 1. OVERLAY con glassmorphism (blur + oscuro semitransparente)
  // ─────────────────────────────────────────────────────────────────────────────
  Widget _buildGlassmorphismOverlay() {
    return AnimatedBuilder(
      animation: _dialController,
      builder: (_, __) {
        final v = _dialController.value;
        if (v == 0) return const SizedBox.shrink();
        return Positioned.fill(
          child: GestureDetector(
            onTap: _closeDial,
            behavior: HitTestBehavior.opaque,
            child: BackdropFilter(
              filter: ImageFilter.blur(
                sigmaX: 8.0 * v,
                sigmaY: 8.0 * v,
              ),
              child: Container(
                color: AppTheme.darkBackground.withOpacity(0.65 * v),
              ),
            ),
          ),
        );
      },
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 2. BOTONES del Speed Dial en arco con stagger
  // ─────────────────────────────────────────────────────────────────────────────
  Widget _buildDialButtons(BuildContext context) {
    final mq = MediaQuery.of(context);
    final screenWidth = mq.size.width;
    final bottomPad = mq.padding.bottom;

    // Nav bar: FAB 72px + padding vertical 16px = 88px de contenido + SafeArea
    // Centro del FAB desde el borde inferior de la pantalla:
    // = bottomPad (safe area) + 8 (padding bottom) + 36 (mitad del FAB 72px)
    final fabFromBottom = bottomPad + 44.0;
    final fabFromLeft = screenWidth / 2;

    const radius = 120.0;      // radio del arco
    const circleSize = 72.0;   // tamaño del círculo sub-botón
    const widgetW = 90.0;      // ancho del widget (circle centrado dentro)

    return AnimatedBuilder(
      animation: _dialController,
      builder: (_, __) {
        return Stack(
          children: List.generate(_dialItems.length, (i) {
            final item = _dialItems[i];
            final t = _itemAnims[i].value;

            if (t == 0) return const SizedBox.shrink();

            final rad = item.angle * math.pi / 180.0;
            final dx = math.cos(rad) * radius * t;
            final dy = math.sin(rad) * radius * t;

            // Centro del círculo en pantalla (coordenadas desde abajo)
            final circleX = fabFromLeft + dx;
            final circleFromBottom = fabFromBottom + dy;

            // Positioned.bottom = borde inferior del widget.
            // El widget tiene: [label] + [gap] + [circle].
            // El círculo está al FONDO de la columna, así que el borde inferior
            // del widget = borde inferior del círculo.
            // borde inferior del círculo = circleCenter - circleSize/2
            final left = circleX - widgetW / 2;
            final bottom = circleFromBottom - circleSize / 2;

            return Positioned(
              left: left,
              bottom: bottom,
              child: Opacity(
                opacity: t.clamp(0.0, 1.0),
                child: Transform.scale(
                  scale: 0.3 + 0.7 * t,
                  alignment: Alignment.bottomCenter,
                  child: _buildDialButton(context, item),
                ),
              ),
            );
          }),
        );
      },
    );
  }

  /// Un sub-botón individual del Speed Dial:
  /// label (encima) → gap → círculo estilo glass con ícono teal
  Widget _buildDialButton(BuildContext context, _DialItem item) {
    final l10n = context.l10n;
    String label;
    switch (item.label) {
      case 'gallery':
        label = l10n.navGallery;
        break;
      case 'identify':
        label = l10n.navIdentify;
        break;
      case 'spot':
        label = l10n.navSpot;
        break;
      default:
        label = item.label;
    }
    return GestureDetector(
      onTap: () => _onDialAction(context, item.route),
      child: SizedBox(
        width: 90,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // ── Label ENCIMA (estilo Pokémon GO) ─────────────────────────────
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: AppTheme.primaryBlue.withOpacity(0.88),
                borderRadius: BorderRadius.circular(6),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.35),
                    blurRadius: 4,
                    offset: const Offset(0, 1),
                  ),
                ],
              ),
              child: Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.5,
                ),
                maxLines: 1,
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 5),

            // ── Círculo con darkSurface + borde accentBlue + ícono teal ──────
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppTheme.darkSurface.withOpacity(0.95),
                border: Border.all(
                  color: AppTheme.accentBlue.withOpacity(0.50),
                  width: 1.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: AppTheme.accentBlue.withOpacity(0.30),
                    blurRadius: 16,
                    spreadRadius: 2,
                    offset: const Offset(0, 4),
                  ),
                  BoxShadow(
                    color: Colors.black.withOpacity(0.28),
                    blurRadius: 8,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Icon(
                item.icon,
                color: AppTheme.teal,
                size: 30,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 3. FAB CENTRAL con pulso animado
  // ─────────────────────────────────────────────────────────────────────────────
  Widget _buildCenterFab(BuildContext context, int currentIndex) {
    return AnimatedBuilder(
      animation: Listenable.merge([_dialController, _pulseController]),
      builder: (_, __) {
        final dialT = _dialController.value;
        final pulseV = _pulseAnim.value;

        // Escala pulsante solo cuando el menú está cerrado
        final pulseScale = _isOpen ? 1.0 : (1.0 + 0.03 * pulseV);
        // Glow pulsante: más grande e intenso cuando cerrado
        final glowRadius = _isOpen ? 10.0 : (10.0 + 8.0 * pulseV);
        final glowOpacity = _isOpen ? 0.18 : (0.18 + 0.20 * pulseV);
        final glowSpread = _isOpen ? 0.0 : (1.0 * pulseV);

        return GestureDetector(
          onTap: _toggleDial,
          child: Transform.scale(
            scale: pulseScale,
            child: Container(
              width: 72,
              height: 72,
              decoration: _isOpen
                  ? BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppTheme.darkSurface,
                      border: Border.all(
                        color: AppTheme.accentBlue,
                        width: 2,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: AppTheme.accentBlue.withOpacity(0.18),
                          blurRadius: 10,
                        ),
                      ],
                    )
                  : BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: const LinearGradient(
                        colors: [AppTheme.primaryBlue, AppTheme.teal],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: AppTheme.accentBlue.withOpacity(glowOpacity),
                          blurRadius: glowRadius,
                          spreadRadius: glowSpread,
                        ),
                      ],
                    ),
              child: Transform.rotate(
                angle: dialT * math.pi * 0.75, // rota 0→135° al abrir
                child: Icon(
                  _isOpen ? Icons.close_rounded : Icons.camera_alt_rounded,
                  color: _isOpen ? AppTheme.teal : Colors.white,
                  size: 30,
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 4. BOTTOM NAV BAR con esquinas redondeadas y pill highlight
  // ─────────────────────────────────────────────────────────────────────────────
  Widget _buildBottomNav(BuildContext context) {
    final location = GoRouterState.of(context).matchedLocation;
    final currentIndex = _getIndexFromLocation(location);
    final l10n = context.l10n;

    return Container(
      decoration: BoxDecoration(
        color: AppTheme.darkBackground,
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(20),
          topRight: Radius.circular(20),
        ),
        border: Border(
          top: BorderSide(
            color: AppTheme.accentBlue.withOpacity(0.20),
            width: 1,
          ),
        ),
        boxShadow: [
          BoxShadow(
            color: AppTheme.accentBlue.withOpacity(0.08),
            blurRadius: 24,
            offset: const Offset(0, -6),
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
                label: l10n.navMap,
                index: 0,
                currentIndex: currentIndex,
              ),
              _buildNavItem(
                context,
                icon: Icons.collections_bookmark_outlined,
                activeIcon: Icons.collections_bookmark,
                label: l10n.navCollection,
                index: 1,
                currentIndex: currentIndex,
              ),
              _buildCenterFab(context, currentIndex),
              _buildNavItem(
                context,
                icon: Icons.leaderboard_outlined,
                activeIcon: Icons.leaderboard,
                label: l10n.navRanking,
                index: 3,
                currentIndex: currentIndex,
              ),
              _buildNavItem(
                context,
                icon: Icons.person_outline,
                activeIcon: Icons.person,
                label: l10n.navProfile,
                index: 4,
                currentIndex: currentIndex,
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 5. ÍTEMS DE NAV con AnimatedContainer (pill highlight activo)
  // ─────────────────────────────────────────────────────────────────────────────
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
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        curve: Curves.easeOut,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          // Pill highlight en el ítem activo (reemplaza el punto indicador)
          color: isActive
              ? AppTheme.accentBlue.withOpacity(0.15)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isActive ? activeIcon : icon,
              // Activo: teal brillante / Inactivo: blanco apagado
              color: isActive
                  ? AppTheme.teal
                  : Colors.white.withOpacity(0.45),
              size: 24,
            ),
            const SizedBox(height: 3),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight:
                    isActive ? FontWeight.w700 : FontWeight.normal,
                // Activo: accentBlue / Inactivo: blanco apagado
                color: isActive
                    ? AppTheme.accentBlue
                    : Colors.white.withOpacity(0.45),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
