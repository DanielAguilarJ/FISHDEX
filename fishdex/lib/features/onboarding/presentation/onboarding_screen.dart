import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';

/// Pantalla de onboarding para nuevos usuarios
/// Se muestra solo la primera vez que abren la app.
/// Incluye 3 páginas de introducción + 1 página de selección de rol.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen>
    with TickerProviderStateMixin {
  final PageController _pageController = PageController();
  int _currentPage = 0;

  /// Animación de escaneo para la primera página
  late AnimationController _scanAnimationController;
  late Animation<double> _scanAnimation;

  /// Total de páginas: 3 intro + 1 selección de rol
  static const int _totalPages = 4;

  /// Datos estáticos de cada página intro (icono y gradiente únicamente)
  final List<_OnboardingPageData> _introPages = const [
    _OnboardingPageData(
      icon: Icons.phishing,
      gradient: AppTheme.primaryGradient,
    ),
    _OnboardingPageData(
      icon: Icons.emoji_events,
      gradient: AppTheme.goldGradient,
    ),
    _OnboardingPageData(
      icon: Icons.public,
      gradient: AppTheme.legendaryGradient,
    ),
  ];

  /// Devuelve los textos localizados para cada página intro
  List<({String title, String description})> _getIntroPageTexts(
      BuildContext context) {
    return [
      (
        title: context.l10n.onboardingPage1Title,
        description: context.l10n.onboardingPage1Desc,
      ),
      (
        title: context.l10n.onboardingPage2Title,
        description: context.l10n.onboardingPage2Desc,
      ),
      (
        title: context.l10n.onboardingPage3Title,
        description: context.l10n.onboardingPage3Desc,
      ),
    ];
  }

  @override
  void initState() {
    super.initState();
    // Controlador de animación de escaneo (loop)
    _scanAnimationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    _scanAnimation = Tween<double>(begin: -1.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _scanAnimationController,
        curve: Curves.easeInOut,
      ),
    );
  }

  @override
  void dispose() {
    _pageController.dispose();
    _scanAnimationController.dispose();
    super.dispose();
  }

  /// Marca el onboarding como completado y navega al registro con rol seleccionado
  Future<void> _completeOnboardingWithRole(String role) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_completed', true);
    await prefs.setString('selected_role', role);
    if (mounted) {
      context.go('/register');
    }
  }

  /// Salta directamente a la selección de rol
  void _skipToRoleSelection() {
    _pageController.animateToPage(
      _totalPages - 1,
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeInOut,
    );
  }

  /// Avanza a la siguiente página
  void _nextPage() {
    if (_currentPage < _totalPages - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOut,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: SafeArea(
        child: Column(
          children: [
            // Botón saltar (arriba derecha) - solo en páginas de intro
            _buildSkipButton(),

            // Contenido de las páginas
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                onPageChanged: (index) {
                  setState(() => _currentPage = index);
                },
                itemCount: _totalPages,
                itemBuilder: (context, index) {
                  if (index < _introPages.length) {
                    final texts = _getIntroPageTexts(context);
                    return _buildPage(
                      _introPages[index],
                      index,
                      texts[index].title,
                      texts[index].description,
                    );
                  } else {
                    return _buildRoleSelectionPage();
                  }
                },
              ),
            ),

            // Indicador de puntos
            _buildDotsIndicator(),

            const SizedBox(height: 24),

            // Botón de acción (solo en páginas de intro)
            if (_currentPage < _introPages.length) _buildActionButton(),

            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  /// Botón de saltar en la esquina superior derecha
  Widget _buildSkipButton() {
    return Align(
      alignment: Alignment.centerRight,
      child: Padding(
        padding: const EdgeInsets.only(right: 16, top: 8),
        child: _currentPage < _introPages.length
            ? TextButton(
                onPressed: _skipToRoleSelection,
                child: Text(
                  context.l10n.onboardingSkip,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 16,
                  ),
                ),
              )
            : const SizedBox(height: 48),
      ),
    );
  }

  /// Construye una página individual del onboarding
  Widget _buildPage(
    _OnboardingPageData page,
    int index,
    String title,
    String description,
  ) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Icono animado
          _buildAnimatedIcon(page, index),

          const SizedBox(height: 48),

          // Título
          Text(
            title,
            style: Theme.of(context).textTheme.displayMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                ),
            textAlign: TextAlign.center,
          ),

          const SizedBox(height: 20),

          // Descripción
          Text(
            description,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Colors.white.withOpacity(0.7),
                  height: 1.5,
                ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  /// Icono principal con animación según la página
  Widget _buildAnimatedIcon(_OnboardingPageData page, int index) {
    return AnimatedBuilder(
      animation: _scanAnimation,
      builder: (context, child) {
        return Container(
          width: 160,
          height: 160,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: page.gradient,
            boxShadow: [
              BoxShadow(
                color: page.gradient.colors.first.withOpacity(0.4),
                blurRadius: 30,
                spreadRadius: 5,
              ),
            ],
          ),
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Icono principal
              Icon(
                page.icon,
                size: 72,
                color: Colors.white,
              ),

              // Línea de escaneo (solo para la página 1)
              if (index == 0)
                Positioned(
                  top: 80 + (_scanAnimation.value * 40),
                  left: 20,
                  right: 20,
                  child: Container(
                    height: 2,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          Colors.transparent,
                          AppTheme.teal.withOpacity(0.8),
                          Colors.transparent,
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  /// Indicador de puntos de la página actual
  Widget _buildDotsIndicator() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(_totalPages, (index) {
        final isActive = index == _currentPage;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 300),
          margin: const EdgeInsets.symmetric(horizontal: 4),
          width: isActive ? 28 : 10,
          height: 10,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(5),
            color: isActive
                ? AppTheme.accentBlue
                : Colors.white.withOpacity(0.3),
          ),
        );
      }),
    );
  }

  /// Botón de acción (Siguiente - solo páginas intro)
  Widget _buildActionButton() {
    final isLastIntroPage = _currentPage == _introPages.length - 1;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: SizedBox(
        width: double.infinity,
        height: 56,
        child: ElevatedButton(
          onPressed: _nextPage,
          style: ElevatedButton.styleFrom(
            backgroundColor:
                isLastIntroPage ? AppTheme.successGreen : AppTheme.accentBlue,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            elevation: 4,
          ),
          child: Text(
            isLastIntroPage
                ? context.l10n.onboardingChooseRole
                : context.l10n.next,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              letterSpacing: 1,
            ),
          ),
        ),
      ),
    );
  }

  // ===========================================================================
  // PÁGINA DE SELECCIÓN DE ROL
  // ===========================================================================

  /// Construye la página de selección de rol (pescador o investigador)
  Widget _buildRoleSelectionPage() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            context.l10n.onboardingRoleTitle,
            style: Theme.of(context).textTheme.displayMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          Text(
            context.l10n.onboardingRoleSubtitle,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Colors.white.withOpacity(0.6),
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 40),

          // Tarjeta: Pescador
          _buildRoleCard(
            icon: Icons.phishing,
            title: context.l10n.onboardingFishermanTitle,
            description: context.l10n.onboardingFishermanDesc,
            gradient: AppTheme.primaryGradient,
            onTap: () => _completeOnboardingWithRole('fisherman'),
          ),

          const SizedBox(height: 20),

          // Tarjeta: Investigador
          _buildRoleCard(
            icon: Icons.biotech,
            title: context.l10n.onboardingResearcherTitle,
            description: context.l10n.onboardingResearcherDesc,
            gradient: AppTheme.legendaryGradient,
            onTap: () => _completeOnboardingWithRole('researcher'),
            badge: context.l10n.onboardingRequiresApproval,
          ),
        ],
      ),
    );
  }

  /// Tarjeta de selección de rol
  Widget _buildRoleCard({
    required IconData icon,
    required String title,
    required String description,
    required LinearGradient gradient,
    required VoidCallback onTap,
    String? badge,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: gradient.colors.first.withOpacity(0.4),
            width: 1.5,
          ),
          color: Colors.white.withOpacity(0.05),
        ),
        child: Row(
          children: [
            // Ícono circular
            Container(
              width: 60,
              height: 60,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: gradient,
              ),
              child: Icon(icon, color: Colors.white, size: 30),
            ),
            const SizedBox(width: 16),

            // Texto
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      if (badge != null) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.orange.withOpacity(0.2),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: Colors.orange.withOpacity(0.5),
                            ),
                          ),
                          child: Text(
                            badge,
                            style: const TextStyle(
                              color: Colors.orange,
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    description,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.6),
                      fontSize: 13,
                      height: 1.3,
                    ),
                  ),
                ],
              ),
            ),

            // Flecha
            Icon(
              Icons.arrow_forward_ios,
              color: Colors.white.withOpacity(0.4),
              size: 18,
            ),
          ],
        ),
      ),
    );
  }
}

/// Datos inmutables para cada página del onboarding (icono y gradiente)
class _OnboardingPageData {
  final IconData icon;
  final LinearGradient gradient;

  const _OnboardingPageData({
    required this.icon,
    required this.gradient,
  });
}
