import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/theme/app_theme.dart';

/// Pantalla de onboarding para nuevos usuarios
/// Se muestra solo la primera vez que abren la app
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

  /// Datos de cada página del onboarding
  final List<_OnboardingPageData> _pages = const [
    _OnboardingPageData(
      icon: Icons.phishing,
      title: 'Identifica Peces',
      description:
          'Usa la cámara para grabar peces en su hábitat natural. '
          'Nuestra IA identifica cada pez individualmente, como una '
          'huella dactilar submarina.',
      gradient: AppTheme.primaryGradient,
    ),
    _OnboardingPageData(
      icon: Icons.emoji_events,
      title: 'Colecciona y Compite',
      description:
          'Construye tu FishDex como un Pokédex acuático. '
          'Descubre especies raras, gana XP, sube de nivel y '
          'compite en el ranking con otros exploradores.',
      gradient: AppTheme.goldGradient,
    ),
    _OnboardingPageData(
      icon: Icons.public,
      title: 'Contribuye a la Ciencia',
      description:
          'Cada avistamiento ayuda a los investigadores a rastrear '
          'migración, crecimiento y salud de los ecosistemas marinos. '
          'Tus datos hacen la diferencia.',
      gradient: AppTheme.legendaryGradient,
    ),
  ];

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

  /// Marca el onboarding como completado y navega al login
  Future<void> _completeOnboarding() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_completed', true);
    if (mounted) {
      context.go('/login');
    }
  }

  /// Avanza a la siguiente página o completa el onboarding
  void _nextPage() {
    if (_currentPage < _pages.length - 1) {
      _pageController.nextPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOut,
      );
    } else {
      _completeOnboarding();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: SafeArea(
        child: Column(
          children: [
            // Botón saltar (arriba derecha)
            _buildSkipButton(),

            // Contenido de las páginas
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                onPageChanged: (index) {
                  setState(() => _currentPage = index);
                },
                itemCount: _pages.length,
                itemBuilder: (context, index) {
                  return _buildPage(_pages[index], index);
                },
              ),
            ),

            // Indicador de puntos
            _buildDotsIndicator(),

            const SizedBox(height: 24),

            // Botón de acción
            _buildActionButton(),

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
        child: _currentPage < _pages.length - 1
            ? TextButton(
                onPressed: _completeOnboarding,
                child: Text(
                  'Saltar',
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
  Widget _buildPage(_OnboardingPageData page, int index) {
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
            page.title,
            style: Theme.of(context).textTheme.displayMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                ),
            textAlign: TextAlign.center,
          ),

          const SizedBox(height: 20),

          // Descripción
          Text(
            page.description,
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
      children: List.generate(_pages.length, (index) {
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

  /// Botón de acción (Siguiente o Comenzar)
  Widget _buildActionButton() {
    final isLastPage = _currentPage == _pages.length - 1;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: SizedBox(
        width: double.infinity,
        height: 56,
        child: ElevatedButton(
          onPressed: _nextPage,
          style: ElevatedButton.styleFrom(
            backgroundColor:
                isLastPage ? AppTheme.successGreen : AppTheme.accentBlue,
            foregroundColor: Colors.white,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
            ),
            elevation: 4,
          ),
          child: Text(
            isLastPage ? 'COMENZAR' : 'Siguiente',
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
}

/// Datos inmutables para cada página del onboarding
class _OnboardingPageData {
  final IconData icon;
  final String title;
  final String description;
  final LinearGradient gradient;

  const _OnboardingPageData({
    required this.icon,
    required this.title,
    required this.description,
    required this.gradient,
  });
}
