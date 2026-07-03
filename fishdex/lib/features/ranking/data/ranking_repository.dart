import 'package:appwrite/appwrite.dart';
import 'package:flutter/foundation.dart';
import '../../../core/constants/app_constants.dart';

// =============================================================================
// MODELOS DE DATOS
// =============================================================================

/// Datos de un jugador en el ranking
class RankerData {
  final String userId;
  final String name;
  final int level;
  final String? avatarUrl;
  final double value;
  final int position;
  final bool isCurrentUser;

  const RankerData({
    required this.userId,
    required this.name,
    required this.level,
    this.avatarUrl,
    required this.value,
    required this.position,
    this.isCurrentUser = false,
  });
}

/// Posición del usuario actual en cada categoría
class UserRankPosition {
  final int xpPosition;
  final int speciesPosition;
  final int biggestPosition;
  final int totalXp;
  final int uniqueSpecies;
  final double biggestFishCm;

  const UserRankPosition({
    this.xpPosition = -1,
    this.speciesPosition = -1,
    this.biggestPosition = -1,
    this.totalXp = 0,
    this.uniqueSpecies = 0,
    this.biggestFishCm = 0.0,
  });
}

// =============================================================================
// REPOSITORIO DE RANKING
// =============================================================================

class RankingRepository {
  final Databases _databases;

  RankingRepository({required Databases databases}) : _databases = databases;

  // ---------------------------------------------------------------------------
  // LEADERBOARD POR XP TOTAL
  // ---------------------------------------------------------------------------

  /// Obtiene el top N jugadores ordenados por XP total.
  /// Hace JOIN manual con perfiles para obtener username y avatar.
  Future<List<RankerData>> getXpLeaderboard({
    int limit = 50,
    String period = 'all_time',
    String? currentUserId,
  }) async {
    try {
      final queries = <String>[
        Query.orderDesc('xp_total'),
        Query.limit(limit),
      ];

      // Filtro por período
      final periodFilter = _buildPeriodFilter(period, 'updated_at');
      if (periodFilter != null) queries.add(periodFilter);

      final result = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.leaderboardsCollection,
        queries: queries,
      );

      if (result.documents.isEmpty) return [];

      // Obtener perfiles de los usuarios
      final userIds =
          result.documents.map((d) => d.data['user_id'] as String).toList();
      final profiles = await _fetchProfiles(userIds);

      // Construir lista de rankers
      final rankers = <RankerData>[];
      for (int i = 0; i < result.documents.length; i++) {
        final doc = result.documents[i];
        final userId = doc.data['user_id'] as String;
        final profile = profiles[userId];

        rankers.add(RankerData(
          userId: userId,
          name: profile?['username'] ?? 'Pescador',
          level: (doc.data['level'] as num?)?.toInt() ?? 1,
          avatarUrl: profile?['avatarUrl'],
          value: (doc.data['xp_total'] as num?)?.toDouble() ?? 0.0,
          position: i + 1,
          isCurrentUser: userId == currentUserId,
        ));
      }

      return rankers;
    } catch (e) {
      debugPrint('⚠️ Error getXpLeaderboard: $e');
      return [];
    }
  }

  // ---------------------------------------------------------------------------
  // LEADERBOARD POR ESPECIES ÚNICAS
  // ---------------------------------------------------------------------------

  /// Obtiene el top N por número de especies únicas descubiertas.
  Future<List<RankerData>> getSpeciesLeaderboard({
    int limit = 50,
    String period = 'all_time',
    String? currentUserId,
  }) async {
    try {
      final queries = <String>[
        Query.orderDesc('unique_species'),
        Query.limit(limit),
      ];

      // Para el filtro semanal/mensual no aplica directamente a 'users',
      // ya que no tiene campo de fecha. Usamos 'all_time' como fallback.
      // En un futuro se podría filtrar por sightings en período.

      final result = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        queries: queries,
      );

      if (result.documents.isEmpty) return [];

      // Los documentos de 'users' tienen el $id como user_id
      final userIds = result.documents.map((d) => d.$id).toList();
      final profiles = await _fetchProfiles(userIds);

      final rankers = <RankerData>[];
      for (int i = 0; i < result.documents.length; i++) {
        final doc = result.documents[i];
        final userId = doc.$id;
        final profile = profiles[userId];

        rankers.add(RankerData(
          userId: userId,
          name: profile?['username'] ?? 'Pescador',
          level: (doc.data['level'] as num?)?.toInt() ?? 1,
          avatarUrl: profile?['avatarUrl'],
          value: (doc.data['unique_species'] as num?)?.toDouble() ?? 0.0,
          position: i + 1,
          isCurrentUser: userId == currentUserId,
        ));
      }

      return rankers;
    } catch (e) {
      debugPrint('⚠️ Error getSpeciesLeaderboard: $e');
      return [];
    }
  }

  // ---------------------------------------------------------------------------
  // LEADERBOARD POR PEZ MÁS GRANDE
  // ---------------------------------------------------------------------------

  /// Obtiene el top N por tamaño del pez más grande capturado.
  /// Consulta fish_sightings ordenado por tamaño y agrupa por usuario.
  Future<List<RankerData>> getBiggestFishLeaderboard({
    int limit = 50,
    String period = 'all_time',
    String? currentUserId,
  }) async {
    try {
      final queries = <String>[
        Query.orderDesc('estimated_size_cm'),
        Query.limit(200), // Traer más para poder agrupar por usuario
      ];

      final periodFilter = _buildPeriodFilter(period, 'created_at');
      if (periodFilter != null) queries.add(periodFilter);

      final result = await _databases.listDocuments(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.fishSightingsCollection,
        queries: queries,
      );

      if (result.documents.isEmpty) return [];

      // Agrupar por usuario, quedarse con el pez más grande de cada uno
      final Map<String, double> userMaxSize = {};
      for (final doc in result.documents) {
        final userId = doc.data['user_id'] as String;
        final size = (doc.data['estimated_size_cm'] as num?)?.toDouble() ?? 0.0;
        if (!userMaxSize.containsKey(userId) || size > userMaxSize[userId]!) {
          userMaxSize[userId] = size;
        }
      }

      // Ordenar por tamaño descendente y limitar
      final sortedEntries = userMaxSize.entries.toList()
        ..sort((a, b) => b.value.compareTo(a.value));
      final topEntries = sortedEntries.take(limit).toList();

      // Obtener perfiles
      final userIds = topEntries.map((e) => e.key).toList();
      final profiles = await _fetchProfiles(userIds);

      final rankers = <RankerData>[];
      for (int i = 0; i < topEntries.length; i++) {
        final entry = topEntries[i];
        final profile = profiles[entry.key];

        rankers.add(RankerData(
          userId: entry.key,
          name: profile?['username'] ?? 'Pescador',
          level: 1, // No disponible directamente aquí
          avatarUrl: profile?['avatarUrl'],
          value: entry.value,
          position: i + 1,
          isCurrentUser: entry.key == currentUserId,
        ));
      }

      return rankers;
    } catch (e) {
      debugPrint('⚠️ Error getBiggestFishLeaderboard: $e');
      return [];
    }
  }

  // ---------------------------------------------------------------------------
  // POSICIÓN DEL USUARIO ACTUAL
  // ---------------------------------------------------------------------------

  /// Calcula la posición del usuario en cada categoría de ranking.
  Future<UserRankPosition> getCurrentUserPosition(String userId) async {
    try {
      int xpPosition = -1;
      int speciesPosition = -1;
      int biggestPosition = -1;
      int totalXp = 0;
      int uniqueSpecies = 0;
      double biggestFishCm = 0.0;

      // Posición en XP (contar cuántos tienen más XP)
      try {
        final userLeaderboard = await _databases.listDocuments(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.leaderboardsCollection,
          queries: [
            Query.equal('user_id', userId),
            Query.limit(1),
          ],
        );
        if (userLeaderboard.documents.isNotEmpty) {
          totalXp =
              (userLeaderboard.documents.first.data['xp_total'] as num?)
                      ?.toInt() ??
                  0;

          // Contar usuarios con más XP
          final above = await _databases.listDocuments(
            databaseId: AppConstants.databaseId,
            collectionId: AppConstants.leaderboardsCollection,
            queries: [
              Query.greaterThan('xp_total', totalXp),
              Query.limit(1),
            ],
          );
          xpPosition = above.total + 1;
        }
      } catch (_) {}

      // Posición en especies
      try {
        final userDoc = await _databases.getDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.usersCollection,
          documentId: userId,
        );
        uniqueSpecies =
            (userDoc.data['unique_species'] as num?)?.toInt() ?? 0;

        final above = await _databases.listDocuments(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.usersCollection,
          queries: [
            Query.greaterThan('unique_species', uniqueSpecies),
            Query.limit(1),
          ],
        );
        speciesPosition = above.total + 1;
      } catch (_) {}

      // Posición en pez más grande
      try {
        final userSightings = await _databases.listDocuments(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.fishSightingsCollection,
          queries: [
            Query.equal('user_id', userId),
            Query.orderDesc('estimated_size_cm'),
            Query.limit(1),
          ],
        );
        if (userSightings.documents.isNotEmpty) {
          biggestFishCm = (userSightings.documents.first
                      .data['estimated_size_cm'] as num?)
                  ?.toDouble() ??
              0.0;

          final above = await _databases.listDocuments(
            databaseId: AppConstants.databaseId,
            collectionId: AppConstants.fishSightingsCollection,
            queries: [
              Query.greaterThan('estimated_size_cm', biggestFishCm),
              Query.limit(1),
            ],
          );
          // Esto cuenta sightings, no usuarios únicos, pero es una aprox.
          biggestPosition = above.total + 1;
        }
      } catch (_) {}

      return UserRankPosition(
        xpPosition: xpPosition,
        speciesPosition: speciesPosition,
        biggestPosition: biggestPosition,
        totalXp: totalXp,
        uniqueSpecies: uniqueSpecies,
        biggestFishCm: biggestFishCm,
      );
    } catch (e) {
      debugPrint('⚠️ Error getCurrentUserPosition: $e');
      return const UserRankPosition();
    }
  }

  // ---------------------------------------------------------------------------
  // HELPERS PRIVADOS
  // ---------------------------------------------------------------------------

  /// Obtiene perfiles (username, avatarUrl) para una lista de user IDs.
  /// Retorna un Map<userId, Map<campo, valor>>.
  Future<Map<String, Map<String, dynamic>>> _fetchProfiles(
    List<String> userIds,
  ) async {
    final Map<String, Map<String, dynamic>> profiles = {};
    if (userIds.isEmpty) return profiles;

    try {
      // Appwrite tiene límite de 100 por query, dividimos en batches
      final batches = <List<String>>[];
      for (int i = 0; i < userIds.length; i += 25) {
        batches.add(userIds.sublist(
          i,
          i + 25 > userIds.length ? userIds.length : i + 25,
        ));
      }

      for (final batch in batches) {
        try {
          final result = await _databases.listDocuments(
            databaseId: AppConstants.databaseId,
            collectionId: AppConstants.usersCollection,
            queries: [
              Query.equal('\$id', batch),
              Query.limit(25),
            ],
          );
          for (final doc in result.documents) {
            profiles[doc.$id] = doc.data;
          }
        } catch (_) {
          // Si falla un batch, continuar con los demás
        }
      }
    } catch (e) {
      debugPrint('⚠️ Error fetchProfiles: $e');
    }

    return profiles;
  }

  /// Construye filtro de período para queries de Appwrite.
  String? _buildPeriodFilter(String period, String fieldName) {
    switch (period) {
      case 'weekly':
        final weekAgo =
            DateTime.now().subtract(const Duration(days: 7)).toIso8601String();
        return Query.greaterThan(fieldName, weekAgo);
      case 'monthly':
        final monthAgo =
            DateTime.now().subtract(const Duration(days: 30)).toIso8601String();
        return Query.greaterThan(fieldName, monthAgo);
      default:
        return null;
    }
  }
}
