import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'offline_queue_service.dart';

// =============================================================================
// OFFLINE MIGRATION SERVICE — SharedPreferences → SQLite one-time migration
// =============================================================================
//
// Migrates pending sightings from the legacy SharedPreferences queues
// (sightings_repository + cache_service) into the new SQLite-based
// OfflineQueueService.
//
// ─── WHERE TO CALL ───────────────────────────────────────────────────────────
// Call `OfflineMigrationService.migrateIfNeeded()` once at app startup,
// ideally in `main()` or in the root widget's `initState()` AFTER
// `WidgetsFlutterBinding.ensureInitialized()`.
//
// Example:
//   void main() async {
//     WidgetsFlutterBinding.ensureInitialized();
//     final migrated = await OfflineMigrationService.migrateIfNeeded();
//     if (migrated > 0) debugPrint('Migrated $migrated offline sightings');
//     runApp(const FishDexApp());
//   }
// =============================================================================

class OfflineMigrationService {
  OfflineMigrationService._();

  /// SharedPreferences key written by SightingsRepository._saveLocally()
  static const String _legacySightingsKey = 'pending_sightings';

  /// SharedPreferences key written by CacheService.queueSighting()
  static const String _legacyCacheKey = 'cache_pending_sightings';

  /// Flag to avoid re-running the migration after it succeeds.
  static const String _migrationCompleteKey = 'migration_v1_complete';

  /// Runs the one-time migration if it hasn't been done yet.
  ///
  /// 1. Reads from SharedPreferences keys `pending_sightings` and
  ///    `cache_pending_sightings`.
  /// 2. Inserts each item into the SQLite `pending_sightings` table
  ///    via [OfflineQueueService].
  /// 3. Clears the SharedPreferences keys after successful migration.
  /// 4. Stores `migration_v1_complete = true` to avoid re-running.
  ///
  /// Returns the total number of items migrated.
  static Future<int> migrateIfNeeded() async {
    final prefs = await SharedPreferences.getInstance();

    // Already migrated — bail out fast.
    if (prefs.getBool(_migrationCompleteKey) == true) return 0;

    final queue = OfflineQueueService.instance;
    int totalMigrated = 0;

    // ── Migrate SightingsRepository queue ──────────────────────────────
    totalMigrated += await _migrateStringList(
      prefs: prefs,
      key: _legacySightingsKey,
      queue: queue,
    );

    // ── Migrate CacheService queue ─────────────────────────────────────
    totalMigrated += await _migrateJsonString(
      prefs: prefs,
      key: _legacyCacheKey,
      queue: queue,
    );

    // ── Mark migration complete ────────────────────────────────────────
    await prefs.setBool(_migrationCompleteKey, true);

    if (totalMigrated > 0) {
      debugPrint(
        '✅ OfflineMigrationService: migrated $totalMigrated pending '
        'sightings from SharedPreferences → SQLite',
      );
    }

    return totalMigrated;
  }

  /// Migrates items stored as a `List<String>` (each element is a JSON
  /// object string). This is the format used by `SightingsRepository`.
  static Future<int> _migrateStringList({
    required SharedPreferences prefs,
    required String key,
    required OfflineQueueService queue,
  }) async {
    final list = prefs.getStringList(key);
    if (list == null || list.isEmpty) return 0;

    int count = 0;
    for (final itemJson in list) {
      try {
        final data = json.decode(itemJson) as Map<String, dynamic>;
        final userId = data['user_id'] as String? ?? 'unknown';

        await queue.queue(
          userId: userId,
          payload: itemJson,
          clientId: queue.generateClientId(),
        );
        count++;
      } catch (e) {
        debugPrint('⚠️ Migration: skipped invalid entry in $key: $e');
      }
    }

    // Clear the legacy key after successful migration
    await prefs.remove(key);
    return count;
  }

  /// Migrates items stored as a single JSON string encoding a `List<Map>`.
  /// This is the format used by `CacheService`.
  static Future<int> _migrateJsonString({
    required SharedPreferences prefs,
    required String key,
    required OfflineQueueService queue,
  }) async {
    final raw = prefs.getString(key);
    if (raw == null || raw.isEmpty) return 0;

    int count = 0;
    try {
      final items = json.decode(raw) as List<dynamic>;
      for (final item in items) {
        try {
          final data = item as Map<String, dynamic>;
          final userId = data['user_id'] as String? ?? 'unknown';
          final payload = json.encode(data);

          await queue.queue(
            userId: userId,
            payload: payload,
            clientId: queue.generateClientId(),
          );
          count++;
        } catch (e) {
          debugPrint('⚠️ Migration: skipped invalid entry in $key: $e');
        }
      }
    } catch (e) {
      debugPrint('⚠️ Migration: could not parse $key as JSON list: $e');
    }

    // Clear the legacy key after successful migration
    await prefs.remove(key);
    return count;
  }
}
