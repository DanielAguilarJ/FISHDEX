import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';

// =============================================================================
// CAMPOS REUTILIZABLES DEL FORMULARIO DE CAPTURA
// =============================================================================

/// Widget con todos los campos del formulario de captura de pez.
/// Se usa tanto en el resultado post-IA como en el formulario manual.
class CaptureFormFields extends StatelessWidget {
  final TextEditingController speciesController;
  final TextEditingController lengthController;
  final TextEditingController weightController;
  final TextEditingController colorController;
  final TextEditingController featuresController;
  final TextEditingController notesController;
  final TextEditingController latitudeController;
  final TextEditingController longitudeController;
  final String? selectedCondition;
  final ValueChanged<String?> onConditionChanged;
  final bool showLocationFields;
  final bool speciesReadOnly;

  const CaptureFormFields({
    super.key,
    required this.speciesController,
    required this.lengthController,
    required this.weightController,
    required this.colorController,
    required this.featuresController,
    required this.notesController,
    required this.latitudeController,
    required this.longitudeController,
    required this.selectedCondition,
    required this.onConditionChanged,
    this.showLocationFields = true,
    this.speciesReadOnly = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // === ESPECIE ===
        _buildSectionLabel(context.l10n.captureFieldSpecies),
        const SizedBox(height: 8),
        TextFormField(
          controller: speciesController,
          readOnly: speciesReadOnly,
          style: const TextStyle(color: Colors.white),
          decoration: _buildInputDecoration(
            hint: context.l10n.captureFieldSpeciesHint,
            icon: Icons.pets,
          ),
          validator: (value) {
            if (value == null || value.trim().isEmpty) {
              return context.l10n.captureFieldSpeciesRequired;
            }
            return null;
          },
        ),

        const SizedBox(height: 20),

        // === LONGITUD ===
        _buildSectionLabel(context.l10n.captureFieldLength),
        const SizedBox(height: 8),
        TextFormField(
          controller: lengthController,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
          ],
          style: const TextStyle(color: Colors.white),
          decoration: _buildInputDecoration(
            hint: context.l10n.captureFieldLengthHint,
            icon: Icons.straighten,
            suffix: 'cm',
          ),
          validator: (value) {
            if (value == null || value.trim().isEmpty) {
              return context.l10n.captureFieldLengthRequired;
            }
            final num = double.tryParse(value);
            if (num == null || num <= 0) {
              return context.l10n.captureFieldLengthInvalid;
            }
            return null;
          },
        ),

        const SizedBox(height: 20),

        // === PESO (opcional) ===
        _buildSectionLabel(context.l10n.captureFieldWeight),
        const SizedBox(height: 8),
        TextFormField(
          controller: weightController,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
          ],
          style: const TextStyle(color: Colors.white),
          decoration: _buildInputDecoration(
            hint: context.l10n.captureFieldWeightHint,
            icon: Icons.monitor_weight_outlined,
            suffix: 'kg',
          ),
        ),

        const SizedBox(height: 20),

        // === COLOR (opcional) ===
        _buildSectionLabel(context.l10n.captureFieldColor),
        const SizedBox(height: 8),
        TextFormField(
          controller: colorController,
          style: const TextStyle(color: Colors.white),
          decoration: _buildInputDecoration(
            hint: context.l10n.captureFieldColorHint,
            icon: Icons.color_lens_outlined,
          ),
        ),

        const SizedBox(height: 20),

        // === CONDICIÓN ===
        _buildSectionLabel(context.l10n.captureFieldCondition),
        const SizedBox(height: 8),
        _buildConditionSelector(context),

        const SizedBox(height: 20),

        // === CARACTERÍSTICAS FÍSICAS (opcional) ===
        _buildSectionLabel(context.l10n.captureFieldFeatures),
        const SizedBox(height: 8),
        TextFormField(
          controller: featuresController,
          maxLines: 2,
          style: const TextStyle(color: Colors.white),
          decoration: _buildInputDecoration(
            hint: context.l10n.captureFieldFeaturesHint,
            icon: Icons.description_outlined,
          ),
        ),

        const SizedBox(height: 20),

        // === NOTAS (opcional) ===
        _buildSectionLabel(context.l10n.captureFieldNotes),
        const SizedBox(height: 8),
        TextFormField(
          controller: notesController,
          maxLines: 3,
          style: const TextStyle(color: Colors.white),
          decoration: _buildInputDecoration(
            hint: context.l10n.captureFieldNotesHint,
            icon: Icons.note_outlined,
          ),
        ),

        // === UBICACIÓN ===
        if (showLocationFields) ...[
          const SizedBox(height: 20),
          _buildSectionLabel(context.l10n.captureFieldGps),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: TextFormField(
                  controller: latitudeController,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: _buildInputDecoration(
                    hint: context.l10n.captureFieldLatitude,
                    icon: Icons.location_on_outlined,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextFormField(
                  controller: longitudeController,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                  decoration: _buildInputDecoration(
                    hint: context.l10n.captureFieldLongitude,
                    icon: Icons.location_on_outlined,
                  ),
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }

  /// Selector de condición (alive/released/dead)
  Widget _buildConditionSelector(BuildContext context) {
    return Row(
      children: [
        _buildConditionChip(
            context, 'alive', context.l10n.captureConditionAlive,
            Icons.favorite, Colors.green),
        const SizedBox(width: 8),
        _buildConditionChip(
            context, 'released', context.l10n.captureConditionReleased,
            Icons.waves, Colors.blue),
        const SizedBox(width: 8),
        _buildConditionChip(
            context, 'dead', context.l10n.captureConditionDead,
            Icons.close, Colors.red),
      ],
    );
  }

  Widget _buildConditionChip(
    BuildContext context,
    String value,
    String label,
    IconData icon,
    Color color,
  ) {
    final isSelected = selectedCondition == value;
    return Expanded(
      child: GestureDetector(
        onTap: () => onConditionChanged(value),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: isSelected
                ? color.withOpacity(0.2)
                : Colors.white.withOpacity(0.05),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSelected ? color : Colors.white.withOpacity(0.1),
              width: isSelected ? 1.5 : 1,
            ),
          ),
          child: Column(
            children: [
              Icon(icon, color: isSelected ? color : Colors.white54, size: 20),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  color: isSelected ? color : Colors.white54,
                  fontSize: 11,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSectionLabel(String label) {
    return Text(
      label,
      style: TextStyle(
        color: Colors.white.withOpacity(0.8),
        fontSize: 14,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  InputDecoration _buildInputDecoration({
    required String hint,
    required IconData icon,
    String? suffix,
  }) {
    return InputDecoration(
      hintText: hint,
      hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
      prefixIcon: Icon(icon, color: Colors.white.withOpacity(0.4), size: 20),
      suffixText: suffix,
      suffixStyle: TextStyle(color: Colors.white.withOpacity(0.5)),
      filled: true,
      fillColor: Colors.white.withOpacity(0.05),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: AppTheme.accentBlue),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: Colors.red),
      ),
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    );
  }
}
