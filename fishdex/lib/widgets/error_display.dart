import 'package:flutter/material.dart';
import '../core/theme/app_theme.dart';

/// Widget reutilizable para mostrar errores con opciones de reintento
/// y modo offline. Estilizado con el tema de la app.
class ErrorDisplay extends StatelessWidget {
  /// Título del error (ej: "Sin conexión", "Error de servidor")
  final String title;

  /// Mensaje descriptivo del error
  final String message;

  /// Callback al presionar "Reintentar"
  final VoidCallback? onRetry;

  /// Callback al presionar "Modo offline"
  final VoidCallback? onOfflineMode;

  /// Icono personalizado (por defecto muestra error genérico)
  final IconData icon;

  const ErrorDisplay({
    super.key,
    this.title = 'Algo salió mal',
    this.message = 'Ha ocurrido un error inesperado. Intenta de nuevo.',
    this.onRetry,
    this.onOfflineMode,
    this.icon = Icons.error_outline,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(32),
          decoration: BoxDecoration(
            color: AppTheme.darkSurface,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: AppTheme.rareRed.withOpacity(0.3),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: AppTheme.rareRed.withOpacity(0.1),
                blurRadius: 20,
                spreadRadius: 2,
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Icono de error
              _buildErrorIcon(),

              const SizedBox(height: 20),

              // Título
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
                textAlign: TextAlign.center,
              ),

              const SizedBox(height: 12),

              // Mensaje descriptivo
              Text(
                message,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.6),
                  fontSize: 15,
                  height: 1.4,
                ),
                textAlign: TextAlign.center,
              ),

              const SizedBox(height: 28),

              // Botón de reintentar
              if (onRetry != null) _buildRetryButton(),

              // Botón de modo offline
              if (onOfflineMode != null) ...[
                const SizedBox(height: 12),
                _buildOfflineButton(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  /// Icono de error con fondo circular
  Widget _buildErrorIcon() {
    return Container(
      width: 72,
      height: 72,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: AppTheme.rareRed.withOpacity(0.1),
        border: Border.all(
          color: AppTheme.rareRed.withOpacity(0.3),
          width: 2,
        ),
      ),
      child: Icon(
        icon,
        size: 36,
        color: AppTheme.rareRed,
      ),
    );
  }

  /// Botón principal para reintentar la operación
  Widget _buildRetryButton() {
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: ElevatedButton.icon(
        onPressed: onRetry,
        icon: const Icon(Icons.refresh, size: 20),
        label: const Text(
          'Reintentar',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: AppTheme.accentBlue,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
    );
  }

  /// Botón secundario para activar modo offline
  Widget _buildOfflineButton() {
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: OutlinedButton.icon(
        onPressed: onOfflineMode,
        icon: const Icon(Icons.wifi_off, size: 20),
        label: const Text(
          'Modo offline',
          style: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
        style: OutlinedButton.styleFrom(
          foregroundColor: AppTheme.teal,
          side: BorderSide(
            color: AppTheme.teal.withOpacity(0.5),
            width: 1.5,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
    );
  }
}
