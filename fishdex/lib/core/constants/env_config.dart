import 'package:flutter/foundation.dart';

/// Compile-time environment configuration for FishDex.
///
/// Values are injected with `--dart-define` at build time.
///
/// ## Why there are no production defaults here
///
/// Anything compiled into the binary is extractable from the APK/IPA with
/// standard tooling — `strings`, `apktool`, or a hex editor. This file used to
/// ship the production server IP, the Appwrite project id, and an
/// `AI_SERVER_SECRET` default of `'change-me'`, which meant a release build with
/// no `--dart-define` flags authenticated against the real API with a guessable
/// secret.
///
/// Defaults now point at localhost and are **debug-only**. A release build that
/// omits the required flags fails fast via [assertConfigured] instead of silently
/// talking to the wrong host with a placeholder credential.
///
/// ## Building
///
/// Development (defaults are fine):
/// ```sh
/// flutter run
/// ```
///
/// Release:
/// ```sh
/// flutter build apk --release \
///   --dart-define=AI_SERVER_URL=https://ai.example.org \
///   --dart-define=AI_SERVER_SECRET="$FISHDEX_CLIENT_SECRET" \
///   --dart-define=APPWRITE_ENDPOINT=https://fra.cloud.appwrite.io/v1 \
///   --dart-define=APPWRITE_PROJECT_ID="$APPWRITE_PROJECT_ID" \
///   --dart-define=DATABASE_ID=fishdex_db
/// ```
///
/// Note that a shared client secret only identifies the *application*, never a
/// user. The server treats it accordingly: per-user data requires the session
/// token obtained from `POST /api/v1/auth/login`.
class EnvConfig {
  EnvConfig._();

  /// Placeholder that must never survive into a release build.
  static const String _unset = '';

  /// Loopback default used only in debug builds.
  ///
  /// `10.0.2.2` is the host machine as seen from the Android emulator; on iOS
  /// simulators and desktop, `localhost` resolves correctly.
  static const String _debugAiServerUrl = 'http://10.0.2.2:8000';

  /// Base URL of the AI identification server.
  ///
  /// Override with `--dart-define=AI_SERVER_URL=https://your-host`.
  /// Must be `https://` in release builds; see [assertConfigured].
  static const String aiServerUrl = String.fromEnvironment(
    'AI_SERVER_URL',
    defaultValue: _unset,
  );

  /// Shared client secret presented as `X-FishDex-Client-Secret`.
  ///
  /// Override with `--dart-define=AI_SERVER_SECRET=...`. No default: an empty
  /// value makes the server reject the request, which is the correct outcome for
  /// a misconfigured build.
  static const String aiServerSecret = String.fromEnvironment(
    'AI_SERVER_SECRET',
    defaultValue: _unset,
  );

  /// Appwrite API endpoint.
  static const String appwriteEndpoint = String.fromEnvironment(
    'APPWRITE_ENDPOINT',
    defaultValue: _unset,
  );

  /// Appwrite project identifier.
  static const String appwriteProjectId = String.fromEnvironment(
    'APPWRITE_PROJECT_ID',
    defaultValue: _unset,
  );

  /// Appwrite database identifier.
  static const String databaseId = String.fromEnvironment(
    'DATABASE_ID',
    defaultValue: 'fishdex_db',
  );

  /// Effective AI server URL, falling back to loopback in debug builds only.
  static String get resolvedAiServerUrl {
    if (aiServerUrl.isNotEmpty) return aiServerUrl;
    return kReleaseMode ? _unset : _debugAiServerUrl;
  }

  /// Whether the app has everything it needs to reach the API.
  static bool get isConfigured =>
      resolvedAiServerUrl.isNotEmpty && aiServerSecret.isNotEmpty;

  /// Whether the configured server URL is encrypted.
  static bool get usesTls => resolvedAiServerUrl.startsWith('https://');

  /// Human-readable list of missing or unsafe settings.
  ///
  /// Returns an empty list when the configuration is usable.
  static List<String> get configurationProblems {
    final problems = <String>[];
    if (resolvedAiServerUrl.isEmpty) {
      problems.add('AI_SERVER_URL is not set');
    }
    if (aiServerSecret.isEmpty) {
      problems.add('AI_SERVER_SECRET is not set');
    }
    if (kReleaseMode && !usesTls) {
      problems.add('AI_SERVER_URL must use https:// in release builds');
    }
    return problems;
  }

  /// Fail fast on a misconfigured build.
  ///
  /// Call once during startup, before any network client is constructed.
  /// Throws [StateError] in release builds; logs a warning in debug builds so
  /// local development against a plain-HTTP server still works.
  static void assertConfigured() {
    final problems = configurationProblems;
    if (problems.isEmpty) return;

    final message =
        'FishDex environment is not configured correctly:\n'
        '  - ${problems.join('\n  - ')}\n'
        'Pass the missing values with --dart-define. See EnvConfig docs.';

    if (kReleaseMode) {
      throw StateError(message);
    }
    debugPrint('WARNING: $message');
  }
}
