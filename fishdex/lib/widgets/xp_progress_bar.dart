import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// Barra de progreso de XP animada con badge de nivel
/// Muestra el nivel actual, progreso visual y texto de XP
class XpProgressBar extends StatefulWidget {
  /// Nivel actual del usuario
  final int level;

  /// XP actual en el nivel
  final int currentXp;

  /// XP necesario para subir de nivel
  final int requiredXp;

  /// Si se debe animar el efecto de subida de nivel
  final bool showLevelUpEffect;

  /// Duración de la animación de llenado
  final Duration animationDuration;

  const XpProgressBar({
    super.key,
    required this.level,
    required this.currentXp,
    required this.requiredXp,
    this.showLevelUpEffect = false,
    this.animationDuration = const Duration(milliseconds: 800),
  });

  @override
  State<XpProgressBar> createState() => _XpProgressBarState();
}

class _XpProgressBarState extends State<XpProgressBar>
    with SingleTickerProviderStateMixin {
  /// Controlador para la animación de llenado de barra
  late AnimationController _animController;
  late Animation<double> _progressAnimation;

  /// Valor previo del progreso para animar desde ahí
  double _previousProgress = 0.0;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: widget.animationDuration,
    );

    final targetProgress = widget.requiredXp > 0
        ? (widget.currentXp / widget.requiredXp).clamp(0.0, 1.0)
        : 0.0;

    _progressAnimation = Tween<double>(
      begin: 0.0,
      end: targetProgress,
    ).animate(CurvedAnimation(
      parent: _animController,
      curve: Curves.easeOutCubic,
    ));

    // Iniciar animación al crear el widget
    _animController.forward();
  }

  @override
  void didUpdateWidget(XpProgressBar oldWidget) {
    super.didUpdateWidget(oldWidget);

    // Si cambió el XP, animar la transición
    if (oldWidget.currentXp != widget.currentXp ||
        oldWidget.requiredXp != widget.requiredXp) {
      _previousProgress = oldWidget.requiredXp > 0
          ? (oldWidget.currentXp / oldWidget.requiredXp).clamp(0.0, 1.0)
          : 0.0;

      final targetProgress = widget.requiredXp > 0
          ? (widget.currentXp / widget.requiredXp).clamp(0.0, 1.0)
          : 0.0;

      _progressAnimation = Tween<double>(
        begin: _previousProgress,
        end: targetProgress,
      ).animate(CurvedAnimation(
        parent: _animController,
        curve: Curves.easeOutCubic,
      ));

      _animController.reset();
      _animController.forward();
    }
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppTheme.gold.withOpacity(0.2),
          width: 1,
        ),
      ),
      child: Row(
        children: [
          // Badge de nivel (izquierda)
          _buildLevelBadge(),

          const SizedBox(width: 12),

          // Barra de progreso animada (centro)
          Expanded(child: _buildProgressBar()),

          const SizedBox(width: 12),

          // Texto de XP (derecha)
          _buildXpText(),
        ],
      ),
    );
  }

  /// Badge circular que muestra el nivel actual
  Widget _buildLevelBadge() {
    return Container(
      width: 40,
      height: 40,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: AppTheme.goldGradient,
        boxShadow: [
          if (widget.showLevelUpEffect)
            BoxShadow(
              color: AppTheme.gold.withOpacity(0.6),
              blurRadius: 12,
              spreadRadius: 2,
            ),
        ],
      ),
      child: Center(
        child: Text(
          '${widget.level}',
          style: const TextStyle(
            color: Colors.black87,
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }

  /// Barra de progreso con gradiente dorado y animación suave
  Widget _buildProgressBar() {
    return AnimatedBuilder(
      animation: _progressAnimation,
      builder: (context, child) {
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Barra visual
            Container(
              height: 12,
              width: double.infinity,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(6),
                color: Colors.white.withOpacity(0.1),
              ),
              child: Stack(
                children: [
                  // Progreso con gradiente dorado
                  FractionallySizedBox(
                    alignment: Alignment.centerLeft,
                    widthFactor: _progressAnimation.value,
                    child: Container(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(6),
                        gradient: AppTheme.goldGradient,
                        boxShadow: [
                          BoxShadow(
                            color: AppTheme.gold.withOpacity(0.4),
                            blurRadius: 4,
                            offset: const Offset(0, 1),
                          ),
                        ],
                      ),
                    ),
                  ),

                  // Efecto de brillo sobre la barra
                  if (_progressAnimation.value > 0.05)
                    FractionallySizedBox(
                      alignment: Alignment.centerLeft,
                      widthFactor: _progressAnimation.value,
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(6),
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              Colors.white.withOpacity(0.3),
                              Colors.transparent,
                            ],
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  /// Texto que muestra XP actual / requerido
  Widget _buildXpText() {
    return Text(
      '${widget.currentXp}/${widget.requiredXp} XP',
      style: TextStyle(
        color: AppTheme.gold.withOpacity(0.9),
        fontSize: 12,
        fontWeight: FontWeight.bold,
      ),
    );
  }
}
