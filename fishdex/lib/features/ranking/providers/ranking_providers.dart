import 'package:equatable/equatable.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../auth/providers/auth_provider.dart';
import '../data/ranking_repository.dart';

// =============================================================================
// PROVIDER DEL REPOSITORIO
// =============================================================================

/// Singleton del repositorio de ranking
final rankingRepositoryProvider = Provider<RankingRepository>((ref) {
  return RankingRepository(
    databases: ref.watch(appwriteDatabasesProvider),
  );
});

// =============================================================================
// PARÁMETROS DE CONSULTA
// =============================================================================

/// Parámetros para las queries de ranking — inmutable y comparable
class RankingParams extends Equatable {
  final String type; // 'xp' | 'species' | 'biggest'
  final String period; // 'all_time' | 'weekly' | 'monthly'

  const RankingParams({
    required this.type,
    required this.period,
  });

  @override
  List<Object?> get props => [type, period];
}

// =============================================================================
// PROVIDER PRINCIPAL DEL RANKING
// =============================================================================

/// Provider reactivo del listado de ranking.
/// Se auto-dispone al no ser observado y se re-evalúa al cambiar params.
final rankingListProvider = FutureProvider.autoDispose
    .family<List<RankerData>, RankingParams>((ref, params) async {
  final repo = ref.watch(rankingRepositoryProvider);

  // Obtener ID del usuario actual para marcar isCurrentUser
  String? currentUserId;
  try {
    final authState = await ref.watch(authStateProvider.future);
    currentUserId = authState?.$id;
  } catch (_) {}

  switch (params.type) {
    case 'xp':
      return repo.getXpLeaderboard(
        period: params.period,
        currentUserId: currentUserId,
      );
    case 'species':
      return repo.getSpeciesLeaderboard(
        period: params.period,
        currentUserId: currentUserId,
      );
    case 'biggest':
      return repo.getBiggestFishLeaderboard(
        period: params.period,
        currentUserId: currentUserId,
      );
    default:
      return [];
  }
});

// =============================================================================
// POSICIÓN DEL USUARIO ACTUAL
// =============================================================================

/// Posición del usuario autenticado en cada categoría.
/// Se invalida automáticamente cuando cambia authState.
final currentUserRankProvider =
    FutureProvider.autoDispose<UserRankPosition?>((ref) async {
  final authState = await ref.watch(authStateProvider.future);
  if (authState == null) return null;
  final repo = ref.watch(rankingRepositoryProvider);
  return repo.getCurrentUserPosition(authState.$id);
});
