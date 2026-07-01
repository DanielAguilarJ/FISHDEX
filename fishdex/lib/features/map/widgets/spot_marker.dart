import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';

/// Widget del marcador de un spot de pesca en el mapa
class SpotMarkerWidget extends StatelessWidget {
  final bool hasRareFish;
  final int totalCatches;

  const SpotMarkerWidget({
    super.key,
    required this.hasRareFish,
    required this.totalCatches,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        // Halo de resplandor para spots con peces raros
        if (hasRareFish)
          Container(
            width: 50,
            height: 50,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppTheme.legendaryPurple.withOpacity(0.2),
            ),
          ),
        
        // Marcador principal
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: hasRareFish ? AppTheme.legendaryPurple : AppTheme.teal,
            border: Border.all(
              color: Colors.white,
              width: 2,
            ),
            boxShadow: [
              BoxShadow(
                color: (hasRareFish ? AppTheme.legendaryPurple : AppTheme.teal)
                    .withOpacity(0.5),
                blurRadius: 8,
                spreadRadius: 1,
              ),
            ],
          ),
          child: Center(
            child: Icon(
              hasRareFish ? Icons.star : Icons.phishing,
              color: Colors.white,
              size: 20,
            ),
          ),
        ),
        
        // Badge con número de capturas
        if (totalCatches > 0)
          Positioned(
            top: 0,
            right: 0,
            child: Container(
              padding: const EdgeInsets.all(3),
              decoration: BoxDecoration(
                color: AppTheme.energyOrange,
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 1),
              ),
              constraints: const BoxConstraints(
                minWidth: 18,
                minHeight: 18,
              ),
              child: Center(
                child: Text(
                  totalCatches > 99 ? '99+' : totalCatches.toString(),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}
