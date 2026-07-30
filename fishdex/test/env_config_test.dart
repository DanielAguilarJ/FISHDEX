import 'package:fishdex/core/constants/env_config.dart';
import 'package:flutter_test/flutter_test.dart';

/// Regression tests for the compile-time configuration.
///
/// The previous version of [EnvConfig] shipped the production server IP, the
/// Appwrite project id and an `AI_SERVER_SECRET` default of `'change-me'`. All
/// three are extractable from a release APK, so a build with no `--dart-define`
/// flags authenticated against the real API with a guessable secret.
///
/// These tests run without any `--dart-define`, which is exactly the misconfigured
/// case that used to be dangerous.
void main() {
  group('EnvConfig has no baked-in production values', () {
    test('no hardcoded server IP or hostname', () {
      // Only a loopback address is acceptable as a default.
      expect(EnvConfig.resolvedAiServerUrl, isNot(contains('160.217.215.92')));
      expect(
        EnvConfig.resolvedAiServerUrl,
        anyOf(
          isEmpty,
          contains('10.0.2.2'),
          contains('localhost'),
          contains('127.0.0.1'),
        ),
        reason: 'the default server URL must be loopback, never a real host',
      );
    });

    test('no placeholder client secret', () {
      expect(EnvConfig.aiServerSecret, isNot('change-me'));
      expect(EnvConfig.aiServerSecret, isNot('change-me-in-production'));
      expect(
        EnvConfig.aiServerSecret,
        isEmpty,
        reason: 'without --dart-define the secret must be empty, not guessable',
      );
    });

    test('no hardcoded Appwrite project id', () {
      expect(EnvConfig.appwriteProjectId, isNot('6a43bdeb0026006ff2f8'));
      expect(EnvConfig.appwriteProjectId, isEmpty);
    });

    test('no hardcoded Appwrite endpoint', () {
      expect(EnvConfig.appwriteEndpoint, isEmpty);
    });
  });

  group('configuration diagnostics', () {
    test('reports the app as unconfigured when the secret is absent', () {
      expect(EnvConfig.isConfigured, isFalse);
    });

    test('lists every missing setting', () {
      final problems = EnvConfig.configurationProblems;
      expect(problems, isNotEmpty);
      expect(
        problems.any((p) => p.contains('AI_SERVER_SECRET')),
        isTrue,
        reason: 'the missing secret must be reported explicitly',
      );
    });

    test('assertConfigured does not throw in debug builds', () {
      // Debug builds must remain usable against a local plain-HTTP server; the
      // hard failure is reserved for release builds.
      expect(EnvConfig.assertConfigured, returnsNormally);
    });

    test('usesTls is false for a loopback debug default', () {
      expect(EnvConfig.usesTls, isFalse);
    });
  });
}
