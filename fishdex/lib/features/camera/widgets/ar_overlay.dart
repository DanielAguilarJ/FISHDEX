import 'dart:math';
import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';

/// AR Overlay con guías visuales para ayudar al usuario a encuadrar el pez
/// Muestra un marco animado, indicadores de distancia e instrucciones
class AROverlay extends StatefulWidget {
  const AROverlay({super.key});

  @override
  State<AROverlay> createState() => _AROverlayState();
}

class _AROverlayState extends State<AROverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.8, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        // Marco guía para encuadrar al pez
        Center(
          child: AnimatedBuilder(
            animation: _pulseAnimation,
            builder: (context, child) {
              return CustomPaint(
                size: Size(
                  MediaQuery.of(context).size.width * 0.8,
                  MediaQuery.of(context).size.width * 0.5,
                ),
                painter: FishFramePainter(
                  progress: _pulseAnimation.value,
                ),
              );
            },
          ),
        ),

        // Texto de instrucciones (parte superior del marco)
        Positioned(
          top: MediaQuery.of(context).size.height * 0.25,
          left: 0,
          right: 0,
          child: _buildInstructionText(),
        ),

        // Indicadores de ayuda (parte inferior)
        Positioned(
          bottom: 160,
          left: 0,
          right: 0,
          child: _buildHelpIndicators(),
        ),

        // Indicador de distancia óptima
        Positioned(
          right: 20,
          top: MediaQuery.of(context).size.height * 0.4,
          child: _buildDistanceIndicator(),
        ),
      ],
    );
  }

  Widget _buildInstructionText() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 40),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Text(
        'Mantén al pez dentro del marco',
        textAlign: TextAlign.center,
        style: TextStyle(
          color: Colors.white,
          fontSize: 14,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildHelpIndicators() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildIndicatorPill(
          Icons.wb_sunny_outlined,
          'Iluminación',
          AppTheme.successGreen,
          'Buena',
        ),
        const SizedBox(width: 12),
        _buildIndicatorPill(
          Icons.straighten,
          'Distancia',
          AppTheme.energyOrange,
          '30-50cm',
        ),
        const SizedBox(width: 12),
        _buildIndicatorPill(
          Icons.center_focus_strong,
          'Enfoque',
          AppTheme.accentBlue,
          'Auto',
        ),
      ],
    );
  }

  Widget _buildIndicatorPill(
    IconData icon,
    String label,
    Color color,
    String value,
  ) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withOpacity(0.5), width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 14),
          const SizedBox(width: 4),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDistanceIndicator() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.zoom_out, color: Colors.white54, size: 16),
          const SizedBox(height: 4),
          Container(
            width: 3,
            height: 60,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(2),
              gradient: const LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.red,
                  AppTheme.energyOrange,
                  AppTheme.successGreen,
                  AppTheme.energyOrange,
                  Colors.red,
                ],
              ),
            ),
          ),
          // Indicador de posición actual (simulado en el centro = óptimo)
          Transform.translate(
            offset: const Offset(0, -30),
            child: Container(
              width: 12,
              height: 3,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 4),
          const Icon(Icons.zoom_in, color: Colors.white54, size: 16),
        ],
      ),
    );
  }
}

/// CustomPainter que dibuja el marco guía en forma de pez
/// con esquinas redondeadas y animación de pulso
class FishFramePainter extends CustomPainter {
  final double progress;

  FishFramePainter({required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppTheme.accentBlue.withOpacity(0.6 + (progress - 0.8) * 2)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    final cornerLength = size.width * 0.08;
    final radius = 12.0;

    // Esquina superior izquierda
    _drawCorner(canvas, paint, Offset.zero, cornerLength, radius,
        topLeft: true);

    // Esquina superior derecha
    _drawCorner(canvas, paint, Offset(size.width, 0), cornerLength, radius,
        topRight: true);

    // Esquina inferior izquierda
    _drawCorner(canvas, paint, Offset(0, size.height), cornerLength, radius,
        bottomLeft: true);

    // Esquina inferior derecha
    _drawCorner(
        canvas, paint, Offset(size.width, size.height), cornerLength, radius,
        bottomRight: true);

    // Líneas de centro (crosshair sutil)
    final centerPaint = Paint()
      ..color = Colors.white.withOpacity(0.2)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    // Línea horizontal central
    canvas.drawLine(
      Offset(size.width * 0.4, size.height / 2),
      Offset(size.width * 0.6, size.height / 2),
      centerPaint,
    );

    // Línea vertical central
    canvas.drawLine(
      Offset(size.width / 2, size.height * 0.4),
      Offset(size.width / 2, size.height * 0.6),
      centerPaint,
    );
  }

  void _drawCorner(
    Canvas canvas,
    Paint paint,
    Offset position,
    double length,
    double radius, {
    bool topLeft = false,
    bool topRight = false,
    bool bottomLeft = false,
    bool bottomRight = false,
  }) {
    final path = Path();

    if (topLeft) {
      path.moveTo(position.dx, position.dy + length);
      path.lineTo(position.dx, position.dy + radius);
      path.arcToPoint(
        Offset(position.dx + radius, position.dy),
        radius: Radius.circular(radius),
      );
      path.lineTo(position.dx + length, position.dy);
    } else if (topRight) {
      path.moveTo(position.dx - length, position.dy);
      path.lineTo(position.dx - radius, position.dy);
      path.arcToPoint(
        Offset(position.dx, position.dy + radius),
        radius: Radius.circular(radius),
      );
      path.lineTo(position.dx, position.dy + length);
    } else if (bottomLeft) {
      path.moveTo(position.dx, position.dy - length);
      path.lineTo(position.dx, position.dy - radius);
      path.arcToPoint(
        Offset(position.dx + radius, position.dy),
        radius: Radius.circular(radius),
      );
      path.lineTo(position.dx + length, position.dy);
    } else if (bottomRight) {
      path.moveTo(position.dx - length, position.dy);
      path.lineTo(position.dx - radius, position.dy);
      path.arcToPoint(
        Offset(position.dx, position.dy - radius),
        radius: Radius.circular(radius),
      );
      path.lineTo(position.dx, position.dy - length);
    }

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(FishFramePainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
