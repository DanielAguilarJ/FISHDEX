import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/services/identify_service.dart';
import '../../auth/providers/auth_provider.dart';
import '../../camera/providers/capture_metadata_provider.dart';
import '../../map/providers/map_providers.dart';
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

  String _statusText = '';
  bool _statusInitialized = false;
  bool _hasError = false;
  String? _errorMessage;
  Timer? _safetyTimer;

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

    // Iniciar la identificación después de que el contexto esté listo
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _startIdentification();
    });

    // Timer de seguridad: si después de 100s no hay respuesta,
    // mostrar error para que el usuario no se quede atrapado
    _safetyTimer = Timer(const Duration(seconds: 100), () {
      if (mounted && !_hasError) {
        setState(() {
          _hasError = true;
          _errorMessage = 'La identificación tardó demasiado. '
              'Verifica que el servidor esté activo e inténtalo de nuevo.';
          _statusText = context.l10n.identifyingError;
        });
      }
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_statusInitialized) {
      _statusInitialized = true;
      _statusText = context.l10n.identifyingProcessing;
    }
  }

  Future<void> _startIdentification() async {
    if (!mounted) return;
    final l10n = context.l10n;
    try {
      debugPrint('[IdentifyingScreen] Starting identification...');
      // Simular pasos del proceso con delays para UX
      await Future.delayed(const Duration(milliseconds: 800));
      if (mounted) setState(() => _statusText = l10n.identifyingExtractingFrames);

      await Future.delayed(const Duration(milliseconds: 600));
      if (mounted) setState(() => _statusText = l10n.identifyingAnalyzing);

      debugPrint('[IdentifyingScreen] Sending video to server...');

      // Llamar al servicio de identificación con userId y ubicación GPS
      final service = IdentifyService();
      final authUser = ref.read(authStateProvider).valueOrNull;
      final location = ref.read(userLocationProvider).valueOrNull;
      final metadata = ref.read(captureMetadataProvider);
      final result = await service.identifyFish(
        videoPath: widget.videoPath,
        areaCode: metadata.areaCode ?? '401 001',
        fishermanId: authUser?.$id ?? 'anonymous',
        userRole: 'fisherman',
        species: metadata.species,
        fishState: metadata.fishState,
        name: metadata.customName,
        weather: metadata.weather,
        bite: metadata.bite,
        size: metadata.size,
        userId: authUser?.$id,
        latitude: location?.latitude,
        longitude: location?.longitude,
      );

      debugPrint('[IdentifyingScreen] Server response received!');
      await Future.delayed(const Duration(milliseconds: 500));
      if (mounted) setState(() => _statusText = l10n.identifyingSuccess);

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
      debugPrint('[IdentifyingScreen] Error: $e');
      _safetyTimer?.cancel();
      if (mounted) {
        setState(() {
          _hasError = true;
          _errorMessage = e is IdentifyException
              ? '${e.message}${e.detail != null ? '\n\n${e.detail}' : ''}'
              : l10n.identifyingUnexpectedError;
          _statusText = l10n.identifyingError;
        });
      }
    }
  }

  @override
  void dispose() {
    _safetyTimer?.cancel();
    _scanController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: SafeArea(
        child: Stack(
          children: [
            // Botón de volver/cancelar (siempre visible)
            Positioned(
              top: 16,
              left: 16,
              child: GestureDetector(
                onTap: () => Navigator.of(context).pop(),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.white.withOpacity(0.1),
                  ),
                  child: const Icon(Icons.arrow_back, color: Colors.white70),
                ),
              ),
            ),
            // Contenido principal
            Center(
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
                        _errorMessage ?? context.l10n.identifyingUnexpectedError,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.6),
                          fontSize: 14,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 24),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          OutlinedButton(
                            onPressed: () => Navigator.of(context).pop(),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: Colors.white70,
                              side: const BorderSide(color: Colors.white24),
                            ),
                            child: Text(context.l10n.videoPreviewRetake),
                          ),
                          const SizedBox(width: 12),
                          ElevatedButton.icon(
                            onPressed: () {
                              setState(() {
                                _hasError = false;
                                _errorMessage = null;
                                _statusText = context.l10n.identifyingProcessing;
                              });
                              _safetyTimer?.cancel();
                              _safetyTimer = Timer(const Duration(seconds: 100), () {
                                if (mounted && !_hasError) {
                                  setState(() {
                                    _hasError = true;
                                    _errorMessage = 'La identificación tardó demasiado.';
                                    _statusText = context.l10n.identifyingError;
                                  });
                                }
                              });
                              _startIdentification();
                            },
                            icon: const Icon(Icons.refresh, size: 18),
                            label: Text(context.l10n.identifyingRetry),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.accentBlue,
                              foregroundColor: Colors.white,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
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
                      decoration: const BoxDecoration(
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
