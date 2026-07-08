import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';

/// Controles de grabación con botón grande estilo Pokémon Go
/// y barra de progreso circular
class RecordingControls extends StatelessWidget {
  final bool isRecording;
  final double progress;
  final int maxDurationSeconds;
  final VoidCallback onStartRecording;
  final VoidCallback onStopRecording;

  const RecordingControls({
    super.key,
    required this.isRecording,
    required this.progress,
    required this.maxDurationSeconds,
    required this.onStartRecording,
    required this.onStopRecording,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.only(bottom: 100, top: 20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Colors.transparent,
            Colors.black.withOpacity(0.7),
          ],
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Barra de progreso lineal (visible durante grabación)
          if (isRecording) _buildProgressBar(),
          
          const SizedBox(height: 20),

          // Botón principal de grabación
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Espacio para galería (futuro)
              const SizedBox(width: 60),
              
              // BOTÓN DE GRABAR
              _buildRecordButton(),
              
              // Botón de cambiar cámara (futuro)
              const SizedBox(width: 60),
            ],
          ),

          const SizedBox(height: 12),

          // Texto de ayuda
          Text(
            isRecording
                ? context.l10n.recordingStateRecording
                : context.l10n.recordingStatePressToRecord(maxDurationSeconds),
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecordButton() {
    return GestureDetector(
      onTap: isRecording ? onStopRecording : onStartRecording,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Anillo de progreso exterior
          SizedBox(
            width: 80,
            height: 80,
            child: CircularProgressIndicator(
              value: isRecording ? progress : 0,
              strokeWidth: 4,
              backgroundColor: Colors.white24,
              valueColor: const AlwaysStoppedAnimation<Color>(
                AppTheme.accentBlue,
              ),
            ),
          ),

          // Botón interno
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: isRecording ? 32 : 64,
            height: isRecording ? 32 : 64,
            decoration: BoxDecoration(
              color: isRecording ? Colors.red : Colors.red,
              borderRadius: BorderRadius.circular(isRecording ? 8 : 32),
              boxShadow: [
                BoxShadow(
                  color: Colors.red.withOpacity(0.5),
                  blurRadius: isRecording ? 15 : 8,
                  spreadRadius: isRecording ? 3 : 1,
                ),
              ],
            ),
            child: isRecording
                ? const Icon(Icons.stop, color: Colors.white, size: 20)
                : null,
          ),

          // Anillo exterior decorativo
          Container(
            width: 74,
            height: 74,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: Colors.white,
                width: 3,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildProgressBar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: Column(
        children: [
          // Barra de progreso
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 4,
              backgroundColor: Colors.white24,
              valueColor: AlwaysStoppedAnimation<Color>(
                progress > 0.8 ? AppTheme.energyOrange : AppTheme.accentBlue,
              ),
            ),
          ),
          const SizedBox(height: 6),
          // Tiempo restante
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                '${(progress * maxDurationSeconds).toInt()}s',
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 11,
                ),
              ),
              Text(
                '${maxDurationSeconds}s',
                style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
