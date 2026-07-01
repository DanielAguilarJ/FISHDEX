import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/identify_result.dart';
import '../widgets/fish_card.dart';
import '../widgets/confetti_overlay.dart';
import '../widgets/xp_animation.dart';
import '../widgets/reunion_info.dart';

/// Pantalla de resultado de identificación
/// Muestra diferentes animaciones según si el pez es nuevo o un reencuentro
class ResultScreen extends ConsumerStatefulWidget {
  final IdentifyResult result;

  const ResultScreen({super.key, required this.result});

  @override
  ConsumerState<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends ConsumerState<ResultScreen>
    with TickerProviderStateMixin {
  late AnimationController _entranceController;
  late AnimationController _cardController;
  late Animation<double> _fadeIn;
  late Animation<double> _slideUp;
  late Animation<double> _cardScale;
  late Animation<double> _cardRotation;

  bool _showConfetti = false;
  bool _showXP = false;
  bool _showDetails = false;

  @override
  void initState() {
    super.initState();

    // Animación de entrada del título
    _entranceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );

    _fadeIn = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _entranceController, curve: Curves.easeOut),
    );

    _slideUp = Tween<double>(begin: 50, end: 0).animate(
      CurvedAnimation(parent: _entranceController, curve: Curves.easeOutBack),
    );

    // Animación de la carta del pez
    _cardController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );

    _cardScale = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _cardController, curve: Curves.elasticOut),
    );

    _cardRotation = Tween<double>(begin: 0.1, end: 0.0).animate(
      CurvedAnimation(parent: _cardController, curve: Curves.easeOut),
    );

    // Secuencia de animaciones
    _startAnimationSequence();
  }

  Future<void> _startAnimationSequence() async {
    // 1. Mostrar confeti si es nuevo
    if (widget.result.isNew) {
      await Future.delayed(const Duration(milliseconds: 200));
      setState(() => _showConfetti = true);
    }

    // 2. Animar título
    await Future.delayed(const Duration(milliseconds: 300));
    _entranceController.forward();

    // 3. Animar carta del pez
    await Future.delayed(const Duration(milliseconds: 500));
    _cardController.forward();

    // 4. Mostrar XP
    await Future.delayed(const Duration(milliseconds: 800));
    setState(() => _showXP = true);

    // 5. Mostrar detalles
    await Future.delayed(const Duration(milliseconds: 500));
    setState(() => _showDetails = true);
  }

  @override
  void dispose() {
    _entranceController.dispose();
    _cardController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: Stack(
        children: [
          // Fondo con gradiente según resultado
          _buildBackground(),

          // Contenido principal
          SafeArea(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                children: [
                  const SizedBox(height: 20),

                  // Título animado
                  _buildTitle(),
                  const SizedBox(height: 24),

                  // Carta del pez
                  _buildFishCard(),
                  const SizedBox(height: 20),

                  // XP ganada
                  if (_showXP) _buildXPSection(),
                  const SizedBox(height: 16),

                  // Detalles (reencuentro o nuevo)
                  if (_showDetails) _buildDetailsSection(),
                  const SizedBox(height: 24),

                  // Botones de acción
                  if (_showDetails) _buildActions(),
                  const SizedBox(height: 40),
                ],
              ),
            ),
          ),

          // Confeti overlay
          if (_showConfetti) const ConfettiOverlay(),

          // Botón cerrar
          Positioned(
            top: MediaQuery.of(context).padding.top + 12,
            right: 16,
            child: GestureDetector(
              onTap: () => Navigator.of(context).popUntil(
                (route) => route.isFirst,
              ),
              child: Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withOpacity(0.1),
                ),
                child: const Icon(Icons.close, color: Colors.white70, size: 20),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBackground() {
    final colors = widget.result.isNew
        ? [AppTheme.darkBackground, const Color(0xFF0A2E1A)] // Verde oscuro
        : [AppTheme.darkBackground, const Color(0xFF1A1A3E)]; // Azul oscuro

    return Container(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: Alignment.topCenter,
          radius: 1.5,
          colors: colors,
        ),
      ),
    );
  }

  Widget _buildTitle() {
    return AnimatedBuilder(
      animation: _entranceController,
      builder: (context, child) {
        return Transform.translate(
          offset: Offset(0, _slideUp.value),
          child: Opacity(
            opacity: _fadeIn.value,
            child: Column(
              children: [
                // Badge de rareza
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: AppTheme.getRarityColor(widget.result.rarity)
                        .withOpacity(0.2),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: AppTheme.getRarityColor(widget.result.rarity)
                          .withOpacity(0.5),
                    ),
                  ),
                  child: Text(
                    widget.result.rarity.toUpperCase(),
                    style: TextStyle(
                      color: AppTheme.getRarityColor(widget.result.rarity),
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 2,
                    ),
                  ),
                ),
                const SizedBox(height: 12),

                // Título principal
                Text(
                  widget.result.isNew
                      ? '¡NUEVO DESCUBRIMIENTO!'
                      : '¡REENCUENTRO!',
                  style: Theme.of(context).textTheme.displayMedium?.copyWith(
                        color: widget.result.isNew
                            ? AppTheme.successGreen
                            : AppTheme.energyOrange,
                        shadows: [
                          Shadow(
                            color: (widget.result.isNew
                                    ? AppTheme.successGreen
                                    : AppTheme.energyOrange)
                                .withOpacity(0.5),
                            blurRadius: 20,
                          ),
                        ],
                      ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFishCard() {
    return AnimatedBuilder(
      animation: _cardController,
      builder: (context, child) {
        return Transform.scale(
          scale: _cardScale.value,
          child: Transform.rotate(
            angle: _cardRotation.value,
            child: FishCard(
              fishId: widget.result.fishId,
              species: widget.result.species,
              sizeCm: widget.result.estimatedSizeCm,
              rarity: widget.result.rarity,
              confidence: widget.result.confidence,
              imageBase64: widget.result.frameUsed,
              isNew: widget.result.isNew,
            ),
          ),
        );
      },
    );
  }

  Widget _buildXPSection() {
    return XPAnimation(
      xpEarned: widget.result.xpEarned,
      isNewFish: widget.result.isNew,
    );
  }

  Widget _buildDetailsSection() {
    if (!widget.result.isNew && widget.result.previousData != null) {
      return ReunionInfo(previousData: widget.result.previousData!);
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.info_outline, color: AppTheme.accentBlue, size: 18),
              const SizedBox(width: 8),
              Text(
                'Detalles del avistamiento',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.8),
                  fontSize: 14,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _buildDetailRow('ID del pez', widget.result.fishId),
          _buildDetailRow('Especie', widget.result.species),
          _buildDetailRow(
            'Tamaño estimado',
            '${widget.result.estimatedSizeCm} cm',
          ),
          _buildDetailRow(
            'Confianza IA',
            '${(widget.result.confidence * 100).toStringAsFixed(1)}%',
          ),
        ],
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.5),
              fontSize: 13,
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActions() {
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          height: 52,
          child: ElevatedButton.icon(
            onPressed: () {
              Navigator.of(context).popUntil((route) => route.isFirst);
            },
            icon: const Icon(Icons.collections_bookmark),
            label: const Text('VER EN MI COLECCIÓN'),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.accentBlue,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: OutlinedButton.icon(
            onPressed: () {
              Navigator.of(context).popUntil((route) => route.isFirst);
            },
            icon: const Icon(Icons.map),
            label: const Text('VOLVER AL MAPA'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.white70,
              side: const BorderSide(color: Colors.white24),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
