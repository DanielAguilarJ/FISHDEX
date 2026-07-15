import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _localePrefsKey = 'selected_locale';

final sharedPreferencesProvider = Provider<SharedPreferences>((ref) {
  throw UnimplementedError('SharedPreferences must be overridden in main.dart');
});

final localeProvider =
    StateNotifierProvider<LocaleNotifier, Locale>((ref) {
  final prefs = ref.watch(sharedPreferencesProvider);
  return LocaleNotifier(prefs);
});

class LocaleNotifier extends StateNotifier<Locale> {
  final SharedPreferences prefs;

  LocaleNotifier(this.prefs)
      : super(Locale(prefs.getString(_localePrefsKey) ?? 'en'));

  Future<void> setLocale(Locale locale) async {
    final code = locale.languageCode;

    if (!['en', 'es', 'cs'].contains(code)) {
      state = const Locale('en');
      await prefs.setString(_localePrefsKey, 'en');
      return;
    }

    state = Locale(code);
    await prefs.setString(_localePrefsKey, code);
  }
}
