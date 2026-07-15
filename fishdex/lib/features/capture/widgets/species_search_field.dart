import 'package:flutter/material.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';
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

  String _speciesDisplayName(CzechSpecies species, String languageCode) {
    if (languageCode == 'cs') {
      return '${species.czechName} (${species.englishName})';
    } else {
      return '${species.englishName} (${species.czechName})';
    }
  }

  String _localizedRarity(BuildContext context, String rarity) {
    final l10n = context.l10n;
    switch (rarity) {
      case 'uncommon':
        return l10n.rarityUncommon;
      case 'rare':
        return l10n.rarityRare;
      case 'legendary':
        return l10n.rarityLegendary;
      case 'common':
      default:
        return l10n.rarityCommon;
    }
  }

  @override
  Widget build(BuildContext context) {
    final languageCode = Localizations.localeOf(context).languageCode;

    return Autocomplete<CzechSpecies>(
      initialValue: TextEditingValue(
        text: initialSpecies != null ? _speciesDisplayName(initialSpecies!, languageCode) : '',
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
          _speciesDisplayName(option, languageCode),
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
            labelText: context.l10n.speciesSearchLabel,
            hintText: context.l10n.speciesSearchHint,
            prefixIcon: const Icon(Icons.search, color: AppTheme.accentBlue),
            suffixIcon: IconButton(
              icon: const Icon(Icons.clear, color: Colors.white54),
              onPressed: () {
                textEditingController.clear();
                onSelected(null);
              },
            ),
          ),
          onChanged: (value) {
            if (value.trim().isEmpty) {
              onSelected(null);
              return;
            }
            final exactMatch = czechFishCatalog.any((s) =>
                _speciesDisplayName(s, languageCode).toLowerCase() ==
                value.trim().toLowerCase());
            if (!exactMatch) {
              onSelected(null);
            }
          },
          validator: (value) {
            if (value == null || value.trim().isEmpty) {
              return null;
            }
            // Validar que la especie escrita coincida con alguna del catálogo
            final exists = czechFishCatalog.any((s) =>
                _speciesDisplayName(s, languageCode).toLowerCase() ==
                value.trim().toLowerCase());
            if (!exists) {
              return context.l10n.speciesSearchInvalid;
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
                  final isCzech = languageCode == 'cs';
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
                                  isCzech ? option.czechName : option.englishName,
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                Text(
                                  isCzech
                                      ? '${option.englishName} • ${option.latinName}'
                                      : '${option.czechName} • ${option.latinName}',
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
                              _localizedRarity(context, option.rarity).toUpperCase(),
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
