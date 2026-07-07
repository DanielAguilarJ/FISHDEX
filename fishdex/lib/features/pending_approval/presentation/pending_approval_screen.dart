import 'dart:async';
import 'package:appwrite/appwrite.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';

/// Pantalla que se muestra cuando un researcher está esperando
/// la aprobación del administrador.
/// Escucha cambios en tiempo real en su documento de usuario.
class PendingApprovalScreen extends ConsumerStatefulWidget {
  const PendingApprovalScreen({super.key});

  @override
  ConsumerState<PendingApprovalScreen> createState() =>
      _PendingApprovalScreenState();
}

class _PendingApprovalScreenState
    extends ConsumerState<PendingApprovalScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;
  RealtimeSubscription? _subscription;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.8, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    // Iniciar escucha de cambios Realtime
    _subscribeToApprovalChanges();
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _subscription?.close();
    super.dispose();
  }

  /// Suscribirse a cambios en el documento del usuario actual
  Future<void> _subscribeToApprovalChanges() async {
    try {
      final account = ref.read(appwriteAccountProvider);
      final user = await account.get();
      final realtime = ref.read(appwriteRealtimeProvider);

      final channel =
          'databases.${AppConstants.databaseId}.collections.${AppConstants.usersCollection}.documents.${user.$id}';

      _subscription = realtime.subscribe([channel]);
      _subscription!.stream.listen((event) {
        final data = event.payload;
        final status = data['approval_status'] as String?;

        if (status == 'approved' && mounted) {
          // Aprobado - navegar al setup de perfil
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Tu cuenta ha sido aprobada!'),
              backgroundColor: Colors.green,
            ),
          );
          context.go('/profile-setup');
        } else if (status == 'rejected' && mounted) {
          // Rechazado - mostrar mensaje
          setState(() {});
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                  'Tu solicitud ha sido rechazada. Contacta al administrador.'),
              backgroundColor: Colors.red,
            ),
          );
        }
      });
    } catch (e) {
      debugPrint('⚠️ Error al suscribirse a cambios de aprobación: $e');
    }
  }

  Future<void> _logout() async {
    try {
      final account = ref.read(appwriteAccountProvider);
      await account.deleteSession(sessionId: 'current');
    } catch (_) {}
    if (mounted) {
      context.go('/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Spacer(flex: 2),

              // Ícono animado de espera
              AnimatedBuilder(
                animation: _pulseAnimation,
                builder: (context, child) {
                  return Transform.scale(
                    scale: _pulseAnimation.value,
                    child: Container(
                      width: 140,
                      height: 140,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: AppTheme.legendaryGradient,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.purple.withOpacity(0.3),
                            blurRadius: 30,
                            spreadRadius: 5,
                          ),
                        ],
                      ),
                      child: const Icon(
                        Icons.hourglass_top_rounded,
                        size: 64,
                        color: Colors.white,
                      ),
                    ),
                  );
                },
              ),

              const SizedBox(height: 48),

              // Título
              Text(
                'Solicitud Enviada',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                    ),
                textAlign: TextAlign.center,
              ),

              const SizedBox(height: 16),

              // Descripción
              Text(
                'Tu solicitud como investigador está siendo revisada '
                'por un administrador.',
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                      color: Colors.white.withOpacity(0.7),
                      height: 1.5,
                    ),
                textAlign: TextAlign.center,
              ),

              const SizedBox(height: 12),

              Text(
                'Te notificaremos automáticamente cuando sea aprobada. '
                'No necesitas cerrar la app.',
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.white.withOpacity(0.5),
                      height: 1.4,
                    ),
                textAlign: TextAlign.center,
              ),

              const SizedBox(height: 40),

              // Indicador de estado
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 12,
                ),
                decoration: BoxDecoration(
                  color: Colors.orange.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: Colors.orange.withOpacity(0.3),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        color: Colors.orange,
                      ),
                    ),
                    const SizedBox(width: 10),
                    const Text(
                      'Pendiente de aprobación',
                      style: TextStyle(
                        color: Colors.orange,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),

              const Spacer(flex: 3),

              // Botón de cerrar sesión
              TextButton.icon(
                onPressed: _logout,
                icon: Icon(
                  Icons.logout,
                  color: Colors.white.withOpacity(0.5),
                ),
                label: Text(
                  'Cerrar sesión',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                  ),
                ),
              ),

              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}
