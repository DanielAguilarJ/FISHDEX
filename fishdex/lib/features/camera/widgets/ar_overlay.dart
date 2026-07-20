import 'dart:math';
import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';

/// AR Overlay con silueta de pez rotada para guiar al usuario.
/// El pez apunta hacia arriba (hacia la cámara selfie).
/// El teléfono se mantiene en portrait — solo la silueta está rotada.
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
        // Fish silhouette rotated 90° CCW — head points UP (toward selfie camera)
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
          top: screenSize.height * 0.06,
          left: 0,
          right: 0,
          child: _buildInstructionBanner(),
        ),

        // Head indicator (top — toward selfie camera)
        Positioned(
          top: screenSize.height * 0.18,
          left: 0,
          right: 0,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.arrow_upward, color: AppTheme.successGreen, size: 14),
                  const SizedBox(height: 2),
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

        // Tail indicator (bottom)
        Positioned(
          bottom: screenSize.height * 0.22,
          left: 0,
          right: 0,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
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
                  const SizedBox(height: 2),
                  const Icon(Icons.arrow_downward, color: AppTheme.energyOrange, size: 14),
                ],
              ),
            ),
          ),
        ),

        // Help indicators at bottom
        Positioned(
          bottom: 100,
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

  Widget _buildHelpIndicators() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
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

/// CustomPainter that draws a fish silhouette rotated 90° CCW.
/// The fish head points UP (toward selfie camera), tail points DOWN.
/// The phone stays in portrait — only the drawing is rotated.
class FishSilhouettePainter extends CustomPainter {
  final double progress;
  final Size screenSize;

  FishSilhouettePainter({required this.progress, required this.screenSize});

  @override
  void paint(Canvas canvas, Size size) {
    final centerX = size.width / 2;
    final centerY = size.height / 2 - 20;

    // Fish dimensions — use height as the long axis since fish is vertical
    final fishLength = size.height * 0.55; // Long axis (head-to-tail)
    final fishWidth = fishLength * 0.38; // Short axis (body width)

    // Create fish path (drawn horizontally, then rotated)
    final fishPath = _createRotatedFishPath(centerX, centerY, fishLength, fishWidth);

    // Draw darkened overlay outside fish silhouette
    final overlayPaint = Paint()
      ..color = Colors.black.withOpacity(0.45)
      ..style = PaintingStyle.fill;

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

    // Draw lateral line (vertical now) and eye
    _drawLateralLineAndEye(canvas, centerX, centerY, fishLength, fishWidth);
  }

  /// Creates a fish path rotated 90° counterclockwise.
  /// Head points UP, tail points DOWN.
  Path _createRotatedFishPath(double cx, double cy, double length, double width) {
    final path = Path();

    // The fish is drawn vertically:
    // - "length" runs along Y axis (top to bottom)
    // - "width" runs along X axis (left to right)
    // Head is at top (cy - length/2), tail at bottom (cy + length/2)

    final top = cy - length / 2; // Head end
    final bottom = cy + length / 2; // Tail end

    // Mouth (top center)
    final mouthX = cx;
    final mouthY = top + length * 0.02;

    path.moveTo(mouthX, mouthY);

    // Upper jaw to head — curving RIGHT and DOWN
    path.cubicTo(
      cx + width * 0.15, top + length * 0.08,
      cx + width * 0.30, top + length * 0.12,
      cx + width * 0.38, top + length * 0.18,
    );

    // Head to dorsal (right side of body)
    path.cubicTo(
      cx + width * 0.46, top + length * 0.24,
      cx + width * 0.48, top + length * 0.32,
      cx + width * 0.47, top + length * 0.40,
    );

    // Dorsal region (right side, widest part)
    path.cubicTo(
      cx + width * 0.45, top + length * 0.50,
      cx + width * 0.42, top + length * 0.60,
      cx + width * 0.35, top + length * 0.70,
    );

    // Narrowing toward caudal peduncle (right side)
    path.cubicTo(
      cx + width * 0.28, top + length * 0.78,
      cx + width * 0.20, top + length * 0.84,
      cx + width * 0.15, top + length * 0.88,
    );

    // Caudal peduncle to tail fork (right upper lobe)
    path.cubicTo(
      cx + width * 0.10, top + length * 0.91,
      cx + width * 0.08, top + length * 0.93,
      cx + width * 0.25, top + length * 0.95,
    );

    // Tail fin right tip
    path.cubicTo(
      cx + width * 0.35, top + length * 0.97,
      cx + width * 0.38, top + length * 0.99,
      cx + width * 0.30, bottom,
    );

    // Tail fin fork (V back to center)
    path.cubicTo(
      cx + width * 0.10, top + length * 0.97,
      cx, top + length * 0.96,
      cx - width * 0.10, top + length * 0.97,
    );

    // Tail fin left tip
    path.cubicTo(
      cx - width * 0.38, top + length * 0.99,
      cx - width * 0.35, top + length * 0.97,
      cx - width * 0.25, top + length * 0.95,
    );

    // Caudal peduncle (left side going up)
    path.cubicTo(
      cx - width * 0.08, top + length * 0.93,
      cx - width * 0.10, top + length * 0.91,
      cx - width * 0.15, top + length * 0.88,
    );

    // Lower body left side (belly)
    path.cubicTo(
      cx - width * 0.22, top + length * 0.84,
      cx - width * 0.32, top + length * 0.78,
      cx - width * 0.38, top + length * 0.70,
    );

    // Belly widest
    path.cubicTo(
      cx - width * 0.44, top + length * 0.60,
      cx - width * 0.47, top + length * 0.50,
      cx - width * 0.48, top + length * 0.40,
    );

    // Ventral to head (left side)
    path.cubicTo(
      cx - width * 0.47, top + length * 0.32,
      cx - width * 0.44, top + length * 0.24,
      cx - width * 0.38, top + length * 0.18,
    );

    // Lower jaw back to mouth
    path.cubicTo(
      cx - width * 0.30, top + length * 0.12,
      cx - width * 0.15, top + length * 0.08,
      mouthX, mouthY,
    );

    path.close();
    return path;
  }

  /// Draws a vertical lateral line and eye indicator
  void _drawLateralLineAndEye(
    Canvas canvas, double cx, double cy, double length, double width,
  ) {
    final linePaint = Paint()
      ..color = Colors.white.withOpacity(0.2)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;

    final top = cy - length / 2;
    const dashLen = 6.0;
    const dashGap = 4.0;

    // Lateral line runs vertically from near head to near tail
    var startY = top + length * 0.18;
    final endY = top + length * 0.85;

    while (startY < endY) {
      canvas.drawLine(
        Offset(cx + 2, startY),
        Offset(cx + 2, min(startY + dashLen, endY)),
        linePaint,
      );
      startY += dashLen + dashGap;
    }

    // Eye (near head, slightly offset)
    final eyePaint = Paint()
      ..color = Colors.white.withOpacity(0.3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    canvas.drawCircle(
      Offset(cx + length * 0.04, top + length * 0.12),
      length * 0.02,
      eyePaint,
    );
  }

  @override
  bool shouldRepaint(FishSilhouettePainter oldDelegate) {
    return oldDelegate.progress != progress;
  }
}
