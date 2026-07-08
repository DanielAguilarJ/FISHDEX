import 'package:flutter/material.dart';
import '../../l10n/app_localizations.dart';

/// Extension para acceder fácilmente a las traducciones desde el context
extension AppLocalizationsX on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}
