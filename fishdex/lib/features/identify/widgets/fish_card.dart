import 'dart:convert';
import 'package:flutter/material.dart';
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

  const FishCard({
    super.key,
    required this.fishId,
    required this.species,
    required this.sizeCm,
    required this.rarity,
    required this.confidence,
    this.imageBase64,
    this.isNew = false,
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
          
          // Imagen del pez
          _buildFishImage(),
          
          // Info del pez
          _buildFishInfo(),
          
          // Stats del pez
          _buildStats(),
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
      height: 160,
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
            ? Image.memory(
                base64Decode(imageBase64!),
                fit: BoxFit.cover,
              )
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

  Widget _buildFishInfo() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          // Tamaño
          _buildInfoBadge(
            Icons.straighten,
            '${sizeCm.toStringAsFixed(1)} cm',
          ),
          const SizedBox(width: 8),
          // Confianza
          _buildInfoBadge(
            Icons.psychology,
            '${(confidence * 100).toStringAsFixed(0)}% IA',
          ),
          const Spacer(),
          // Badge de nuevo
          if (isNew)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.successGreen.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: AppTheme.successGreen.withOpacity(0.5),
                ),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.new_releases, color: AppTheme.successGreen, size: 14),
                  SizedBox(width: 4),
                  Text(
                    'NUEVO',
                    style: TextStyle(
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

  Widget _buildStats() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Row(
        children: [
          // Barra de rareza visual
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'RAREZA',
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
