import 'package:appwrite/appwrite.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../constants/app_constants.dart';

/// Cliente Appwrite global (para acceso rápido como ping)
final Client appwriteClient = Client()
    .setEndpoint(AppConstants.appwriteEndpoint)
    .setProject(AppConstants.appwriteProjectId);

/// Provider del cliente Appwrite (singleton)
final appwriteClientProvider = Provider<Client>((ref) {
  return appwriteClient;
});

/// Provider del servicio de Account (autenticación)
final appwriteAccountProvider = Provider<Account>((ref) {
  final client = ref.watch(appwriteClientProvider);
  return Account(client);
});

/// Provider del servicio de Databases
final appwriteDatabasesProvider = Provider<Databases>((ref) {
  final client = ref.watch(appwriteClientProvider);
  return Databases(client);
});

/// Provider del servicio de Storage
final appwriteStorageProvider = Provider<Storage>((ref) {
  final client = ref.watch(appwriteClientProvider);
  return Storage(client);
});

/// Provider del servicio de Realtime
final appwriteRealtimeProvider = Provider<Realtime>((ref) {
  final client = ref.watch(appwriteClientProvider);
  return Realtime(client);
});

/// Provider del servicio de Functions (Cloud Functions)
final appwriteFunctionsProvider = Provider<Functions>((ref) {
  final client = ref.watch(appwriteClientProvider);
  return Functions(client);
});
