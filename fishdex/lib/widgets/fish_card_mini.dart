import 'dart:convert';
import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// Versión compacta de la carta de pez para mostrar en grids
/// Incluye variante "no descubierto" con silueta gris
class FishCardMini extends StatelessWidget {
  /// Nombre de la especie del pez
  final String? species;

  /// Tamaño estimado en cm
  final double? sizeCm;

  /// Rareza del pez (common, uncommon, rare, legendary)
  final String rarity;

  /// Número de veces avistado
  final int timesSpotted;

  /// Imagen en base64 (opcional)
  final String? imageBase64;

  /// Si el pez ha sido descubierto por el usuario
  final bool isDiscovered;

  /// Callback al tocar la carta
  final VoidCallback? onTap;

  const FishCardMini({
    super.key,
    this.species,
    this.sizeCm,
    this.rarity = 'common',
    this.timesSpotted = 0,
    this.imageBase64,
    this.isDiscovered = true,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final rarityColor = AppTheme.getRarityColor(rarity);

    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: AppTheme.darkSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isDiscovered
                ? rarityColor.withOpacity(0.5)
                : Colors.white.withOpacity(0.1),
            width: 1.5,
          ),
          boxShadow: isDiscovered
              ? [
                  BoxShadow(
                    color: rarityColor.withOpacity(0.2),
                    blurRadius: 8,
                    spreadRadius: 1,
                  ),
                ]
              : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Imagen/icono del pez
            Expanded(
              flex: 3,
              child: _buildFishImage(rarityColor),
            ),

            // Info inferior
            Expanded(
              flex: 2,
              child: _buildInfo(rarityColor),
            ),
          ],
        ),
      ),
    );
  }

  /// Sección de imagen: muestra foto, icono o silueta según estado
  Widget _buildFishImage(Color rarityColor) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(13)),
        color: Colors.black.withOpacity(0.2),
      ),
      child: Stack(
        children: [
          // Imagen o silueta
          Center(
            child: _getImageWidget(rarityColor),
          ),

          // Badge de veces avistado (arriba derecha)
          if (isDiscovered && timesSpotted > 0)
            Positioned(
              top: 6,
              right: 6,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppTheme.darkSurfaceElevated,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: Colors.white.withOpacity(0.2),
                    width: 1,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.visibility,
                      size: 10,
                      color: AppTheme.teal,
                    ),
                    const SizedBox(width: 3),
                    Text(
                      'x$timesSpotted',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 10,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// Widget de imagen según estado del pez
  Widget _getImageWidget(Color rarityColor) {
    if (!isDiscovered) {
      // Pez no descubierto - silueta gris
      return Icon(
        Icons.help_outline,
        size: 40,
        color: Colors.white.withOpacity(0.15),
      );
    }

    if (imageBase64 != null && imageBase64!.isNotEmpty) {
      // Imagen real del pez
      return ClipRRect(
        borderRadius: const BorderRadius.vertical(top: Radius.circular(13)),
        child: Image.memory(
          base64Decode(imageBase64!),
          fit: BoxFit.cover,
          width: double.infinity,
          height: double.infinity,
        ),
      );
    }

    // Icono por defecto si no hay imagen
    return Icon(
      Icons.phishing,
      size: 36,
      color: rarityColor.withOpacity(0.6),
    );
  }

  /// Sección de información: nombre, tamaño
  Widget _buildInfo(Color rarityColor) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Nombre de la especie o "???"
          Text(
            isDiscovered ? (species ?? 'Desconocido') : '???',
            style: TextStyle(
              color: isDiscovered ? Colors.white : Colors.white.withOpacity(0.3),
              fontSize: 13,
              fontWeight: FontWeight.bold,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),

          const SizedBox(height: 2),

          // Tamaño o indicador de no descubierto
          if (isDiscovered && sizeCm != null)
            Row(
              children: [
                Icon(
                  Icons.straighten,
                  size: 11,
                  color: Colors.white.withOpacity(0.5),
                ),
                const SizedBox(width: 3),
                Text(
                  '${sizeCm!.toStringAsFixed(1)} cm',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                    fontSize: 11,
                  ),
                ),
              ],
            )
          else if (!isDiscovered)
            Text(
              'No descubierto',
              style: TextStyle(
                color: Colors.white.withOpacity(0.2),
                fontSize: 11,
                fontStyle: FontStyle.italic,
              ),
            ),
        ],
      ),
    );
  }
}
