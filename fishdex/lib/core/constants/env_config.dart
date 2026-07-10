/// Environment configuration for FishDex.
///
/// Values are injected at compile time via `--dart-define` flags.
/// Defaults match the current hardcoded values so the app works
/// out-of-the-box without any flags.
///
/// Usage:
///   flutter run \
///     --dart-define=APPWRITE_ENDPOINT=https://fra.cloud.appwrite.io/v1 \
///     --dart-define=APPWRITE_PROJECT_ID=6a43bdeb0026006ff2f8 \
///     --dart-define=AI_SERVER_URL=http://160.217.215.92:8000 \
///     --dart-define=DATABASE_ID=fishdex_db
class EnvConfig {
  EnvConfig._();

  /// Appwrite API endpoint.
  static const String appwriteEndpoint = String.fromEnvironment(
    'APPWRITE_ENDPOINT',
    defaultValue: 'https://fra.cloud.appwrite.io/v1',
  );

  /// Appwrite project identifier.
  static const String appwriteProjectId = String.fromEnvironment(
    'APPWRITE_PROJECT_ID',
    defaultValue: '6a43bdeb0026006ff2f8',
  );

  /// Base URL of the AI identification server.
  /// Default points to the local Windows development server (localhost).
  /// For mobile device testing on same network, override with your PC's LAN IP:
  ///   --dart-define=AI_SERVER_URL=http://192.168.x.x:8000
  static const String aiServerUrl = String.fromEnvironment(
    'AI_SERVER_URL',
    defaultValue: 'http://160.217.215.92:8000',
  );

  /// Appwrite database identifier.
  static const String databaseId = String.fromEnvironment(
    'DATABASE_ID',
    defaultValue: 'fishdex_db',
  );
}
