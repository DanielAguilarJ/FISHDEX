import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Holds capture metadata state during the fish identification flow.
/// This provider is accessible from both the camera screen (to set GPS + area)
/// and the result screen (to show what was submitted).
class CaptureMetadata {
  final String? areaCode;
  final String? areaName;
  final String? species;
  final String? fishState;
  final String? customName;
  final String? weather;
  final String? bite;
  final double? size;
  final double? lat;
  final double? lon;

  const CaptureMetadata({
    this.areaCode,
    this.areaName,
    this.species,
    this.fishState,
    this.customName,
    this.weather,
    this.bite,
    this.size,
    this.lat,
    this.lon,
  });

  CaptureMetadata copyWith({
    String? areaCode,
    String? areaName,
    String? species,
    String? fishState,
    String? customName,
    String? weather,
    String? bite,
    double? size,
    double? lat,
    double? lon,
  }) {
    return CaptureMetadata(
      areaCode: areaCode ?? this.areaCode,
      areaName: areaName ?? this.areaName,
      species: species ?? this.species,
      fishState: fishState ?? this.fishState,
      customName: customName ?? this.customName,
      weather: weather ?? this.weather,
      bite: bite ?? this.bite,
      size: size ?? this.size,
      lat: lat ?? this.lat,
      lon: lon ?? this.lon,
    );
  }

  /// Returns an empty/reset state
  static const CaptureMetadata empty = CaptureMetadata();
}

/// StateNotifier that manages capture metadata throughout the identification flow.
class CaptureMetadataNotifier extends StateNotifier<CaptureMetadata> {
  CaptureMetadataNotifier() : super(CaptureMetadata.empty);

  /// Set the fishing area code and name
  void setArea(String code, String name) {
    state = state.copyWith(areaCode: code, areaName: name);
  }

  /// Set the species (from dropdown selection)
  void setSpecies(String species) {
    state = state.copyWith(species: species);
  }

  /// Set fish state/condition notes
  void setFishState(String fishState) {
    state = state.copyWith(fishState: fishState);
  }

  /// Set custom name for the fish
  void setCustomName(String name) {
    state = state.copyWith(customName: name);
  }

  /// Set weather conditions
  void setWeather(String weather) {
    state = state.copyWith(weather: weather);
  }

  /// Set bait/lure used
  void setBite(String bite) {
    state = state.copyWith(bite: bite);
  }

  /// Set measured size in cm
  void setSize(double size) {
    state = state.copyWith(size: size);
  }

  /// Set GPS location
  void setLocation(double lat, double lon) {
    state = state.copyWith(lat: lat, lon: lon);
  }

  /// Reset all metadata after successful identification
  void reset() {
    state = CaptureMetadata.empty;
  }
}

/// Provider for capture metadata state
final captureMetadataProvider =
    StateNotifierProvider<CaptureMetadataNotifier, CaptureMetadata>(
  (ref) => CaptureMetadataNotifier(),
);
