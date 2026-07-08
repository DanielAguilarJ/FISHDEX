import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/identify_result.dart';
import '../providers/capture_provider.dart';
import '../widgets/capture_form_fields.dart';

/// Pantalla de formulario de captura.
/// Se muestra cuando:
/// - La IA no pudo identificar con confianza suficiente (formulario vacío)
/// - El usuario quiere editar/completar datos de una captura existente
/// - Se usa como formulario de respaldo post-identificación
class CaptureFormScreen extends ConsumerStatefulWidget {
  /// Resultado de la IA (puede ser null si es entrada completamente manual)
  final IdentifyResult? aiResult;

  /// Coordenadas GPS del momento de captura
  final double? latitude;
  final double? longitude;

  /// Path del video grabado
  final String? videoPath;

  const CaptureFormScreen({
    super.key,
    this.aiResult,
    this.latitude,
    this.longitude,
    this.videoPath,
  });

  @override
  ConsumerState<CaptureFormScreen> createState() => _CaptureFormScreenState();
}

class _CaptureFormScreenState extends ConsumerState<CaptureFormScreen> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _speciesController;
  late TextEditingController _lengthController;
  late TextEditingController _weightController;
  late TextEditingController _colorController;
  late TextEditingController _featuresController;
  late TextEditingController _notesController;
  late TextEditingController _latController;
  late TextEditingController _lngController;
  String? _selectedCondition;

  @override
  void initState() {
    super.initState();

    // Inicializar con datos de la IA si existen
    _speciesController = TextEditingController(
      text: widget.aiResult?.species ?? '',
    );
    _lengthController = TextEditingController(
      text: widget.aiResult?.estimatedSizeCm.toString() ?? '',
    );
    _weightController = TextEditingController();
    _colorController = TextEditingController();
    _featuresController = TextEditingController();
    _notesController = TextEditingController();
    _latController = TextEditingController(
      text: widget.latitude?.toStringAsFixed(6) ?? '',
    );
    _lngController = TextEditingController(
      text: widget.longitude?.toStringAsFixed(6) ?? '',
    );

    // Inicializar el provider
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final notifier = ref.read(captureFormProvider.notifier);
      if (widget.aiResult != null) {
        notifier.initializeWithAiResult(
          widget.aiResult!,
          latitude: widget.latitude,
          longitude: widget.longitude,
          videoPath: widget.videoPath,
        );
      } else {
        notifier.initializeManual(
          latitude: widget.latitude,
          longitude: widget.longitude,
          videoPath: widget.videoPath,
        );
      }
    });
  }

  @override
  void dispose() {
    _speciesController.dispose();
    _lengthController.dispose();
    _weightController.dispose();
    _colorController.dispose();
    _featuresController.dispose();
    _notesController.dispose();
    _latController.dispose();
    _lngController.dispose();
    super.dispose();
  }

  Future<void> _handleSave() async {
    final l10n = context.l10n;
    if (!_formKey.currentState!.validate()) return;
    if (_selectedCondition == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(l10n.captureFormSelectCondition),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    final notifier = ref.read(captureFormProvider.notifier);

    // Actualizar estado del provider con los valores del formulario
    notifier.setSpecies(_speciesController.text.trim());
    notifier.setLengthCm(double.tryParse(_lengthController.text));
    notifier.setWeightKg(double.tryParse(_weightController.text));
    notifier.setPredominantColor(
      _colorController.text.isEmpty ? null : _colorController.text.trim(),
    );
    notifier.setPhysicalFeatures(
      _featuresController.text.isEmpty ? null : _featuresController.text.trim(),
    );
    notifier.setNotes(
      _notesController.text.isEmpty ? null : _notesController.text.trim(),
    );
    notifier.setCondition(_selectedCondition);
    notifier.setLatitude(double.tryParse(_latController.text));
    notifier.setLongitude(double.tryParse(_lngController.text));

    // Obtener userId
    try {
      final account = ref.read(appwriteAccountProvider);
      final user = await account.get();
      final success = await notifier.saveCapture(user.$id);

      if (success && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(l10n.captureFormSaved),
            backgroundColor: Colors.green,
          ),
        );
        // Navegar de vuelta al mapa
        context.go('/map');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final captureState = ref.watch(captureFormProvider);
    final isFromAI = widget.aiResult != null;
    final lowConfidence = widget.aiResult != null &&
        widget.aiResult!.confidence < 0.70;

    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(
          isFromAI
              ? (lowConfidence
                  ? context.l10n.captureFormTitle
                  : context.l10n.captureFormTitleComplete)
              : context.l10n.captureFormTitleRegister,
          style: const TextStyle(color: Colors.white),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Banner informativo
              if (lowConfidence) _buildLowConfidenceBanner(),
              if (isFromAI && !lowConfidence) _buildAiResultBanner(),

              const SizedBox(height: 24),

              // Campos del formulario
              CaptureFormFields(
                speciesController: _speciesController,
                lengthController: _lengthController,
                weightController: _weightController,
                colorController: _colorController,
                featuresController: _featuresController,
                notesController: _notesController,
                latitudeController: _latController,
                longitudeController: _lngController,
                selectedCondition: _selectedCondition,
                onConditionChanged: (value) {
                  setState(() => _selectedCondition = value);
                },
                speciesReadOnly: isFromAI && !lowConfidence,
              ),

              const SizedBox(height: 32),

              // Error message
              if (captureState.errorMessage != null)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.red.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.red.withOpacity(0.3)),
                  ),
                  child: Text(
                    captureState.errorMessage!,
                    style: const TextStyle(color: Colors.red, fontSize: 13),
                  ),
                ),

              // Botón guardar
              SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton(
                  onPressed: captureState.isLoading ? null : _handleSave,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.successGreen,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                  child: captureState.isLoading
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : Text(
                          context.l10n.captureFormSaveButton,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 1,
                            color: Colors.white,
                          ),
                        ),
                ),
              ),

              const SizedBox(height: 40),
            ],
          ),
        ),
      ),
    );
  }

  /// Banner cuando la IA tiene baja confianza
  Widget _buildLowConfidenceBanner() {
    final percent =
        ((widget.aiResult?.confidence ?? 0) * 100).toInt();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.orange.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.orange.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded, color: Colors.orange),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.captureFormLowConfidence,
                  style: const TextStyle(
                    color: Colors.orange,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  context.l10n.captureFormLowConfidenceDesc(percent),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Banner cuando la IA identificó correctamente
  Widget _buildAiResultBanner() {
    final percent =
        ((widget.aiResult?.confidence ?? 0) * 100).toInt();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.green.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.green.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.check_circle, color: Colors.green),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  context.l10n.captureFormAiBanner(
                      widget.aiResult?.species ?? ''),
                  style: const TextStyle(
                    color: Colors.green,
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  context.l10n.captureFormAiBannerDesc(percent),
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
