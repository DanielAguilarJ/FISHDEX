import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Encrypted storage for the session token.
///
/// The token used to live in `SharedPreferences`, which is a plain-text XML file
/// on Android and an unencrypted plist on iOS. On a rooted or jailbroken device
/// any process could read it and impersonate the user.
///
/// This wrapper stores it in the Android Keystore (via `EncryptedSharedPreferences`)
/// and the iOS Keychain, and transparently migrates — then deletes — any token
/// left behind by an earlier install.
class SecureTokenStore {
  /// Key under which the token is stored in secure storage.
  static const String _secureKey = 'fishdex_session_token';

  /// Legacy `SharedPreferences` key, read once during migration.
  static const String _legacyKey = 'local_auth_token';

  final FlutterSecureStorage _storage;

  /// Creates a store, optionally with an injected backend for tests.
  SecureTokenStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(
                encryptedSharedPreferences: true,
              ),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            );

  /// Reads the stored token, migrating from `SharedPreferences` if needed.
  ///
  /// Returns `null` when no token is stored.
  Future<String?> read() async {
    try {
      final token = await _storage.read(key: _secureKey);
      if (token != null && token.isNotEmpty) return token;
    } on Exception catch (error, stackTrace) {
      // A corrupt keystore entry must not lock the user out permanently; fall
      // through to the migration path and, failing that, force a fresh login.
      debugPrint('SecureTokenStore.read failed: $error');
      debugPrintStack(stackTrace: stackTrace);
    }
    return _migrateLegacyToken();
  }

  /// Persists [token], or clears storage when it is `null`.
  Future<void> write(String? token) async {
    try {
      if (token == null || token.isEmpty) {
        await _storage.delete(key: _secureKey);
      } else {
        await _storage.write(key: _secureKey, value: token);
      }
    } on Exception catch (error) {
      // Surfaced rather than swallowed: if the token cannot be persisted, the
      // user will be logged out on the next launch and should know why.
      debugPrint('SecureTokenStore.write failed: $error');
      rethrow;
    }
  }

  /// Removes the token from both secure and legacy storage.
  Future<void> clear() async {
    try {
      await _storage.delete(key: _secureKey);
    } on Exception catch (error) {
      debugPrint('SecureTokenStore.clear failed: $error');
    }
    await _removeLegacyToken();
  }

  /// Moves a token written by a pre-encryption build into secure storage.
  ///
  /// Returns the migrated token, or `null` when there was nothing to migrate.
  Future<String?> _migrateLegacyToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final legacyToken = prefs.getString(_legacyKey);
      if (legacyToken == null || legacyToken.isEmpty) return null;

      await _storage.write(key: _secureKey, value: legacyToken);
      // Remove the plain-text copy: leaving it behind would defeat the point.
      await prefs.remove(_legacyKey);
      debugPrint('Migrated session token from SharedPreferences to secure storage');
      return legacyToken;
    } on Exception catch (error) {
      debugPrint('SecureTokenStore migration failed: $error');
      return null;
    }
  }

  /// Deletes the legacy plain-text token, ignoring failures.
  Future<void> _removeLegacyToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_legacyKey);
    } on Exception catch (error) {
      debugPrint('Could not remove legacy token: $error');
    }
  }
}
