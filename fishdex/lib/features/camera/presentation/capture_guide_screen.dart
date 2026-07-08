import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';

/// Tutorial screen shown before first capture to teach users how to properly
/// record a fish video. Similar to "Intro Captura" from the technical spec.
/// Shows proper fish orientation, distance, and technique with visual examples.
class CaptureGuideScreen extends StatefulWidget {
  final VoidCallback onContinue;

  const CaptureGuideScreen({super.key, required this.onContinue});

  @override
  State<CaptureGuideScreen> createState() => _CaptureGuideScreenState();
}

class _CaptureGuideScreenState extends State<CaptureGuideScreen> {
  final PageController _pageController = PageController();
  int _currentPage = 0;
  static const int _totalPages = 4;

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: SafeArea(
        child: Column(
          children: [
            // Skip button
            Align(
              alignment: Alignment.topRight,
              child: TextButton(
                onPressed: widget.onContinue,
                child: const Text(
                  'Skip',
                  style: TextStyle(color: Colors.white54, fontSize: 14),
                ),
              ),
            ),
            // Page content
            Expanded(
              child: PageView(
                controller: _pageController,
                onPageChanged: (i) => setState(() => _currentPage = i),
                children: [
                  _buildPage1Orientation(),
                  _buildPage2Position(),
                  _buildPage3Technique(),
                  _buildPage4Ready(),
                ],
              ),
            ),
            // Page indicators + button
            _buildBottomControls(),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  /// Page 1: Fish orientation - head to the left
  Widget _buildPage1Orientation() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Fish silhouette with arrow showing correct orientation
          Container(
            width: 280,
            height: 160,
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: AppTheme.accentBlue.withOpacity(0.3),
              ),
            ),
            child: CustomPaint(
              painter: _OrientationGuidePainter(),
            ),
          ),
          const SizedBox(height: 32),
          const Text(
            'Correct Orientation',
            style: TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Always position the fish with the HEAD pointing LEFT '
            'and the TAIL pointing RIGHT. This ensures consistent '
            'identification across all catches.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 14,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 20),
          _buildTipChip(
            Icons.lightbulb_outline,
            'Same orientation = better matching accuracy',
          ),
        ],
      ),
    );
  }

  /// Page 2: Position and distance
  Widget _buildPage2Position() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Visual showing full body with margins
          Container(
            width: 280,
            height: 160,
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: AppTheme.successGreen.withOpacity(0.3),
              ),
            ),
            child: CustomPaint(
              painter: _PositionGuidePainter(),
            ),
          ),
          const SizedBox(height: 32),
          const Text(
            'Full Body Visible',
            style: TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Make sure the ENTIRE fish body is visible in the frame, '
            'from mouth to tail. Leave small margins on all sides. '
            'Distance: 30-50 cm from the fish.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 14,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 20),
          _buildTipChip(
            Icons.crop_free,
            'Full body = patterns can be analyzed correctly',
          ),
        ],
      ),
    );
  }

  /// Page 3: Recording technique
  Widget _buildPage3Technique() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Checkmarks and X marks
          Container(
            width: 280,
            height: 200,
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(20),
            ),
            padding: const EdgeInsets.all(20),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _buildDoItem(true, 'Lay fish flat on measuring mat'),
                _buildDoItem(true, 'Use good natural light'),
                _buildDoItem(true, 'Record 5-10 seconds steadily'),
                _buildDoItem(false, 'Hold fish with hands covering body'),
                _buildDoItem(false, 'Record in very dark conditions'),
              ],
            ),
          ),
          const SizedBox(height: 32),
          const Text(
            'Recording Tips',
            style: TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'Place the fish on a flat surface (measuring mat is ideal). '
            'Minimize hand coverage. A steady 5-10 second video is perfect.',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 14,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  /// Page 4: Ready to start
  Widget _buildPage4Ready() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                colors: [
                  AppTheme.accentBlue.withOpacity(0.3),
                  AppTheme.successGreen.withOpacity(0.3),
                ],
              ),
            ),
            child: const Icon(
              Icons.videocam_rounded,
              color: Colors.white,
              size: 56,
            ),
          ),
          const SizedBox(height: 32),
          const Text(
            'Ready to Capture!',
            style: TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'The camera will show a fish silhouette guide. '
            'Align the fish with the outline and press the record button. '
            'The AI will identify your catch!',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 14,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 30),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              children: [
                const Icon(Icons.info_outline, color: AppTheme.accentBlue, size: 20),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'You can always access this guide from the camera settings.',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.6),
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDoItem(bool isDo, String text) {
    return Row(
      children: [
        Icon(
          isDo ? Icons.check_circle : Icons.cancel,
          color: isDo ? AppTheme.successGreen : Colors.red.shade400,
          size: 18,
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            text,
            style: TextStyle(
              color: Colors.white.withOpacity(0.8),
              fontSize: 12,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTipChip(IconData icon, String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.accentBlue.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.accentBlue.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: AppTheme.accentBlue, size: 16),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              text,
              style: const TextStyle(
                color: AppTheme.accentBlue,
                fontSize: 11,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomControls() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        children: [
          // Page dots
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(_totalPages, (i) {
              return AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                margin: const EdgeInsets.symmetric(horizontal: 4),
                width: _currentPage == i ? 24 : 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _currentPage == i
                      ? AppTheme.accentBlue
                      : Colors.white24,
                  borderRadius: BorderRadius.circular(4),
                ),
              );
            }),
          ),
          const SizedBox(height: 24),
          // Next / Start button
          SizedBox(
            width: double.infinity,
            height: 52,
            child: ElevatedButton(
              onPressed: () {
                if (_currentPage < _totalPages - 1) {
                  _pageController.nextPage(
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeInOut,
                  );
                } else {
                  widget.onContinue();
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: _currentPage == _totalPages - 1
                    ? AppTheme.successGreen
                    : AppTheme.accentBlue,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: Text(
                _currentPage == _totalPages - 1 ? 'Start Camera' : 'Next',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Painter showing correct fish orientation (head left, arrow)
class _OrientationGuidePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppTheme.accentBlue.withOpacity(0.6)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    // Simple fish outline pointing left
    final cx = size.width / 2;
    final cy = size.height / 2;
    final w = size.width * 0.7;
    final h = w * 0.35;

    final path = Path();
    // Body ellipse
    path.addOval(Rect.fromCenter(
      center: Offset(cx - w * 0.05, cy),
      width: w * 0.7,
      height: h,
    ));
    canvas.drawPath(path, paint);

    // Tail (V shape on right)
    final tailPaint = Paint()
      ..color = AppTheme.accentBlue.withOpacity(0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    canvas.drawLine(
      Offset(cx + w * 0.28, cy),
      Offset(cx + w * 0.42, cy - h * 0.45),
      tailPaint,
    );
    canvas.drawLine(
      Offset(cx + w * 0.28, cy),
      Offset(cx + w * 0.42, cy + h * 0.45),
      tailPaint,
    );

    // Arrow pointing left (indicating head direction)
    final arrowPaint = Paint()
      ..color = AppTheme.successGreen
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;

    final arrowY = cy + h * 0.8;
    canvas.drawLine(
      Offset(cx + w * 0.15, arrowY),
      Offset(cx - w * 0.25, arrowY),
      arrowPaint,
    );
    // Arrowhead
    canvas.drawLine(
      Offset(cx - w * 0.25, arrowY),
      Offset(cx - w * 0.18, arrowY - 6),
      arrowPaint,
    );
    canvas.drawLine(
      Offset(cx - w * 0.25, arrowY),
      Offset(cx - w * 0.18, arrowY + 6),
      arrowPaint,
    );

    // "HEAD" label
    final textPainter = TextPainter(
      text: TextSpan(
        text: 'HEAD',
        style: TextStyle(
          color: AppTheme.successGreen.withOpacity(0.8),
          fontSize: 10,
          fontWeight: FontWeight.bold,
        ),
      ),
      textDirection: TextDirection.ltr,
    );
    textPainter.layout();
    textPainter.paint(canvas, Offset(cx - w * 0.38, arrowY - 5));

    // "TAIL" label
    final tailTextPainter = TextPainter(
      text: TextSpan(
        text: 'TAIL',
        style: TextStyle(
          color: AppTheme.energyOrange.withOpacity(0.8),
          fontSize: 10,
          fontWeight: FontWeight.bold,
        ),
      ),
      textDirection: TextDirection.ltr,
    );
    tailTextPainter.layout();
    tailTextPainter.paint(canvas, Offset(cx + w * 0.20, arrowY - 5));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// Painter showing correct fish position with margin indicators
class _PositionGuidePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    // Draw frame borders
    final framePaint = Paint()
      ..color = AppTheme.successGreen.withOpacity(0.4)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    final margin = size.width * 0.12;
    final frameRect = Rect.fromLTRB(margin, margin * 1.2, size.width - margin, size.height - margin * 1.2);
    canvas.drawRRect(
      RRect.fromRectAndRadius(frameRect, const Radius.circular(8)),
      framePaint,
    );

    // Fish body inside frame
    final fishPaint = Paint()
      ..color = AppTheme.accentBlue.withOpacity(0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;

    final cx = size.width / 2;
    final cy = size.height / 2;
    canvas.drawOval(
      Rect.fromCenter(center: Offset(cx, cy), width: size.width * 0.55, height: size.height * 0.4),
      fishPaint,
    );

    // Margin arrows
    final arrowPaint = Paint()
      ..color = Colors.white.withOpacity(0.4)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;

    // Left margin
    canvas.drawLine(Offset(4, cy), Offset(margin - 4, cy), arrowPaint);
    // Right margin
    canvas.drawLine(Offset(size.width - margin + 4, cy), Offset(size.width - 4, cy), arrowPaint);

    // Checkmark
    final checkPaint = Paint()
      ..color = AppTheme.successGreen
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.0
      ..strokeCap = StrokeCap.round;

    canvas.drawLine(
      Offset(size.width - 30, 15),
      Offset(size.width - 23, 22),
      checkPaint,
    );
    canvas.drawLine(
      Offset(size.width - 23, 22),
      Offset(size.width - 14, 10),
      checkPaint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
