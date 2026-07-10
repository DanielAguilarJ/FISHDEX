import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../features/auth/providers/auth_provider.dart';
import '../../data/repositories/auth_repository.dart';

/// Mock classes replacing the Appwrite Python/Dart SDK in local mode.
/// This prevents Downstream Widget compile errors and mimics the SDK interfaces.

class MockUser {
  final String $id;
  final String email;
  final String name;

  MockUser({
    required String id,
    required this.email,
    required this.name,
  }) : $id = id;
}

class MockAccount {
  final Ref _ref;
  MockAccount(this._ref);

  Future<MockUser> get() async {
    final user = _ref.read(authStateProvider).value;
    if (user == null) {
      // Simulate Appwrite 401 Unauthorized exception by throwing an object with code
      throw MockAppwriteException('Unauthorized user session', 401);
    }
    return MockUser(
      id: user.id,
      email: user.email,
      name: user.name,
    );
  }

  Future<void> deleteSession({required String sessionId}) async {
    await _ref.read(authRepositoryProvider).logout();
  }
}

class MockAppwriteException implements Exception {
  final String message;
  final int code;

  MockAppwriteException(this.message, this.code);

  @override
  String toString() => 'MockAppwriteException: [$code] $message';
}

class MockDatabases {
  Future<dynamic> getDocument({
    required String databaseId,
    required String collectionId,
    required String documentId,
  }) async {
    throw MockAppwriteException("Appwrite Databases disabled in local mode", 404);
  }

  Future<dynamic> updateDocument({
    required String databaseId,
    required String collectionId,
    required String documentId,
    required Map<String, dynamic> data,
  }) async {
    throw MockAppwriteException("Appwrite Databases disabled in local mode", 404);
  }

  Future<dynamic> createDocument({
    required String databaseId,
    required String collectionId,
    required String documentId,
    required Map<String, dynamic> data,
  }) async {
    throw MockAppwriteException("Appwrite Databases disabled in local mode", 404);
  }

  Future<MockResponse> listDocuments({
    required String databaseId,
    required String collectionId,
    List<dynamic>? queries,
  }) async {
    return MockResponse(documents: []);
  }
}

class MockResponse {
  final List<dynamic> documents;
  MockResponse({required this.documents});
}

class MockStorage {
  Future<dynamic> createFile({
    required String bucketId,
    required String fileId,
    required dynamic file,
  }) async {
    throw MockAppwriteException("Appwrite Storage disabled in local mode", 500);
  }
}

class MockRealtime {
  MockSubscription subscribe(List<String> channels) {
    return MockSubscription();
  }
}

class MockSubscription {
  Stream<MockRealtimeEvent> get stream => const Stream<MockRealtimeEvent>.empty();
}

class MockRealtimeEvent {
  Map<String, dynamic> get payload => {};
}

class MockFunctions {
  Future<dynamic> createExecution({
    required String functionId,
    String? body,
  }) async {
    throw MockAppwriteException("Appwrite Functions disabled in local mode", 500);
  }
}

// Global mock providers
final appwriteClientProvider = Provider<dynamic>((ref) => null);
final appwriteAccountProvider = Provider<MockAccount>((ref) => MockAccount(ref));
final appwriteDatabasesProvider = Provider<MockDatabases>((ref) => MockDatabases());
final appwriteStorageProvider = Provider<MockStorage>((ref) => MockStorage());
final appwriteRealtimeProvider = Provider<MockRealtime>((ref) => MockRealtime());
final appwriteFunctionsProvider = Provider<MockFunctions>((ref) => MockFunctions());
