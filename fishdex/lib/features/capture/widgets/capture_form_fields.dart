import 'package:flutter/material.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../core/theme/app_theme.dart';

/// Reusable form fields for the capture form.
/// Extracted to avoid a monolithic capture_form_screen.
class CaptureFormFields extends StatelessWidget {
  final TextEditingController speciesController;
  final TextEditingController sizeController;
  final TextEditingController notesController;
  final String? selectedWeather;
  final String? selectedBite;
  final ValueChanged<String?> onWeatherChanged;
  final ValueChanged<String?> onBiteChanged;

  const CaptureFormFields({
    super.key,
    required this.speciesController,
    required this.sizeController,
    required this.notesController,
    this.selectedWeather,
    this.selectedBite,
    required this.onWeatherChanged,
    required this.onBiteChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Species field
        TextField(
          controller: speciesController,
          decoration: InputDecoration(
            labelText: context.l10n.captureSpecies,
            prefixIcon: const Icon(Icons.pets),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
        const SizedBox(height: 16),

        // Size field
        TextField(
          controller: sizeController,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: context.l10n.captureSize,
            suffixText: 'cm',
            prefixIcon: const Icon(Icons.straighten),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
        const SizedBox(height: 16),

        // Weather dropdown
        DropdownButtonFormField<String>(
          value: selectedWeather,
          onChanged: onWeatherChanged,
          decoration: InputDecoration(
            labelText: context.l10n.captureWeather,
            prefixIcon: const Icon(Icons.wb_sunny),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          items: const [
            DropdownMenuItem(value: 'sunny', child: Text('Sunny')),
            DropdownMenuItem(value: 'cloudy', child: Text('Cloudy')),
            DropdownMenuItem(value: 'rainy', child: Text('Rainy')),
            DropdownMenuItem(value: 'overcast', child: Text('Overcast')),
          ],
        ),
        const SizedBox(height: 16),

        // Bait dropdown
        DropdownButtonFormField<String>(
          value: selectedBite,
          onChanged: onBiteChanged,
          decoration: InputDecoration(
            labelText: context.l10n.captureBite,
            prefixIcon: const Icon(Icons.catching_pokemon),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          items: const [
            DropdownMenuItem(value: 'worm', child: Text('Worm')),
            DropdownMenuItem(value: 'spinner', child: Text('Spinner')),
            DropdownMenuItem(value: 'fly', child: Text('Fly')),
            DropdownMenuItem(value: 'dough', child: Text('Dough')),
            DropdownMenuItem(value: 'corn', child: Text('Corn')),
            DropdownMenuItem(value: 'other', child: Text('Other')),
          ],
        ),
        const SizedBox(height: 16),

        // Notes field
        TextField(
          controller: notesController,
          maxLines: 3,
          decoration: InputDecoration(
            labelText: context.l10n.captureNotes,
            prefixIcon: const Icon(Icons.note),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
      ],
    );
  }
}
