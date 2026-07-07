/// Modelo de captura de pez con todos los datos extendidos
class FishCapture {
  /// UUID único por captura
  final String captureId;

  /// ID del pez (reutilizable si es el mismo individuo)
  final String fishId;

  /// ID del usuario que realizó la captura
  final String userId;

  /// Latitud GPS de la captura
  final double latitude;

  /// Longitud GPS de la captura
  final double longitude;

  /// Fecha y hora de la captura
  final DateTime capturedAt;

  /// Nombre de la especie identificada
  final String species;

  /// Nombre científico (si disponible)
  final String? scientificName;

  /// Familia taxonómica (si disponible)
  final String? family;

  /// Longitud estimada en centímetros
  final double? lengthCm;

  /// Peso estimado en kilogramos
  final double? weightKg;

  /// Condición del pez: alive, released, dead
  final String? condition;

  /// URL del video de 10 segundos
  final String? videoUrl;

  /// URL de la imagen/frame
  final String? imageUrl;

  /// Confianza de la identificación por IA (0.0 a 1.0)
  final double confidence;

  /// Color predominante del pez
  final String? predominantColor;

  /// Características físicas descriptivas
  final String? physicalFeatures;

  /// Notas adicionales del usuario
  final String? notes;

  /// Rareza del pez: common, uncommon, rare, legendary
  final String rarity;

  /// Si la entrada fue manual (formulario) o automática (IA)
  final bool isManualEntry;

  /// XP ganada por esta captura
  final int xpEarned;

  /// Si es la primera vez que se registra este fish_id
  final bool isNewFish;

  /// ID del spot de pesca asociado
  final String? spotId;

  /// Datos adicionales no estructurados
  final Map<String, dynamic>? additionalData;

  const FishCapture({
    required this.captureId,
    required this.fishId,
    required this.userId,
    required this.latitude,
    required this.longitude,
    required this.capturedAt,
    required this.species,
    this.scientificName,
    this.family,
    this.lengthCm,
    this.weightKg,
    this.condition,
    this.videoUrl,
    this.imageUrl,
    required this.confidence,
    this.predominantColor,
    this.physicalFeatures,
    this.notes,
    required this.rarity,
    required this.isManualEntry,
    required this.xpEarned,
    required this.isNewFish,
    this.spotId,
    this.additionalData,
  });

  /// Crear desde un mapa (documento Appwrite)
  factory FishCapture.fromMap(Map<String, dynamic> map) {
    return FishCapture(
      captureId: map['\$id'] as String? ?? map['capture_id'] as String? ?? '',
      fishId: map['fish_id'] as String? ?? '',
      userId: map['user_id'] as String? ?? '',
      latitude: (map['latitude'] as num?)?.toDouble() ?? 0.0,
      longitude: (map['longitude'] as num?)?.toDouble() ?? 0.0,
      capturedAt: map['captured_at'] != null
          ? DateTime.parse(map['captured_at'] as String)
          : DateTime.now(),
      species: map['species'] as String? ?? 'Desconocido',
      scientificName: map['scientific_name'] as String?,
      family: map['family'] as String?,
      lengthCm: (map['length_cm'] as num?)?.toDouble(),
      weightKg: (map['weight_kg'] as num?)?.toDouble(),
      condition: map['condition'] as String?,
      videoUrl: map['video_url'] as String?,
      imageUrl: map['image_url'] as String?,
      confidence: (map['confidence'] as num?)?.toDouble() ?? 0.0,
      predominantColor: map['predominant_color'] as String?,
      physicalFeatures: map['physical_features'] as String?,
      notes: map['notes'] as String?,
      rarity: map['rarity'] as String? ?? 'common',
      isManualEntry: map['is_manual_entry'] as bool? ?? false,
      xpEarned: (map['xp_earned'] as num?)?.toInt() ?? 0,
      isNewFish: map['is_new'] as bool? ?? true,
      spotId: map['spot_id'] as String?,
      additionalData: map['additional_data'] is Map
          ? Map<String, dynamic>.from(map['additional_data'] as Map)
          : null,
    );
  }

  /// Convertir a mapa para guardar en Appwrite
  Map<String, dynamic> toMap() {
    return {
      'fish_id': fishId,
      'user_id': userId,
      'latitude': latitude,
      'longitude': longitude,
      'captured_at': capturedAt.toIso8601String(),
      'species': species,
      'scientific_name': scientificName,
      'family': family,
      'length_cm': lengthCm,
      'weight_kg': weightKg,
      'condition': condition,
      'video_url': videoUrl,
      'image_url': imageUrl,
      'confidence': confidence,
      'predominant_color': predominantColor,
      'physical_features': physicalFeatures,
      'notes': notes,
      'rarity': rarity,
      'is_manual_entry': isManualEntry,
      'xp_earned': xpEarned,
      'is_new': isNewFish,
      'spot_id': spotId,
      'additional_data': additionalData,
    };
  }

  /// Versión anonimizada para fisherman (sin datos sensibles de otros)
  Map<String, dynamic> toAnonymizedMap() {
    return {
      'fish_id': fishId,
      'species': species,
      'rarity': rarity,
      'previously_registered': true,
      // NO incluir: userId, latitude, longitude, capturedAt, notas, etc.
    };
  }

  FishCapture copyWith({
    String? captureId,
    String? fishId,
    String? userId,
    double? latitude,
    double? longitude,
    DateTime? capturedAt,
    String? species,
    String? scientificName,
    String? family,
    double? lengthCm,
    double? weightKg,
    String? condition,
    String? videoUrl,
    String? imageUrl,
    double? confidence,
    String? predominantColor,
    String? physicalFeatures,
    String? notes,
    String? rarity,
    bool? isManualEntry,
    int? xpEarned,
    bool? isNewFish,
    String? spotId,
    Map<String, dynamic>? additionalData,
  }) {
    return FishCapture(
      captureId: captureId ?? this.captureId,
      fishId: fishId ?? this.fishId,
      userId: userId ?? this.userId,
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
      capturedAt: capturedAt ?? this.capturedAt,
      species: species ?? this.species,
      scientificName: scientificName ?? this.scientificName,
      family: family ?? this.family,
      lengthCm: lengthCm ?? this.lengthCm,
      weightKg: weightKg ?? this.weightKg,
      condition: condition ?? this.condition,
      videoUrl: videoUrl ?? this.videoUrl,
      imageUrl: imageUrl ?? this.imageUrl,
      confidence: confidence ?? this.confidence,
      predominantColor: predominantColor ?? this.predominantColor,
      physicalFeatures: physicalFeatures ?? this.physicalFeatures,
      notes: notes ?? this.notes,
      rarity: rarity ?? this.rarity,
      isManualEntry: isManualEntry ?? this.isManualEntry,
      xpEarned: xpEarned ?? this.xpEarned,
      isNewFish: isNewFish ?? this.isNewFish,
      spotId: spotId ?? this.spotId,
      additionalData: additionalData ?? this.additionalData,
    );
  }
}
