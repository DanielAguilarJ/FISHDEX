/// Modelo de datos para el resultado de identificación de un pez
class IdentifyResult {
  final bool success;
  final String fishId;
  final String species;
  final String? scientificName;
  final String? family;
  final String? commonName;
  final double confidence;
  final bool isNew;
  final double estimatedSizeCm;
  final String rarity;
  final int xpEarned;
  final bool requiresManualInput;
  final FishPreviousData? previousData;
  final String? frameUsed;
  final String message;
  final String timestamp;
  // Czech area system
  final String? areaCode;
  final String? areaName;
  final String? areaUrl;
  final String? speciesCzech;
  final String? speciesEnglish;
  final int? catchNumber;
  final String? userRole;
  // AI model validation breakdown
  final double? detectionConfidence;
  final double? classificationConfidence;
  final double? matchConfidence;

  const IdentifyResult({
    required this.success,
    required this.fishId,
    required this.species,
    this.scientificName,
    this.family,
    this.commonName,
    required this.confidence,
    required this.isNew,
    required this.estimatedSizeCm,
    required this.rarity,
    required this.xpEarned,
    this.requiresManualInput = false,
    this.previousData,
    this.frameUsed,
    required this.message,
    required this.timestamp,
    this.areaCode,
    this.areaName,
    this.areaUrl,
    this.speciesCzech,
    this.speciesEnglish,
    this.catchNumber,
    this.userRole,
    this.detectionConfidence,
    this.classificationConfidence,
    this.matchConfidence,
  });

  factory IdentifyResult.fromJson(Map<String, dynamic> json) {
    return IdentifyResult(
      success: json['success'] as bool,
      fishId: json['fish_id'] as String,
      species: json['species'] as String,
      scientificName: json['scientific_name'] as String?,
      family: json['family'] as String?,
      commonName: json['common_name'] as String?,
      confidence: (json['confidence'] as num).toDouble(),
      isNew: json['is_new'] as bool,
      estimatedSizeCm: (json['estimated_size_cm'] as num).toDouble(),
      rarity: json['rarity'] as String,
      xpEarned: json['xp_earned'] as int,
      requiresManualInput: json['requires_manual_input'] as bool? ?? false,
      previousData: json['previous_data'] != null
          ? FishPreviousData.fromJson(
              json['previous_data'] as Map<String, dynamic>)
          : null,
      frameUsed: json['frame_used'] as String?,
      message: json['message'] as String,
      timestamp: json['timestamp'] as String,
      areaCode: json['area_code'] as String?,
      areaName: json['area_name'] as String?,
      areaUrl: json['area_url'] as String?,
      speciesCzech: json['species_czech'] as String?,
      speciesEnglish: json['species_english'] as String?,
      catchNumber: json['catch_number'] as int?,
      userRole: json['user_role'] as String?,
      detectionConfidence: (json['detection_confidence'] as num?)?.toDouble(),
      classificationConfidence:
          (json['classification_confidence'] as num?)?.toDouble(),
      matchConfidence: (json['match_confidence'] as num?)?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'success': success,
        'fish_id': fishId,
        'species': species,
        'scientific_name': scientificName,
        'family': family,
        'common_name': commonName,
        'confidence': confidence,
        'is_new': isNew,
        'estimated_size_cm': estimatedSizeCm,
        'rarity': rarity,
        'xp_earned': xpEarned,
        'requires_manual_input': requiresManualInput,
        'previous_data': previousData?.toJson(),
        'frame_used': frameUsed,
        'message': message,
        'timestamp': timestamp,
        'area_code': areaCode,
        'area_name': areaName,
        'area_url': areaUrl,
        'species_czech': speciesCzech,
        'species_english': speciesEnglish,
        'catch_number': catchNumber,
        'user_role': userRole,
        'detection_confidence': detectionConfidence,
        'classification_confidence': classificationConfidence,
        'match_confidence': matchConfidence,
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
