/// Model representing a Czech fishing area (revír).
class FishingArea {
  final String code;
  final String codeClean;
  final String name;
  final double? lat;
  final double? lon;
  final double? lat2;
  final double? lon2;
  final String? url;
  final String regionCode;
  final double? distanceKm;

  const FishingArea({
    required this.code,
    required this.codeClean,
    required this.name,
    this.lat,
    this.lon,
    this.lat2,
    this.lon2,
    this.url,
    required this.regionCode,
    this.distanceKm,
  });

  /// Create from JSON response
  factory FishingArea.fromJson(Map<String, dynamic> json) {
    return FishingArea(
      code: json['code'] as String? ?? '',
      codeClean: json['code_clean'] as String? ?? '',
      name: json['name'] as String? ?? '',
      lat: (json['lat'] as num?)?.toDouble(),
      lon: (json['lon'] as num?)?.toDouble(),
      lat2: (json['lat2'] as num?)?.toDouble(),
      lon2: (json['lon2'] as num?)?.toDouble(),
      url: json['url'] as String?,
      regionCode: json['region_code'] as String? ?? '',
      distanceKm: (json['distance_km'] as num?)?.toDouble(),
    );
  }

  /// Convert to JSON
  Map<String, dynamic> toJson() => {
        'code': code,
        'code_clean': codeClean,
        'name': name,
        'lat': lat,
        'lon': lon,
        'lat2': lat2,
        'lon2': lon2,
        'url': url,
        'region_code': regionCode,
        if (distanceKm != null) 'distance_km': distanceKm,
      };

  /// Formatted display string for dropdown
  String get displayName => '$code \u2014 $name';

  /// Distance display string (if available)
  String get distanceDisplay =>
      distanceKm != null ? '${distanceKm!.toStringAsFixed(1)} km' : '';

  @override
  String toString() => displayName;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is FishingArea &&
          runtimeType == other.runtimeType &&
          codeClean == other.codeClean;

  @override
  int get hashCode => codeClean.hashCode;
}
