/// Stub providers — Appwrite has been removed.
/// These providers exist to maintain compilation while the app
/// is migrated to direct AI server communication only.
///
/// TODO: Replace with proper auth system (JWT from AI server, or similar).

import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Stub — no longer backed by Appwrite.
/// Returns null; screens that use this must handle the null case.
final appwriteAccountProvider = Provider<dynamic>((ref) => null);

/// Stub — current user session.
/// Returns null (no auth system active).
final currentUserProvider = FutureProvider<dynamic>((ref) async => null);

/// Stub — current user ID.
/// Returns a placeholder until proper auth is implemented.
final currentUserIdProvider = Provider<String>((ref) => 'local-user');

/// Stub — databases client.
/// Returns null; database operations go through AI server REST API.
final appwriteDatabasesProvider = Provider<dynamic>((ref) => null);

/// Stub — storage client.
/// Returns null; storage is served by AI server.
final appwriteStorageProvider = Provider<dynamic>((ref) => null);

/// Stub — realtime client.
/// Returns null; realtime via WebSocket to AI server.
final appwriteRealtimeProvider = Provider<dynamic>((ref) => null);
