import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/presentation/register_screen.dart';
import '../../features/auth/presentation/splash_screen.dart';
import '../../features/auth/providers/auth_provider.dart';
import '../shell/main_shell.dart';
import '../../features/map/presentation/map_screen.dart';
import '../../features/camera/presentation/camera_screen.dart';
import '../../features/collection/presentation/collection_screen.dart';
import '../../features/ranking/presentation/ranking_screen.dart';
import '../../features/profile/presentation/profile_screen.dart';

/// Provider del router de la aplicación
final appRouterProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authStateProvider);

  return GoRouter(
    initialLocation: '/splash',
    debugLogDiagnostics: true,
    
    // Redirigir según estado de autenticación
    // NOTA: Desactivado temporalmente para permitir modo demo sin backend
    redirect: (context, state) {
      // Permitir navegación libre en modo demo
      return null;
    },

    routes: [
      // =====================================================================
      // RUTAS DE AUTENTICACIÓN
      // =====================================================================
      GoRoute(
        path: '/splash',
        name: 'splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/register',
        name: 'register',
        builder: (context, state) => const RegisterScreen(),
      ),

      // =====================================================================
      // RUTAS PRINCIPALES (con bottom navigation)
      // =====================================================================
      ShellRoute(
        builder: (context, state, child) => MainShell(child: child),
        routes: [
          GoRoute(
            path: '/map',
            name: 'map',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: MapScreen(),
            ),
          ),
          GoRoute(
            path: '/camera',
            name: 'camera',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: CameraScreen(),
            ),
          ),
          GoRoute(
            path: '/collection',
            name: 'collection',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: CollectionScreen(),
            ),
          ),
          GoRoute(
            path: '/ranking',
            name: 'ranking',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: RankingScreen(),
            ),
          ),
          GoRoute(
            path: '/profile',
            name: 'profile',
            pageBuilder: (context, state) => const NoTransitionPage(
              child: ProfileScreen(),
            ),
          ),
        ],
      ),
    ],
  );
});
