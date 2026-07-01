import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/services/identify_service.dart';
import '../../../data/models/identify_result.dart';
import 'result_screen.dart';

/// Pantalla de carga mientras se identifica el pez
/// Muestra animación tipo "escaneando" y luego navega al resultado
class IdentifyingScreen extends ConsumerStatefulWidget {
  final String videoPath;

  const IdentifyingScreen({super.key, required this.videoPath});

  @override
  ConsumerState<IdentifyingScreen> createState() => _IdentifyingScreenState();
}

class _IdentifyingScreenState extends ConsumerState<IdentifyingScreen>
    with TickerProviderStateMixin {
  late AnimationController _scanController;
  late AnimationController _pulseController;
  late Animation<double> _scanAnimation;
  late Animation<double> _pulseAnimation;

  String _statusText = 'Procesando video...';
  bool _hasError = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();

    // Animación de escaneo (línea que se mueve)
    _scanController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat();

    _scanAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _scanController, curve: Curves.easeInOut),
    );

    // Animación de pulso del icono
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.8, end: 1.2).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    // Iniciar la identificación
    _startIdentification();
  }

  Future<void> _startIdentification() async {
    try {
      // Simular pasos del proceso con delays para UX
      await Future.delayed(const Duration(milliseconds: 800));
      if (mounted) setState(() => _statusText = 'Extrayendo frames...');

      await Future.delayed(const Duration(milliseconds: 600));
      if (mounted) setState(() => _statusText = 'Analizando con IA...');

      // Llamar al servicio de identificación
      final service = IdentifyService();
      final result = await service.identifyFish(
        videoPath: widget.videoPath,
      );

      await Future.delayed(const Duration(milliseconds: 500));
      if (mounted) setState(() => _statusText = '¡Pez identificado!');

      await Future.delayed(const Duration(milliseconds: 400));

      // Navegar al resultado
      if (mounted) {
        Navigator.of(context).pushReplacement(
          PageRouteBuilder(
            pageBuilder: (context, animation, secondaryAnimation) {
              return ResultScreen(result: result);
            },
            transitionsBuilder: (context, animation, secondaryAnimation, child) {
              return FadeTransition(opacity: animation, child: child);
            },
            transitionDuration: const Duration(milliseconds: 500),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _hasError = true;
          _errorMessage = e is IdentifyException
              ? e.message
              : 'Error inesperado al identificar';
          _statusText = 'Error';
        });
      }
    }
  }

  @override
  void dispose() {
    _scanController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Icono animado de escaneo
              _buildScanIcon(),
              const SizedBox(height: 40),

              // Texto de estado
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 300),
                child: Text(
                  _statusText,
                  key: ValueKey(_statusText),
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        color: _hasError ? Colors.red : Colors.white,
                      ),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 16),

              // Barra de progreso o error
              if (!_hasError)
                const SizedBox(
                  width: 200,
                  child: LinearProgressIndicator(
                    backgroundColor: AppTheme.darkSurfaceElevated,
                    valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentBlue),
                  ),
                )
              else ...[
                const SizedBox(height: 8),
                Text(
                  _errorMessage ?? 'Error desconocido',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 14,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Volver a intentar'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildScanIcon() {
    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Transform.scale(
          scale: _pulseAnimation.value,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Círculo exterior con gradiente
              Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      AppTheme.accentBlue.withOpacity(0.3),
                      AppTheme.teal.withOpacity(0.3),
                    ],
                  ),
                  border: Border.all(
                    color: AppTheme.accentBlue.withOpacity(0.5),
                    width: 2,
                  ),
                ),
              ),

              // Línea de escaneo animada
              AnimatedBuilder(
                animation: _scanAnimation,
                builder: (context, child) {
                  return Positioned(
                    top: 20 + (_scanAnimation.value * 80),
                    child: Container(
                      width: 80,
                      height: 2,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [
                            Colors.transparent,
                            AppTheme.accentBlue,
                            Colors.transparent,
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),

              // Icono del pez
              Icon(
                _hasError ? Icons.error_outline : Icons.phishing,
                size: 48,
                color: _hasError ? Colors.red : AppTheme.accentBlue,
              ),
            ],
          ),
        );
      },
    );
  }
}
