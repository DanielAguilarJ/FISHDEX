import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../providers/auth_provider.dart';
import '../../../core/theme/app_theme.dart';

/// Splash Screen con animación de carga y logo de FishDex
class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key});

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _fadeAnimation;
  late Animation<double> _scaleAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeIn),
    );

    _scaleAnimation = Tween<double>(begin: 0.5, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.elasticOut),
    );

    _controller.forward();

    // Verificar autenticación después de la animación
    Future.delayed(const Duration(milliseconds: 2500), () {
      _checkAuth();
    });
  }

  Future<void> _checkAuth() async {
    if (!mounted) return;

    final prefs = await SharedPreferences.getInstance();

    // 1. Verificar si ya completó el onboarding informativo
    final onboardingCompleted = prefs.getBool('onboarding_completed') ?? false;
    if (!onboardingCompleted) {
      if (mounted) context.go('/onboarding');
      return;
    }

    // 2. Verificar si el usuario eligió modo demo anteriormente
    final isDemoMode = prefs.getBool('is_demo_mode') ?? false;
    if (isDemoMode) {
      if (mounted) context.go('/map');
      return;
    }

    // 3. Intentar verificar sesión de Appwrite
    try {
      final authState = await ref
          .read(authStateProvider.future)
          .timeout(const Duration(seconds: 6));

      if (authState != null) {
        // Autenticado → marcar sesión activa y verificar profile setup
        await prefs.setBool('has_active_session', true);
        await prefs.setBool('is_demo_mode', false);

        // Verificar rol y estado de aprobación
        final cachedRole = prefs.getString('cached_user_role') ?? 'fisherman';
        final cachedStatus = prefs.getString('cached_approval_status') ?? 'approved';

        // Si es researcher pendiente → ir a pantalla de espera
        if (cachedRole == 'researcher' && cachedStatus == 'pending') {
          if (mounted) context.go('/pending-approval');
          return;
        }

        // Si es researcher rechazado → ir a login
        if (cachedRole == 'researcher' && cachedStatus == 'rejected') {
          if (mounted) context.go('/login');
          return;
        }

        final profileSetupCompleted =
            prefs.getBool('profile_setup_completed') ?? false;
        if (!profileSetupCompleted) {
          if (mounted) context.go('/profile-setup');
        } else {
          if (mounted) context.go('/map');
        }
      } else {
        // Servidor respondió 401: no hay sesión activa → ir a login
        await prefs.setBool('has_active_session', false);
        if (mounted) context.go('/login');
      }
    } on NetworkAuthException catch (e) {
      debugPrint('⚠️ Splash NetworkAuthException: $e');
      _handleNetworkError(prefs);
    } on TimeoutException {
      debugPrint('⚠️ Splash TimeoutException');
      _handleNetworkError(prefs);
    } catch (e) {
      debugPrint('⚠️ Splash error genérico: $e');
      _handleNetworkError(prefs);
    }
  }

  /// Maneja errores de red/timeout.
  /// Si el usuario estaba en demo o tenía sesión previa, lo deja entrar.
  void _handleNetworkError(SharedPreferences prefs) {
    if (!mounted) return;

    final isDemoMode = prefs.getBool('is_demo_mode') ?? false;
    final hadActiveSession = prefs.getBool('has_active_session') ?? false;

    if (isDemoMode || hadActiveSession) {
      // Demo mode o sesión previa → error de red, dejarlo pasar
      final profileSetupCompleted =
          prefs.getBool('profile_setup_completed') ?? false;
      context.go(profileSetupCompleted ? '/map' : '/profile-setup');
    } else {
      // Nunca tuvo sesión ni eligió demo → ir a login
      context.go('/login');
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFF0A1628),
              Color(0xFF0D47A1),
              Color(0xFF00BCD4),
            ],
          ),
        ),
        child: Center(
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              return FadeTransition(
                opacity: _fadeAnimation,
                child: ScaleTransition(
                  scale: _scaleAnimation,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // Logo/Icono del pez
                      Container(
                        width: 120,
                        height: 120,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: AppTheme.primaryGradient,
                          boxShadow: [
                            BoxShadow(
                              color: AppTheme.accentBlue.withOpacity(0.5),
                              blurRadius: 30,
                              spreadRadius: 5,
                            ),
                          ],
                        ),
                        child: const Icon(
                          Icons.phishing,
                          size: 60,
                          color: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 24),
                      // Nombre de la app
                      Text(
                        'FISHDEX',
                        style: Theme.of(context)
                            .textTheme
                            .displayLarge
                            ?.copyWith(
                              letterSpacing: 8,
                              shadows: [
                                Shadow(
                                  color: AppTheme.accentBlue.withOpacity(0.5),
                                  blurRadius: 20,
                                ),
                              ],
                            ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Identifica. Colecciona. Compite.',
                        style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                              color: Colors.white.withOpacity(0.7),
                              letterSpacing: 2,
                            ),
                      ),
                      const SizedBox(height: 48),
                      // Indicador de carga
                      SizedBox(
                        width: 40,
                        height: 40,
                        child: CircularProgressIndicator(
                          strokeWidth: 3,
                          valueColor: AlwaysStoppedAnimation<Color>(
                            Colors.white.withOpacity(0.7),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
