import 'package:flutter/foundation.dart';

// =============================================================================
// MODELOS DE DATOS
// =============================================================================

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
// REPOSITORIO DE RANKING MOCKEADO LOCAL
// =============================================================================

class RankingRepository {
  RankingRepository({required dynamic databases});

  /// Mock leaderboard by total XP.
  Future<List<RankerData>> getXpLeaderboard({
    int limit = 50,
    String period = 'all_time',
    String? currentUserId,
  }) async {
    return [
      RankerData(
        userId: currentUserId ?? 'current_user',
        name: 'Tú (Local Fisherman)',
        level: 3,
        value: 250,
        position: 1,
        isCurrentUser: true,
      ),
      const RankerData(
        userId: 'user_dummy_1',
        name: 'Daniel (Expert)',
        level: 8,
        value: 1200,
        position: 2,
      ),
      const RankerData(
        userId: 'user_dummy_2',
        name: 'Czech Fisher 22',
        level: 5,
        value: 450,
        position: 3,
      ),
    ]..sort((a, b) => b.value.compareTo(a.value));
  }

  /// Mock leaderboard by species count.
  Future<List<RankerData>> getSpeciesLeaderboard({
    int limit = 50,
    String period = 'all_time',
    String? currentUserId,
  }) async {
    return [
      RankerData(
        userId: currentUserId ?? 'current_user',
        name: 'Tú (Local Fisherman)',
        level: 3,
        value: 2,
        position: 2,
        isCurrentUser: true,
      ),
      const RankerData(
        userId: 'user_dummy_1',
        name: 'Daniel (Expert)',
        level: 8,
        value: 15,
        position: 1,
      ),
      const RankerData(
        userId: 'user_dummy_2',
        name: 'Czech Fisher 22',
        level: 5,
        value: 6,
        position: 3,
      ),
    ]..sort((a, b) => b.value.compareTo(a.value));
  }

  /// Mock leaderboard by biggest fish caught.
  Future<List<RankerData>> getBiggestFishLeaderboard({
    int limit = 50,
    String period = 'all_time',
    String? currentUserId,
  }) async {
    return [
      RankerData(
        userId: currentUserId ?? 'current_user',
        name: 'Tú (Local Fisherman)',
        level: 3,
        value: 45.5,
        position: 3,
        isCurrentUser: true,
      ),
      const RankerData(
        userId: 'user_dummy_1',
        name: 'Daniel (Expert)',
        level: 8,
        value: 120.0,
        position: 1,
      ),
      const RankerData(
        userId: 'user_dummy_2',
        name: 'Czech Fisher 22',
        level: 5,
        value: 82.5,
        position: 2,
      ),
    ]..sort((a, b) => b.value.compareTo(a.value));
  }

  /// Return user position.
  Future<UserRankPosition> getCurrentUserPosition(String userId) async {
    return const UserRankPosition(
      xpPosition: 2,
      speciesPosition: 2,
      biggestPosition: 3,
      totalXp: 250,
      uniqueSpecies: 2,
      biggestFishCm: 45.5,
    );
  }
}
