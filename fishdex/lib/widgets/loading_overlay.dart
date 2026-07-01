import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// Overlay de carga con fondo semitransparente
/// Muestra un indicador de carga, mensaje y opcionalmente progreso
/// Incluye un icono de pez animado con pulso
class LoadingOverlay extends StatefulWidget {
  /// Mensaje que se muestra debajo del indicador
  final String message;

  /// Progreso opcional (0.0 a 1.0), si es null muestra spinner indeterminado
  final double? progress;

  /// Si el overlay es visible
  final bool isVisible;

  const LoadingOverlay({
    super.key,
    this.message = 'Cargando...',
    this.progress,
    this.isVisible = true,
  });

  @override
  State<LoadingOverlay> createState() => _LoadingOverlayState();
}

class _LoadingOverlayState extends State<LoadingOverlay>
    with SingleTickerProviderStateMixin {
  /// Controlador para la animación de pulso del pez
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.8, end: 1.2).animate(
      CurvedAnimation(
        parent: _pulseController,
        curve: Curves.easeInOut,
      ),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isVisible) return const SizedBox.shrink();

    return Container(
      color: Colors.black.withOpacity(0.7),
      width: double.infinity,
      height: double.infinity,
      child: Center(
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 40),
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 40),
          decoration: BoxDecoration(
            color: AppTheme.darkSurface,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: AppTheme.accentBlue.withOpacity(0.3),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: AppTheme.accentBlue.withOpacity(0.15),
                blurRadius: 30,
                spreadRadius: 5,
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Icono de pez animado con pulso
              _buildPulsingFishIcon(),

              const SizedBox(height: 24),

              // Indicador de progreso
              _buildProgressIndicator(),

              const SizedBox(height: 20),

              // Mensaje de carga
              Text(
                widget.message,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                ),
                textAlign: TextAlign.center,
              ),

              // Porcentaje de progreso (si aplica)
              if (widget.progress != null) ...[
                const SizedBox(height: 8),
                Text(
                  '${(widget.progress! * 100).toInt()}%',
                  style: TextStyle(
                    color: AppTheme.accentBlue.withOpacity(0.8),
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  /// Icono de pez con animación de pulso
  Widget _buildPulsingFishIcon() {
    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Transform.scale(
          scale: _pulseAnimation.value,
          child: Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppTheme.accentBlue.withOpacity(0.1),
              border: Border.all(
                color: AppTheme.accentBlue.withOpacity(0.4),
                width: 2,
              ),
            ),
            child: const Icon(
              Icons.phishing,
              size: 32,
              color: AppTheme.accentBlue,
            ),
          ),
        );
      },
    );
  }

  /// Indicador de progreso (determinado o indeterminado)
  Widget _buildProgressIndicator() {
    if (widget.progress != null) {
      // Barra de progreso determinada
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: LinearProgressIndicator(
          value: widget.progress,
          minHeight: 6,
          backgroundColor: Colors.white.withOpacity(0.1),
          valueColor: const AlwaysStoppedAnimation<Color>(AppTheme.accentBlue),
        ),
      );
    } else {
      // Spinner circular indeterminado
      return const SizedBox(
        width: 40,
        height: 40,
        child: CircularProgressIndicator(
          strokeWidth: 3,
          valueColor: AlwaysStoppedAnimation<Color>(AppTheme.accentBlue),
        ),
      );
    }
  }
}
