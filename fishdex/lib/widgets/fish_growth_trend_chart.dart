import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';
import '../core/l10n/l10n_extension.dart';

class FishGrowthPoint {
  final DateTime date;
  final double sizeCm;
  final int index;

  const FishGrowthPoint({
    required this.date,
    required this.sizeCm,
    required this.index,
  });
}

class FishGrowthTrendCard extends StatelessWidget {
  final List<FishGrowthPoint> points;
  final String title;

  const FishGrowthTrendCard({
    super.key,
    required this.points,
    this.title = 'Growth trend',
  });

  String _two(int value) => value.toString().padLeft(2, '0');

  String _formatExactDate(DateTime date) {
    final local = date.toLocal();
    return '${_two(local.day)}/${_two(local.month)}/${local.year} '
        '${_two(local.hour)}:${_two(local.minute)}';
  }

  @override
  Widget build(BuildContext context) {
    final validPoints = points.where((p) => p.sizeCm > 0).toList()
      ..sort((a, b) => a.date.compareTo(b.date));

    if (validPoints.length < 2) {
      return const SizedBox.shrink();
    }

    final first = validPoints.first;
    final last = validPoints.last;
    final growth = last.sizeCm - first.sizeCm;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.teal.withOpacity(0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.show_chart, color: AppTheme.teal, size: 20),
              const SizedBox(width: 8),
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const Spacer(),
              Text(
                growth >= 0
                    ? '+${growth.toStringAsFixed(1)} cm'
                    : '${growth.toStringAsFixed(1)} cm',
                style: TextStyle(
                  color: growth >= 0 ? AppTheme.successGreen : Colors.orange,
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 140,
            child: CustomPaint(
              painter: _GrowthTrendPainter(validPoints),
              child: const SizedBox.expand(),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _metric('First', '${first.sizeCm.toStringAsFixed(1)} cm'),
              _metric('Latest', '${last.sizeCm.toStringAsFixed(1)} cm'),
              _metric('Sightings', '${validPoints.length}'),
            ],
          ),
          const SizedBox(height: 12),
          _buildExactDateLegend(context, validPoints),
          const SizedBox(height: 10),
          _buildGrowthIntervals(context, validPoints),
        ],
      ),
    );
  }

  Widget _metric(String label, String value) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 13,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.45),
            fontSize: 11,
          ),
        ),
      ],
    );
  }

  Widget _buildExactDateLegend(BuildContext context, List<FishGrowthPoint> points) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          context.l10n.chartExactDates,
          style: TextStyle(
            color: Colors.white.withOpacity(0.55),
            fontSize: 11,
            fontWeight: FontWeight.bold,
            letterSpacing: 0.6,
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: points.map((point) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: AppTheme.darkSurfaceElevated,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.white.withOpacity(0.08)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '#${point.index} · ${_formatExactDate(point.date)}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '${point.sizeCm.toStringAsFixed(1)} cm',
                    style: TextStyle(
                      color: AppTheme.teal.withOpacity(0.9),
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildGrowthIntervals(BuildContext context, List<FishGrowthPoint> points) {
    if (points.length < 2) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          context.l10n.chartGrowthByRecapture,
          style: TextStyle(
            color: Colors.white.withOpacity(0.55),
            fontSize: 11,
            fontWeight: FontWeight.bold,
            letterSpacing: 0.6,
          ),
        ),
        const SizedBox(height: 8),
        ...List.generate(points.length - 1, (i) {
          final previous = points[i];
          final current = points[i + 1];
          final growth = current.sizeCm - previous.sizeCm;
          final days = current.date.difference(previous.date).inDays;

          return Container(
            margin: const EdgeInsets.only(bottom: 6),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppTheme.darkSurfaceElevated,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              children: [
                Icon(
                  growth >= 0 ? Icons.trending_up : Icons.trending_down,
                  color: growth >= 0 ? AppTheme.successGreen : Colors.orange,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${_formatExactDate(previous.date)} → ${_formatExactDate(current.date)}'
                    '${days > 0 ? ' · $days días' : ''}',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.65),
                      fontSize: 11,
                    ),
                  ),
                ),
                Text(
                  growth >= 0
                      ? '+${growth.toStringAsFixed(1)} cm'
                      : '${growth.toStringAsFixed(1)} cm',
                  style: TextStyle(
                    color: growth >= 0 ? AppTheme.successGreen : Colors.orange,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }
}

class _GrowthTrendPainter extends CustomPainter {
  final List<FishGrowthPoint> points;

  _GrowthTrendPainter(this.points);

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;

    final minSize = points.map((p) => p.sizeCm).reduce((a, b) => a < b ? a : b);
    final maxSize = points.map((p) => p.sizeCm).reduce((a, b) => a > b ? a : b);

    final range = (maxSize - minSize).abs() < 0.1 ? 1.0 : maxSize - minSize;

    const leftPad = 28.0;
    const rightPad = 12.0;
    const topPad = 14.0;
    const bottomPad = 24.0;

    final chartW = size.width - leftPad - rightPad;
    final chartH = size.height - topPad - bottomPad;

    final gridPaint = Paint()
      ..color = Colors.white.withOpacity(0.08)
      ..strokeWidth = 1;

    final linePaint = Paint()
      ..color = AppTheme.teal
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final fillPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          AppTheme.teal.withOpacity(0.25),
          AppTheme.teal.withOpacity(0.02),
        ],
      ).createShader(Rect.fromLTWH(0, 0, size.width, size.height));

    Offset mapPoint(int i, FishGrowthPoint p) {
      final firstMs = points.first.date.millisecondsSinceEpoch.toDouble();
      final lastMs = points.last.date.millisecondsSinceEpoch.toDouble();
      final dateRange = lastMs - firstMs;
      final useDateSpacing = dateRange.abs() > 1000;

      final x = useDateSpacing
          ? leftPad +
              ((p.date.millisecondsSinceEpoch.toDouble() - firstMs) / dateRange) *
                  chartW
          : leftPad + (points.length == 1 ? 0 : i / (points.length - 1)) * chartW;

      final normalized = (p.sizeCm - minSize) / range;
      final y = topPad + (1 - normalized) * chartH;
      return Offset(x, y);
    }

    for (int i = 0; i < 4; i++) {
      final y = topPad + (chartH / 3) * i;
      canvas.drawLine(Offset(leftPad, y), Offset(size.width - rightPad, y), gridPaint);
    }

    final path = Path();
    final fillPath = Path();

    for (int i = 0; i < points.length; i++) {
      final offset = mapPoint(i, points[i]);
      if (i == 0) {
        path.moveTo(offset.dx, offset.dy);
        fillPath.moveTo(offset.dx, size.height - bottomPad);
        fillPath.lineTo(offset.dx, offset.dy);
      } else {
        path.lineTo(offset.dx, offset.dy);
        fillPath.lineTo(offset.dx, offset.dy);
      }
    }

    final last = mapPoint(points.length - 1, points.last);
    fillPath.lineTo(last.dx, size.height - bottomPad);
    fillPath.lineTo(last.dx, size.height - bottomPad);
    fillPath.close();

    canvas.drawPath(fillPath, fillPaint);
    canvas.drawPath(path, linePaint);

    final dotPaint = Paint()..color = AppTheme.teal;
    final dotBorder = Paint()..color = Colors.white;

    for (int i = 0; i < points.length; i++) {
      final offset = mapPoint(i, points[i]);
      canvas.drawCircle(offset, 5, dotBorder);
      canvas.drawCircle(offset, 3.5, dotPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _GrowthTrendPainter oldDelegate) {
    return oldDelegate.points != points;
  }
}
