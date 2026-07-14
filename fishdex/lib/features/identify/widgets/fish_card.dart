import 'dart:convert';
import 'package:flutter/material.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';

/// Carta coleccionable del pez estilo Pokémon TCG
/// Muestra la información del pez con diseño de carta de juego
class FishCard extends StatelessWidget {
  final String fishId;
  final String species;
  final double sizeCm;
  final String rarity;
  final double confidence;
  final String? imageBase64;
  final bool isNew;
  // AI model validation breakdown (optional)
  final double? detectionConfidence;
  final double? classificationConfidence;
  final double? matchConfidence;

  const FishCard({
    super.key,
    required this.fishId,
    required this.species,
    required this.sizeCm,
    required this.rarity,
    required this.confidence,
    this.imageBase64,
    this.isNew = false,
    this.detectionConfidence,
    this.classificationConfidence,
    this.matchConfidence,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      constraints: const BoxConstraints(maxWidth: 320),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: _getCardGradient(),
        border: Border.all(
          color: AppTheme.getRarityColor(rarity).withOpacity(0.6),
          width: 2,
        ),
        boxShadow: [
          BoxShadow(
            color: AppTheme.getRarityColor(rarity).withOpacity(0.3),
            blurRadius: 20,
            spreadRadius: 2,
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header de la carta
          _buildCardHeader(),

          // Imagen del pez (annotated or plain)
          _buildFishImage(),

          // AI validation panel (3 model confidences)
          _buildAiValidation(context),

          // Info del pez
          _buildFishInfo(context),

          // Stats del pez
          _buildStats(context),
        ],
      ),
    );
  }

  LinearGradient _getCardGradient() {
    switch (rarity) {
      case 'legendary':
        return const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1A0A2E), Color(0xFF2D1B4E), Color(0xFF1A0A2E)],
        );
      case 'rare':
        return const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0A1A2E), Color(0xFF1B2D4E), Color(0xFF0A1A2E)],
        );
      case 'uncommon':
        return const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0A2E1A), Color(0xFF1B4E2D), Color(0xFF0A2E1A)],
        );
      default:
        return const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppTheme.darkSurface,
            AppTheme.darkSurfaceElevated,
            AppTheme.darkSurface,
          ],
        );
    }
  }

  Widget _buildCardHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Nombre de la especie
          Expanded(
            child: Text(
              species,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          // ID del pez
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              '#$fishId',
              style: TextStyle(
                color: Colors.white.withOpacity(0.7),
                fontSize: 11,
                fontFamily: 'monospace',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFishImage() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      height: 170,
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        color: Colors.black.withOpacity(0.3),
        border: Border.all(
          color: AppTheme.getRarityColor(rarity).withOpacity(0.3),
          width: 1,
        ),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: imageBase64 != null && imageBase64!.isNotEmpty
            ? (imageBase64!.startsWith('http')
                ? Image.network(
                    imageBase64!,
                    fit: BoxFit.contain,
                    alignment: Alignment.center,
                    errorBuilder: (_, __, ___) => const Center(
                      child: Icon(Icons.broken_image,
                          color: Colors.white30, size: 40),
                    ),
                  )
                : Image.memory(
                    base64Decode(imageBase64!),
                    fit: BoxFit.contain,
                  ))
            : Center(
                child: Icon(
                  Icons.phishing,
                  size: 64,
                  color: AppTheme.getRarityColor(rarity).withOpacity(0.5),
                ),
              ),
      ),
    );
  }

  /// AI validation panel — shows DET / CLS / MATCH (or NEW) confidence values.
  Widget _buildAiValidation(BuildContext context) {
    final hasDet = detectionConfidence != null;
    final hasCls = classificationConfidence != null;
    final hasMatch = matchConfidence != null;

    if (!hasDet && !hasCls && !hasMatch) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 0, 14, 6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.black.withOpacity(0.30),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: AppTheme.getRarityColor(rarity).withOpacity(0.18),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            if (hasDet)
              _buildAiBadge(
                'DET',
                detectionConfidence!,
                const Color(0xFF4CAF50),
              ),
            if (hasDet && (hasCls || hasMatch))
              _buildDivider(),
            if (hasCls)
              _buildAiBadge(
                'CLS',
                classificationConfidence!,
                const Color(0xFF29B6F6),
              ),
            if (hasCls && (isNew || hasMatch))
              _buildDivider(),
            if (isNew)
              _buildNewBadge()
            else if (hasMatch)
              _buildAiBadge(
                'MATCH',
                matchConfidence!,
                const Color(0xFFFFB74D),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildDivider() => Container(
        width: 1,
        height: 28,
        color: Colors.white.withOpacity(0.12),
      );

  Widget _buildAiBadge(String label, double value, Color color) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: TextStyle(
            color: color.withOpacity(0.65),
            fontSize: 9,
            fontWeight: FontWeight.bold,
            letterSpacing: 0.8,
          ),
        ),
        const SizedBox(height: 3),
        Text(
          '${(value * 100).toStringAsFixed(0)}%',
          style: TextStyle(
            color: color,
            fontSize: 15,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Widget _buildNewBadge() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'MATCH',
          style: TextStyle(
            color: const Color(0xFF4CAF50).withOpacity(0.65),
            fontSize: 9,
            fontWeight: FontWeight.bold,
            letterSpacing: 0.8,
          ),
        ),
        const SizedBox(height: 3),
        const Text(
          'NEW',
          style: TextStyle(
            color: Color(0xFF4CAF50),
            fontSize: 15,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Widget _buildFishInfo(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          // Tamaño
          _buildInfoBadge(
            Icons.straighten,
            '${sizeCm.toStringAsFixed(1)} cm',
          ),
          const SizedBox(width: 8),
          // Confianza general
          _buildInfoBadge(
            Icons.psychology,
            '${(confidence * 100).toStringAsFixed(0)}${context.l10n.fishCardAiConfidence}',
          ),
          const Spacer(),
          // Badge de nuevo
          if (isNew)
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.successGreen.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: AppTheme.successGreen.withOpacity(0.5),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.new_releases,
                      color: AppTheme.successGreen, size: 14),
                  const SizedBox(width: 4),
                  Text(
                    context.l10n.fishCardNew,
                    style: const TextStyle(
                      color: AppTheme.successGreen,
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildInfoBadge(IconData icon, String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Colors.white70, size: 14),
          const SizedBox(width: 4),
          Text(
            text,
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStats(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 16),
      child: Row(
        children: [
          // Barra de rareza visual
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.fishCardRarity,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.4),
                    fontSize: 10,
                    letterSpacing: 1,
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: List.generate(5, (index) {
                    final filled = _getRarityLevel() > index;
                    return Container(
                      width: 24,
                      height: 6,
                      margin: const EdgeInsets.only(right: 3),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(3),
                        color: filled
                            ? AppTheme.getRarityColor(rarity)
                            : Colors.white.withOpacity(0.1),
                      ),
                    );
                  }),
                ),
              ],
            ),
          ),
          // Icono de rareza
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppTheme.getRarityColor(rarity).withOpacity(0.2),
            ),
            child: Icon(
              _getRarityIcon(),
              color: AppTheme.getRarityColor(rarity),
              size: 18,
            ),
          ),
        ],
      ),
    );
  }

  int _getRarityLevel() {
    switch (rarity) {
      case 'common':
        return 1;
      case 'uncommon':
        return 2;
      case 'rare':
        return 4;
      case 'legendary':
        return 5;
      default:
        return 1;
    }
  }

  IconData _getRarityIcon() {
    switch (rarity) {
      case 'legendary':
        return Icons.auto_awesome;
      case 'rare':
        return Icons.diamond;
      case 'uncommon':
        return Icons.star;
      default:
        return Icons.circle;
    }
  }
}
