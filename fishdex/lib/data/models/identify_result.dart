/// Modelo de datos para el resultado de identificación de un pez
class IdentifyResult {
  final bool success;
  final String fishId;
  final String species;
  final double confidence;
  final bool isNew;
  final double estimatedSizeCm;
  final String rarity;
  final int xpEarned;
  final FishPreviousData? previousData;
  final String? frameUsed;
  final String message;
  final String timestamp;

  const IdentifyResult({
    required this.success,
    required this.fishId,
    required this.species,
    required this.confidence,
    required this.isNew,
    required this.estimatedSizeCm,
    required this.rarity,
    required this.xpEarned,
    this.previousData,
    this.frameUsed,
    required this.message,
    required this.timestamp,
  });

  factory IdentifyResult.fromJson(Map<String, dynamic> json) {
    return IdentifyResult(
      success: json['success'] as bool,
      fishId: json['fish_id'] as String,
      species: json['species'] as String,
      confidence: (json['confidence'] as num).toDouble(),
      isNew: json['is_new'] as bool,
      estimatedSizeCm: (json['estimated_size_cm'] as num).toDouble(),
      rarity: json['rarity'] as String,
      xpEarned: json['xp_earned'] as int,
      previousData: json['previous_data'] != null
          ? FishPreviousData.fromJson(
              json['previous_data'] as Map<String, dynamic>)
          : null,
      frameUsed: json['frame_used'] as String?,
      message: json['message'] as String,
      timestamp: json['timestamp'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
        'success': success,
        'fish_id': fishId,
        'species': species,
        'confidence': confidence,
        'is_new': isNew,
        'estimated_size_cm': estimatedSizeCm,
        'rarity': rarity,
        'xp_earned': xpEarned,
        'previous_data': previousData?.toJson(),
        'frame_used': frameUsed,
        'message': message,
        'timestamp': timestamp,
      };
}

/// Datos previos de un pez ya identificado anteriormente
class FishPreviousData {
  final String fishId;
  final String species;
  final String firstSeenDate;
  final String? firstSeenLocation;
  final int totalSightings;
  final String lastSeenDate;
  final double lastEstimatedSizeCm;
  final double growthCm;

  const FishPreviousData({
    required this.fishId,
    required this.species,
    required this.firstSeenDate,
    this.firstSeenLocation,
    required this.totalSightings,
    required this.lastSeenDate,
    required this.lastEstimatedSizeCm,
    required this.growthCm,
  });

  factory FishPreviousData.fromJson(Map<String, dynamic> json) {
    return FishPreviousData(
      fishId: json['fish_id'] as String,
      species: json['species'] as String,
      firstSeenDate: json['first_seen_date'] as String,
      firstSeenLocation: json['first_seen_location'] as String?,
      totalSightings: json['total_sightings'] as int,
      lastSeenDate: json['last_seen_date'] as String,
      lastEstimatedSizeCm: (json['last_estimated_size_cm'] as num).toDouble(),
      growthCm: (json['growth_cm'] as num).toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'fish_id': fishId,
        'species': species,
        'first_seen_date': firstSeenDate,
        'first_seen_location': firstSeenLocation,
        'total_sightings': totalSightings,
        'last_seen_date': lastSeenDate,
        'last_estimated_size_cm': lastEstimatedSizeCm,
        'growth_cm': growthCm,
      };
}
