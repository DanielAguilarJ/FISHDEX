import 'dart:math';
import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';

/// Overlay de confeti que se muestra cuando se descubre un pez nuevo
/// Partículas animadas que caen desde arriba
class ConfettiOverlay extends StatefulWidget {
  const ConfettiOverlay({super.key});

  @override
  State<ConfettiOverlay> createState() => _ConfettiOverlayState();
}

class _ConfettiOverlayState extends State<ConfettiOverlay>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  final List<ConfettiParticle> _particles = [];
  final Random _random = Random();

  @override
  void initState() {
    super.initState();

    // Generar partículas
    for (int i = 0; i < 50; i++) {
      _particles.add(ConfettiParticle(
        x: _random.nextDouble(),
        y: -_random.nextDouble() * 0.3,
        speed: 0.3 + _random.nextDouble() * 0.7,
        size: 4 + _random.nextDouble() * 8,
        color: _getRandomColor(),
        rotation: _random.nextDouble() * pi * 2,
        rotationSpeed: (_random.nextDouble() - 0.5) * 0.1,
        horizontalDrift: (_random.nextDouble() - 0.5) * 0.02,
      ));
    }

    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..forward();

    _controller.addListener(() => setState(() {}));
  }

  Color _getRandomColor() {
    final colors = [
      AppTheme.gold,
      AppTheme.accentBlue,
      AppTheme.successGreen,
      AppTheme.energyOrange,
      AppTheme.legendaryPurple,
      AppTheme.rareRed,
      Colors.white,
    ];
    return colors[_random.nextInt(colors.length)];
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_controller.isAnimating && _controller.isCompleted) {
      return const SizedBox.shrink();
    }

    return IgnorePointer(
      child: CustomPaint(
        size: MediaQuery.of(context).size,
        painter: ConfettiPainter(
          particles: _particles,
          progress: _controller.value,
        ),
      ),
    );
  }
}

class ConfettiParticle {
  double x;
  double y;
  final double speed;
  final double size;
  final Color color;
  double rotation;
  final double rotationSpeed;
  final double horizontalDrift;

  ConfettiParticle({
    required this.x,
    required this.y,
    required this.speed,
    required this.size,
    required this.color,
    required this.rotation,
    required this.rotationSpeed,
    required this.horizontalDrift,
  });
}

class ConfettiPainter extends CustomPainter {
  final List<ConfettiParticle> particles;
  final double progress;

  ConfettiPainter({required this.particles, required this.progress});

  @override
  void paint(Canvas canvas, Size size) {
    for (final particle in particles) {
      // Calcular posición actual
      final currentY = particle.y + (progress * particle.speed * 1.5);
      final currentX = particle.x + (sin(progress * 10 + particle.rotation) * 0.03);

      // Solo dibujar si está visible
      if (currentY > 1.2) continue;

      final paint = Paint()
        ..color = particle.color.withOpacity(1.0 - progress * 0.8)
        ..style = PaintingStyle.fill;

      final px = currentX * size.width;
      final py = currentY * size.height;

      canvas.save();
      canvas.translate(px, py);
      canvas.rotate(particle.rotation + progress * particle.rotationSpeed * 20);

      // Dibujar rectángulo rotado (confeti)
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(
            center: Offset.zero,
            width: particle.size,
            height: particle.size * 0.6,
          ),
          const Radius.circular(1),
        ),
        paint,
      );

      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(ConfettiPainter oldDelegate) => true;
}
