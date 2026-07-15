import 'package:flutter/material.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';

/// Marker anónimo que indica que un pez fue registrado anteriormente
/// por otro usuario, sin revelar datos sensibles.
/// Se muestra solo a fishermen cuando hay coincidencia de fish_id.
class AnonymousMarker extends StatelessWidget {
  final VoidCallback? onTap;

  const AnonymousMarker({super.key, this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.grey.shade700.withOpacity(0.8),
          border: Border.all(
            color: Colors.grey.shade500,
            width: 2,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.3),
              blurRadius: 4,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: const Icon(
          Icons.nature, // Ícono de rama/naturaleza (neutral)
          color: Colors.white70,
          size: 18,
        ),
      ),
    );
  }
}

/// Bottom sheet que se muestra cuando un fisherman toca un marker anónimo.
/// Solo muestra información genérica sin revelar datos sensibles.
class AnonymousMarkerBottomSheet extends StatelessWidget {
  final String species;

  const AnonymousMarkerBottomSheet({
    super.key,
    required this.species,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppTheme.darkBackground,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withOpacity(0.1)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Handle
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.3),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 24),

          // Ícono
          Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.grey.shade800,
              border: Border.all(
                color: Colors.grey.shade600,
                width: 2,
              ),
            ),
            child: const Icon(
              Icons.nature,
              color: Colors.white60,
              size: 28,
            ),
          ),
          const SizedBox(height: 16),

          // Título
          Text(
            context.l10n.mapAnonymousTitle,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),

          // Descripción
          Text(
            context.l10n.mapAnonymousDesc(species),
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 14,
              height: 1.4,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 20),

          // Indicador
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.grey.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.grey.withOpacity(0.3)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.lock_outline,
                  color: Colors.grey.shade400,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  context.l10n.mapDataProtected,
                  style: TextStyle(
                    color: Colors.grey.shade400,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}
