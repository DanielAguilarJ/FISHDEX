import 'dart:math';
import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';

/// AR Overlay con silueta de pez para guiar al usuario a orientar correctamente el pez.
/// Similar a las apps de banco que muestran la silueta de una tarjeta/ID para verificación.
/// El usuario debe alinear el pez con la silueta para asegurar la mejor calidad de datos.
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
      duration: const Duration(milliseconds: 2500),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.7, end: 1.0).animate(
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
    final screenSize = MediaQuery.of(context).size;

    return Stack(
      children: [
        // Semi-transparent darkened area outside the fish silhouette
        Center(
          child: AnimatedBuilder(
            animation: _pulseAnimation,
            builder: (context, child) {
              return CustomPaint(
                size: Size(screenSize.width, screenSize.height),
                painter: FishSilhouettePainter(
                  progress: _pulseAnimation.value,
                  screenSize: screenSize,
                ),
              );
            },
          ),
        ),

        // Instruction text at top
        Positioned(
          top: screenSize.height * 0.12,
          left: 0,
          right: 0,
          child: _buildInstructionBanner(),
        ),

        // Orientation arrow indicators
        Center(
          child: SizedBox(
            width: screenSize.width * 0.85,
            height: screenSize.width * 0.45,
            child: _buildOrientationGuides(),
          ),
        ),

        // Help indicators at bottom
        Positioned(
          bottom: 160,
          left: 0,
          right: 0,
          child: _buildHelpIndicators(),
        ),
      ],
    );
  }

  Widget _buildInstructionBanner() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 32),
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.7),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: AppTheme.accentBlue.withOpacity(0.5),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            context.l10n.arAlignSilhouette,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            context.l10n.arHeadLeftBodyVisible,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 11,
              fontWeight: FontWeight.w400,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildOrientationGuides() {
    return Stack(
      children: [
        // Head indicator (left side)
        Positioned(
          left: 0,
          top: 0,
          bottom: 0,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.arrow_back, color: AppTheme.successGreen, size: 12),
                  const SizedBox(width: 2),
                  Text(
                    context.l10n.arHeadLabel,
                    style: const TextStyle(
                      color: AppTheme.successGreen,
                      fontSize: 9,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        // Tail indicator (right side)
        Positioned(
          right: 0,
          top: 0,
          bottom: 0,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    context.l10n.arTailLabel,
                    style: const TextStyle(
                      color: AppTheme.energyOrange,
                      fontSize: 9,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(width: 2),
                  const Icon(Icons.arrow_forward, color: AppTheme.energyOrange, size: 12),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHelpIndicators() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildIndicatorPill(
          Icons.rotate_90_degrees_ccw,
          context.l10n.arHorizontal,
          AppTheme.successGreen,
        ),
        const SizedBox(width: 10),
        _buildIndicatorPill(
          Icons.straighten,
          context.l10n.arDistance,
          AppTheme.energyOrange,
        ),
        const SizedBox(width: 10),
        _buildIndicatorPill(
          Icons.wb_sunny_outlined,
          context.l10n.arGoodLight,
          AppTheme.accentBlue,
        ),
      ],
    );
  }

  Widget _buildIndicatorPill(IconData icon, String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black54,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withOpacity(0.4), width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 13),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 10,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }
}

/// CustomPainter that draws a fish silhouette outline on the camera preview.
/// The area outside the fish is darkened to guide the user.
/// The fish outline pulses gently to attract attention.
class FishSilhouettePainter extends CustomPainter {
  final double progress;
  final Size screenSize;

  FishSilhouettePainter({required this.progress, required this.screenSize});

  @override
  void paint(Canvas canvas, Size size) {
    // Fish silhouette dimensions (centered on screen)
    final fishWidth = size.width * 0.75;
    final fishHeight = fishWidth * 0.38;
    final centerX = size.width / 2;
    final centerY = size.height / 2 - 20; // Slightly above center

    // Create fish body path
    final fishPath = _createFishPath(centerX, centerY, fishWidth, fishHeight);

    // Draw darkened overlay outside fish silhouette
    final overlayPaint = Paint()
      ..color = Colors.black.withOpacity(0.45)
      ..style = PaintingStyle.fill;

    // Full screen path minus fish cutout
    final fullPath = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height));
    final cutoutPath = Path.combine(PathOperation.difference, fullPath, fishPath);
    canvas.drawPath(cutoutPath, overlayPaint);

    // Draw fish outline (glowing, pulsing)
    final outlinePaint = Paint()
      ..color = AppTheme.accentBlue.withOpacity(0.4 + progress * 0.4)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    canvas.drawPath(fishPath, outlinePaint);

    // Draw subtle glow effect
    final glowPaint = Paint()
      ..color = AppTheme.accentBlue.withOpacity(0.1 + progress * 0.1)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6.0
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);

    canvas.drawPath(fishPath, glowPaint);

    // Draw dotted center line (lateral line of fish)
    _drawLateralLine(canvas, centerX, centerY, fishWidth);
  }

  /// Creates a realistic fish body silhouette path
  Path _createFishPath(double cx, double cy, double width, double height) {
    final path = Path();

    final left = cx - width / 2;
    final right = cx + width / 2;
    final top = cy - height / 2;
    final bottom = cy + height / 2;

    // Fish body using bezier curves for a natural shape
    // Starting from the mouth (left side, center)
    final mouthX = left + width * 0.02;
    final mouthY = cy;

    path.moveTo(mouthX, mouthY);

    // Upper jaw to head (going right and up)
    path.cubicTo(
      left + width * 0.08, cy - height * 0.15,
      left + width * 0.12, cy - height * 0.30,
      left + width * 0.18, cy - height * 0.38,
    );

    // Head to dorsal (top of head curving up)
    path.cubicTo(
      left + width * 0.24, cy - height * 0.46,
      left + width * 0.32, cy - height * 0.48,
      left + width * 0.40, cy - height * 0.47,
    );

    // Dorsal region (top of body, slight arch)
    path.cubicTo(
      left + width * 0.50, cy - height * 0.45,
      left + width * 0.60, cy - height * 0.42,
      left + width * 0.70, cy - height * 0.35,
    );

    // Dorsal to caudal peduncle (narrowing toward tail)
    path.cubicTo(
      left + width * 0.78, cy - height * 0.28,
      left + width * 0.84, cy - height * 0.20,
      left + width * 0.88, cy - height * 0.15,
    );

    // Caudal peduncle to tail fork (upper)
    path.cubicTo(
      left + width * 0.91, cy - height * 0.10,
      left + width * 0.93, cy - height * 0.08,
      left + width * 0.95, cy - height * 0.25,
    );

    // Tail fin upper tip
    path.cubicTo(
      left + width * 0.97, cy - height * 0.35,
      left + width * 0.99, cy - height * 0.38,
      right, cy - height * 0.30,
    );

    // Tail fin fork (V-shape back to center)
    path.cubicTo(
      left + width * 0.97, cy - height * 0.10,
      left + width * 0.96, cy,
      left + width * 0.97, cy + height * 0.10,
    );

    // Tail fin lower tip
    path.cubicTo(
      left + width * 0.99, cy + height * 0.38,
      left + width * 0.97, cy + height * 0.35,
      left + width * 0.95, cy + height * 0.25,
    );

    // Caudal peduncle lower
    path.cubicTo(
      left + width * 0.93, cy + height * 0.08,
      left + width * 0.91, cy + height * 0.10,
      left + width * 0.88, cy + height * 0.15,
    );

    // Lower body (belly, wider in middle)
    path.cubicTo(
      left + width * 0.84, cy + height * 0.22,
      left + width * 0.78, cy + height * 0.32,
      left + width * 0.70, cy + height * 0.38,
    );

    // Belly to ventral
    path.cubicTo(
      left + width * 0.60, cy + height * 0.44,
      left + width * 0.50, cy + height * 0.47,
      left + width * 0.40, cy + height * 0.48,
    );

    // Ventral to anal region
    path.cubicTo(
      left + width * 0.32, cy + height * 0.47,
      left + width * 0.24, cy + height * 0.44,
      left + width * 0.18, cy + height * 0.38,
    );

    // Lower head back to mouth
    path.cubicTo(
      left + width * 0.12, cy + height * 0.30,
      left + width * 0.08, cy + height * 0.15,
      mouthX, mouthY,
    );

    path.close();
    return path;
  }

  /// Draws a subtle dotted lateral line through the center of the fish
  void _drawLateralLine(Canvas canvas, double cx, double cy, double width) {
    final linePaint = Paint()
      ..color = Colors.white.withOpacity(0.2)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;

    final left = cx - width / 2;
    final dashWidth = 6.0;
    final dashGap = 4.0;
    var startX = left + width * 0.18;
    final endX = left + width * 0.85;

    while (startX < endX) {
      canvas.drawLine(
        Offset(startX, cy - 2),
        Offset(min(startX + dashWidth, endX), cy - 2),
        linePaint,
      );
      startX += dashWidth + dashGap;
    }

    // Eye indicator (small circle on the head)
    final eyePaint = Paint()
      ..color = Colors.white.withOpacity(0.3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    canvas.drawCircle(
      Offset(left + width * 0.12, cy - width * 0.04),
      width * 0.02,
      eyePaint,
    );
  }

  @override
  bool shouldRepaint(FishSilhouettePainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
