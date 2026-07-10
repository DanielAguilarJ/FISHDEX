import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;
import 'package:uuid/uuid.dart';

// =============================================================================
// OFFLINE QUEUE SERVICE — SQLite-backed sighting queue
// =============================================================================

/// Status of a queued sighting row.
enum SightingStatus {
  pending,    // Waiting to be uploaded
  uploading,  // Upload in progress
  synced,     // Successfully synced to server
  failed,     // Upload failed (will be retried)
}

/// Data model for a row in the `pending_sightings` table.
class PendingSighting {
  final int? id;
  final String clientId;
  final String userId;
  final String payload;          // Full JSON blob
  final String? mediaPath;       // Local path to video/photo
  final String status;           // pending | uploading | synced | failed
  final int retryCount;
  final DateTime createdAt;
  final DateTime? lastAttemptAt;
  final String? serverError;

  const PendingSighting({
    this.id,
    required this.clientId,
    required this.userId,
    required this.payload,
    this.mediaPath,
    this.status = 'pending',
    this.retryCount = 0,
    required this.createdAt,
    this.lastAttemptAt,
    this.serverError,
  });

  Map<String, dynamic> toMap() => {
    'client_id': clientId,
    'user_id': userId,
    'payload': payload,
    'media_path': mediaPath,
    'status': status,
    'retry_count': retryCount,
    'created_at': createdAt.toIso8601String(),
    'last_attempt_at': lastAttemptAt?.toIso8601String(),
    'server_error': serverError,
  };

  factory PendingSighting.fromMap(Map<String, dynamic> map) => PendingSighting(
    id: map['id'] as int?,
    clientId: map['client_id'] as String,
    userId: map['user_id'] as String,
    payload: map['payload'] as String,
    mediaPath: map['media_path'] as String?,
    status: map['status'] as String? ?? 'pending',
    retryCount: map['retry_count'] as int? ?? 0,
    createdAt: DateTime.parse(map['created_at'] as String),
    lastAttemptAt: map['last_attempt_at'] != null
        ? DateTime.tryParse(map['last_attempt_at'] as String)
        : null,
    serverError: map['server_error'] as String?,
  );
}

/// SQLite-backed offline queue for sightings that couldn't be uploaded
/// immediately (no network, server down, etc.).
///
/// Uses a singleton so every part of the app shares one DB handle.
class OfflineQueueService {
  OfflineQueueService._();
  static final OfflineQueueService instance = OfflineQueueService._();

  static const String _dbName = 'fishdex_offline_queue.db';
  static const int _dbVersion = 1;
  static const String _table = 'pending_sightings';

  static const _uuid = Uuid();

  Database? _db;

  /// Lazily open (or create) the database.
  Future<Database> get database async {
    if (_db != null) return _db!;
    final dbPath = await getDatabasesPath();
    final path = p.join(dbPath, _dbName);
    _db = await openDatabase(
      path,
      version: _dbVersion,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
    return _db!;
  }

  // ---------------------------------------------------------------------------
  // Schema
  // ---------------------------------------------------------------------------

  Future<void> _onCreate(Database db, int version) async {
    await db.execute('''
      CREATE TABLE $_table (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id     TEXT    NOT NULL UNIQUE,
        user_id       TEXT    NOT NULL,
        payload       TEXT    NOT NULL,
        media_path    TEXT,
        status        TEXT    NOT NULL DEFAULT 'pending',
        retry_count   INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT    NOT NULL,
        last_attempt_at TEXT,
        server_error  TEXT
      )
    ''');

    // Index for fast status lookups during sync
    await db.execute(
      'CREATE INDEX idx_status ON $_table (status)',
    );

    // Store schema version for manual migration checks
    await db.rawQuery('PRAGMA user_version = $_dbVersion');
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    // Future migrations go here.
    // Example: if (oldVersion < 2) { ... ALTER TABLE ... }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /// Generate a new UUID v4 client id for a pending sighting.
  String generateClientId() => _uuid.v4();

  /// Queue a new sighting for later upload.
  ///
  /// Returns the auto-incremented row id.
  Future<int> queue({
    required String userId,
    required String payload,
    String? mediaPath,
    String? clientId,
  }) async {
    final db = await database;
    final sighting = PendingSighting(
      clientId: clientId ?? generateClientId(),
      userId: userId,
      payload: payload,
      mediaPath: mediaPath,
      createdAt: DateTime.now(),
    );
    return db.insert(_table, sighting.toMap());
  }

  /// Retrieve all rows with the given [status] (defaults to 'pending').
  Future<List<PendingSighting>> getByStatus({
    String status = 'pending',
    int limit = 50,
  }) async {
    final db = await database;
    final rows = await db.query(
      _table,
      where: 'status = ?',
      whereArgs: [status],
      orderBy: 'created_at ASC',
      limit: limit,
    );
    return rows.map(PendingSighting.fromMap).toList();
  }

  /// Mark a row as "uploading" so concurrent syncs don't double-send it.
  Future<int> markUploading(int id) async {
    final db = await database;
    return db.update(
      _table,
      {
        'status': 'uploading',
        'last_attempt_at': DateTime.now().toIso8601String(),
      },
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  /// Mark a row as successfully synced.
  Future<int> markSynced(int id) async {
    final db = await database;
    return db.update(
      _table,
      {'status': 'synced'},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  /// Mark a row as failed and increment its retry counter.
  Future<int> markFailed(int id, {String? error}) async {
    final db = await database;
    return db.rawUpdate(
      '''
      UPDATE $_table
         SET status        = 'failed',
             retry_count   = retry_count + 1,
             last_attempt_at = ?,
             server_error  = ?
       WHERE id = ?
      ''',
      [DateTime.now().toIso8601String(), error, id],
    );
  }

  /// Delete synced rows older than [olderThan] (default 7 days).
  Future<int> cleanup({Duration olderThan = const Duration(days: 7)}) async {
    final db = await database;
    final cutoff =
        DateTime.now().subtract(olderThan).toIso8601String();
    return db.delete(
      _table,
      where: "status = 'synced' AND created_at < ?",
      whereArgs: [cutoff],
    );
  }

  /// Number of rows still waiting to be uploaded (pending + failed).
  Future<int> pendingCount() async {
    final db = await database;
    final result = await db.rawQuery(
      "SELECT COUNT(*) AS c FROM $_table WHERE status IN ('pending','failed')",
    );
    return Sqflite.firstIntValue(result) ?? 0;
  }

  /// Close the database (useful in tests).
  Future<void> close() async {
    await _db?.close();
    _db = null;
  }
}
