import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/czech_fish_catalog.dart';

/// Un campo de selección de especie de pez con autocompletado y búsqueda.
/// Muestra nombres en checo, inglés y latín con su rareza.
class SpeciesSearchField extends StatelessWidget {
  final CzechSpecies? initialSpecies;
  final ValueChanged<CzechSpecies?> onSelected;

  const SpeciesSearchField({
    super.key,
    this.initialSpecies,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Autocomplete<CzechSpecies>(
      initialValue: TextEditingValue(
        text: initialSpecies != null ? '${initialSpecies!.czechName} (${initialSpecies!.englishName})' : '',
      ),
      optionsBuilder: (TextEditingValue textEditingValue) {
        if (textEditingValue.text.isEmpty) {
          return czechFishCatalog;
        }
        final query = textEditingValue.text.toLowerCase();
        return czechFishCatalog.where((CzechSpecies species) {
          return species.czechName.toLowerCase().contains(query) ||
              species.englishName.toLowerCase().contains(query) ||
              species.latinName.toLowerCase().contains(query);
        });
      },
      displayStringForOption: (CzechSpecies option) =>
          '${option.czechName} (${option.englishName})',
      fieldViewBuilder: (
        BuildContext context,
        TextEditingController textEditingController,
        FocusNode focusNode,
        VoidCallback onFieldSubmitted,
      ) {
        return TextFormField(
          controller: textEditingController,
          focusNode: focusNode,
          style: const TextStyle(color: Colors.white),
          decoration: InputDecoration(
            labelText: 'Selecciona una especie',
            hintText: 'Escribe para buscar (ej. Kapr...)',
            prefixIcon: const Icon(Icons.search, color: AppTheme.accentBlue),
            suffixIcon: IconButton(
              icon: const Icon(Icons.clear, color: Colors.white54),
              onPressed: () {
                textEditingController.clear();
                onSelected(null);
              },
            ),
          ),
          validator: (value) {
            if (value == null || value.trim().isEmpty) {
              return 'La especie es obligatoria';
            }
            // Validar que la especie escrita coincida con alguna del catálogo
            final exists = czechFishCatalog.any((s) =>
                '${s.czechName} (${s.englishName})'.toLowerCase() ==
                value.trim().toLowerCase());
            if (!exists) {
              return 'Por favor selecciona una especie válida de la lista';
            }
            return null;
          },
        );
      },
      optionsViewBuilder: (
        BuildContext context,
        AutocompleteOnSelected<CzechSpecies> onSelectedOption,
        Iterable<CzechSpecies> options,
      ) {
        return Align(
          alignment: Alignment.topLeft,
          child: Material(
            elevation: 8,
            color: AppTheme.darkSurfaceElevated,
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: MediaQuery.of(context).size.width - 48,
              constraints: const BoxConstraints(maxHeight: 250),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.accentBlue.withOpacity(0.3)),
              ),
              child: ListView.builder(
                padding: EdgeInsets.zero,
                shrinkWrap: true,
                itemCount: options.length,
                itemBuilder: (BuildContext context, int index) {
                  final option = options.elementAt(index);
                  final rarityColor = AppTheme.getRarityColor(option.rarity);
                  return InkWell(
                    onTap: () => onSelectedOption(option),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 12,
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.phishing, color: AppTheme.accentBlue),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  option.czechName,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                Text(
                                  '${option.englishName} • ${option.latinName}',
                                  style: TextStyle(
                                    color: Colors.white.withOpacity(0.6),
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: rarityColor.withOpacity(0.2),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(color: rarityColor),
                            ),
                            child: Text(
                              option.rarity.toUpperCase(),
                              style: TextStyle(
                                color: rarityColor,
                                fontSize: 10,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        );
      },
      onSelected: (CzechSpecies selection) {
        onSelected(selection);
      },
    );
  }
}
